"""VizardでAキーを押すとSPR、Sキーを押すとSPLを表示する。"""

import atexit

import viz
import vizact

import spl_spr_monitor

def print_spr():
    value = spl_spr_monitor.get_spr()
    print('SPR: 未受信' if value is None else 'SPR: {:.3f}'.format(value))


def print_spl():
    value = spl_spr_monitor.get_spl()
    print('SPL: 未受信' if value is None else 'SPL: {:.3f}'.format(value))


def exit_program():
    spl_spr_monitor.stop()
    viz.quit()


def main():
    viz.go()
    if spl_spr_monitor.start() is None:
        print('SPL/SPRデバイスに接続できませんでした。COMポートを確認してください。')
        viz.quit()
        return

    atexit.register(spl_spr_monitor.stop)
    spl_spr_monitor.start.logging()
    vizact.onkeydown('a', print_spr)
    vizact.onkeydown('s', print_spl)
    vizact.onkeydown(viz.KEY_ESCAPE, exit_program)
    print('Aキー: SPR / Sキー: SPL / Escキー: 終了')


if __name__ == '__main__':
    main()
