"""シリアル接続から最新の SPL・SPR を取得するモジュール。"""

import csv
from datetime import datetime
import os
import sys
import threading
import time

import serial


def _experiment_directory():
    # Walk past this module's logging wrapper to the experiment script.
    caller = sys._getframe(2)
    while caller is not None and caller.f_globals is globals():
        caller = caller.f_back
    if caller is not None:
        script = caller.f_globals.get('__file__') or caller.f_code.co_filename
        if script and not script.startswith('<'):
            return os.path.dirname(os.path.abspath(script))

    main_script = getattr(sys.modules.get('__main__'), '__file__', None)
    if main_script and not main_script.startswith('<'):
        return os.path.dirname(os.path.abspath(main_script))
    return os.getcwd()


class SPLSPRMonitor:
    PAYLOAD_LENGTH = 8

    def __init__(
        self,
        port='COM2',
        baudrate=19200,
        read_interval=None,
        print_values=False,
        csv_path=None,
        csv_flush=True,
    ):
        if read_interval is not None and read_interval <= 0:
            raise ValueError('read_interval must be positive')
        self.port = port
        self.baudrate = baudrate
        self.read_interval = read_interval
        self.print_values = print_values
        self.csv_path = csv_path
        self.csv_flush = csv_flush
        self._latest = (None, None)
        self._serial_buffer = ''
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._log_lock = threading.Lock()
        self._log_file = None
        self._log_writer = None
        self._log_started_at = None
        self._reader = None

    def start(self):
        """シリアルポートを開いて受信を開始する。接続に失敗したら False を返す。"""
        with self._lock:
            if self._reader is not None and self._reader.is_alive():
                return True
            try:
                connection = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=0.1,
                )
            except serial.SerialException as error:
                print('SPR serial open failed: {}'.format(error))
                return False

            try:
                self._latest = (None, None)
                self._serial_buffer = ''
                self._stop_event.clear()
                self._reader = threading.Thread(
                    target=self._receive,
                    args=(connection,),
                    name='SPL-SPR receiver',
                    daemon=True,
                )
                self._reader.start()
            except BaseException:
                connection.close()
                raise
            return True

    def stop(self):
        """受信を停止し、シリアルポートとCSVを閉じる。"""
        with self._lock:
            if self._reader is not None:
                self._stop_event.set()
                self._reader.join()
                self._reader = None
            self._latest = (None, None)

    def start_logging(self, csv_path=None):
        """Start CSV recording and return its path."""
        with self._lock, self._log_lock:
            if self._reader is None or not self._reader.is_alive() or self._stop_event.is_set():
                raise RuntimeError('Call start() before starting CSV recording.')
            if self._log_file is not None:
                return self._log_file.name

            path = self.csv_path if csv_path is None else csv_path
            if path is None:
                path = datetime.now().strftime('spl_spr_log_%Y%m%d_%H%M%S_%f.csv')
            if not os.path.isabs(path):
                path = os.path.join(_experiment_directory(), path)
            log_dir = os.path.dirname(path)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)
            log_file = open(path, 'w', newline='')
            try:
                writer = csv.writer(log_file)
                writer.writerow(['elapsed_time_sec', 'unix_time_sec', 'spl', 'spr'])
                if self.csv_flush:
                    log_file.flush()
            except BaseException:
                log_file.close()
                raise

            self._log_file = log_file
            self._log_writer = writer
            self._log_started_at = time.monotonic()
            return log_file.name

    def stop_logging(self):
        """Close the CSV log while keeping serial reception active."""
        with self._lock:
            self._close_log()

    def _close_log(self):
        with self._log_lock:
            log_file = self._log_file
            self._log_file = None
            self._log_writer = None
            if log_file is not None:
                log_file.close()

    def get_spl(self):
        """最新の SPL を返す。有効な受信値がなければ None。"""
        return self._latest[0]

    def get_spr(self):
        """最新の SPR を返す。有効な受信値がなければ None。"""
        return self._latest[1]

    def get_values(self):
        """同じ受信フレームの (SPL, SPR) を返す。"""
        return self._latest

    def _receive(self, connection):
        try:
            while not self._stop_event.is_set():
                waiting = connection.in_waiting
                if self.read_interval is None:
                    # Block for the first byte when the receive buffer is empty.
                    waiting = max(1, waiting)
                if waiting:
                    raw = connection.read(waiting).decode('ascii', errors='ignore')
                    for spl, spr in self._consume(raw):
                        self._latest = (spl, spr)
                        with self._log_lock:
                            if self._log_writer is not None:
                                elapsed = time.monotonic() - self._log_started_at
                                self._log_writer.writerow([
                                    '{:.6f}'.format(value)
                                    for value in (elapsed, time.time(), spl, spr)
                                ])
                                if self.csv_flush:
                                    self._log_file.flush()
                        if self.print_values:
                            print('SPL:{:7.3f}  SPR:{:7.3f}'.format(spl, spr))
                if self.read_interval is not None:
                    self._stop_event.wait(self.read_interval)
        except (serial.SerialException, OSError) as error:
            print('SPL/SPR receive failed: {}'.format(error))
        finally:
            self._stop_event.set()
            self._latest = (None, None)
            try:
                connection.close()
            finally:
                self._close_log()

    def _consume(self, raw):
        self._serial_buffer += raw
        while True:
            start = self._serial_buffer.find(':')
            if start == -1:
                self._serial_buffer = ''
                return
            self._serial_buffer = self._serial_buffer[start:]
            if len(self._serial_buffer) < self.PAYLOAD_LENGTH:
                return
            next_start = self._serial_buffer.find(':', 1, self.PAYLOAD_LENGTH)
            if next_start != -1:
                self._serial_buffer = self._serial_buffer[next_start:]
                continue
            # Only consume the measurement prefix. The next ':' delimits
            # another sample even when several samples arrive in one read.
            payload = self._serial_buffer[:self.PAYLOAD_LENGTH]
            self._serial_buffer = self._serial_buffer[self.PAYLOAD_LENGTH:]
            values = self.parse_frame(payload)
            if values is not None:
                yield values

    @staticmethod
    def parse_frame(frame):
        try:
            spl_raw = int(frame[1:4], 16)
            spr_raw = int(frame[5:8], 16)
        except (TypeError, ValueError):
            return None
        if spl_raw >= 0xC00:
            spl_raw -= 0x1000
        if spr_raw >= 0xC00:
            spr_raw -= 0x1000
        return (spl_raw * 2.0) / 1000.0, (spr_raw * 2.0) / 1000.0


