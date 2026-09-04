# -*- coding: utf-8 -*-
"""직업 설명 문자열을 그리는 공용 폰트 함수의 호출 인자를 잡는다."""
import json
import time

from ppsspp_dbg import Dbg
from ppsspp_ws import ws_send
from trace_nameplate import pause

ENTRY = 0x088A8748
TEXT = 0x09753620


def main():
    d = Dbg()
    status = None
    for _ in range(60):
        status = d.req({'event': 'game.status'})
        if status.get('game'):
            break
        time.sleep(0.25)
    print(status, flush=True)
    if not status or not status.get('game'):
        raise SystemExit('게임이 시작되지 않았습니다.')
    time.sleep(0.8)
    pause(d)
    actual = d.read(TEXT, 8)
    print(f'text {TEXT:08X}: {actual.hex(" ")}', flush=True)
    result = d.req({
        'event': 'cpu.breakpoint.add', 'address': ENTRY,
        'enabled': True, 'log': False,
        'condition': f't0 == 0x{TEXT:08X}',
    })
    print(result, flush=True)
    ws_send(d.s, {'event': 'cpu.resume'})
    ev = d.wait_event('cpu.stepping', timeout=15)
    print('HIT', json.dumps(ev, ensure_ascii=False), flush=True)
    regs = d.req({'event': 'cpu.getAllRegs'})
    print('REGS', json.dumps(regs, ensure_ascii=False), flush=True)
    print('BACKTRACE', json.dumps(d.req({'event': 'hle.backtrace'}),
                                       ensure_ascii=False), flush=True)
    # ra가 호출 직후이므로 주변 호출부도 함께 본다.
    values = regs.get('registers') or regs.get('regs') or []
    ra = None
    for reg in values:
        if reg.get('name') == 'ra':
            ra = reg.get('uintValue', reg.get('value'))
            break
    if ra:
        print('CALLER', json.dumps(d.req({
            'event': 'memory.disasm', 'address': ra - 0x40,
            'count': 32, 'compact': True,
        }), ensure_ascii=False), flush=True)
    ws_send(d.s, {'event': 'cpu.resume'})


if __name__ == '__main__':
    main()
