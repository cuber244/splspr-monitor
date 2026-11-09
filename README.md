# splspr

Read SPL and SPR measurements from a compatible serial device in Python.
The module receives data in the background and can record it to CSV.
The library works without Vizard. A Vizard keyboard demo is included in the
source distribution under `examples/`.

SPL・SPR測定器から値を受信するPythonモジュールです。SPLとSPRを個別に取得でき、
CSV記録の開始・終了も個別に操作できます。

[PyPI project](https://pypi.org/project/splspr/)

## Installation

```sh
python -m pip install splspr
```

Python 3.8 or later and a measurement device using the compatible serial
protocol are required. The default serial settings are `COM2`, 19200 baud,
8 data bits, no parity, and one stop bit. Set `port` to match your device.
Vizard 7 and 8 are supported. Install the package in Vizard's own Python environment.

## Usage

```python
import time

import spl_spr_monitor as monitor

if monitor.start(port="COM2") is None:
    raise RuntimeError("Could not open the measurement device.")

try:
    monitor.start.logging()  # Optional
    for _ in range(5):
        time.sleep(0.1)
        spl, spr = monitor.get_current_values()
        if spl is not None:
            print(f"SPL={spl:.3f} SPR={spr:.3f}")
    monitor.stop_logging()
finally:
    monitor.stop()
```

- `start()` opens the serial connection and begins receiving samples.
- `get_spl()` and `get_spr()` return the latest values individually.
  `get_current_values()` returns a pair from the same sample. Before the
  first valid sample, the values are `None`.
- `start.logging()` starts CSV recording and returns the file path.
  By default, the file is created beside the calling script. Pass
  `csv_path` to choose another location.
- `stop_logging()` closes the CSV and keeps the connection open.
  `stop()` closes both the serial connection and any active CSV.

CSV columns are `elapsed_time_sec`, `unix_time_sec`, `spl`, and `spr`.
The timestamps are assigned by the receiving computer.

## License

MIT. See `LICENSE`.