_default_monitor = None
_default_lock = threading.Lock()


def start(**kwargs):
    """既定のモニターを開始する。接続に失敗したら None を返す。"""
    global _default_monitor
    with _default_lock:
        if _default_monitor is None:
            monitor = SPLSPRMonitor(**kwargs)
        else:
            monitor = _default_monitor
        if monitor.start():
            _default_monitor = monitor
            return monitor
        return None


def start_logging(csv_path=None):
    """Start CSV recording for the default monitor."""
    with _default_lock:
        if _default_monitor is None:
            raise RuntimeError('Call start() before starting CSV recording.')
        return _default_monitor.start_logging(csv_path)


start.logging = start_logging


def stop():
    """既定のモニターを停止する。"""
    global _default_monitor
    with _default_lock:
        if _default_monitor is not None:
            _default_monitor.stop()
            _default_monitor = None


def stop_logging():
    """Close the default monitor's CSV log while keeping reception active."""
    with _default_lock:
        if _default_monitor is not None:
            _default_monitor.stop_logging()


def get_current_values():
    """既定のモニターから、同じ受信フレームの (SPL, SPR) を取得する。"""
    monitor = _default_monitor
    return monitor.get_values() if monitor is not None else (None, None)


def get_spl():
    """既定のモニターから最新の SPL を取得する。"""
    return get_current_values()[0]


def get_spr():
    """既定のモニターから最新の SPR を取得する。"""
    return get_current_values()[1]
