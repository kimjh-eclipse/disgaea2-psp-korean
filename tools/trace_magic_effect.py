# -*- coding: utf-8 -*-
"""3번 상태의 직업 설명을 다시 열어 실제 문자열 읽기 PC를 잡는다."""
import json
import time

import krtext
from ppsspp_dbg import Dbg
from ppsspp_ws import ws_send
from trace_nameplate import pause, scan


def main():
    d = Dbg()
    status = None
    for _ in range(40):
        status = d.req({'event': 'game.status'})
        if status.get('game'):
            break
        time.sleep(0.25)
    print(status, flush=True)
    if not status or not status.get('game'):
        raise SystemExit('게임 부팅을 기다렸지만 시작되지 않았습니다.')
    time.sleep(1.0)
    pause(d)
    needle = krtext.encode('최전선에서')
    # 이 상태 파일에서 검증한 magic.dat 41번 레코드의 PSP 가상주소.
    # 32 MiB 전수 스캔은 원격 API에서 느리므로 바이트를 확인하고 바로 사용한다.
    addr = 0x09753620
    actual = d.read(addr, len(needle))
    if actual != needle:
        d.req({'event': 'cpu.resume'})
        raise SystemExit(f'기준 문자열 주소 불일치: {actual.hex()}')
    print('문자열 주소:', f'{addr:08X}', flush=True)
    print(d.req({
        'event': 'memory.breakpoint.add',
        'address': addr,
        'size': len(needle),
        # 먼저 로그 전용으로 PC를 얻는다. 현재 화면이 매 프레임 읽더라도
        # 입력 처리 전에 CPU가 멈추는 교착을 피한다.
        'enabled': False,
        'log': True,
        'read': True,
        'write': False,
        'change': False,
    }), flush=True)
    ws_send(d.s, {'event': 'cpu.resume'})
    time.sleep(0.2)

    try:
        ev = d.wait_event('cpu.breakpoint.hit', timeout=2)
    except TimeoutError:
        # 상세 화면 -> 직업 목록 -> 같은 직업 상세 화면.
        print('circle down', d.req({
            'event': 'input.buttons.send', 'buttons': {'circle': True},
        }), flush=True)
        time.sleep(0.08)
        print('circle up', d.req({
            'event': 'input.buttons.send', 'buttons': {'circle': False},
        }), flush=True)
        time.sleep(0.7)
        print('cross down', d.req({
            'event': 'input.buttons.send', 'buttons': {'cross': True},
        }), flush=True)
        time.sleep(0.08)
        print('cross up', d.req({
            'event': 'input.buttons.send', 'buttons': {'cross': False},
        }), flush=True)
        ev = d.wait_event('cpu.breakpoint.hit', timeout=10)
    print('LOG HIT', json.dumps(ev, ensure_ascii=False), flush=True)
    pc = ev.get('pc') or ev.get('hit', {}).get('pc')
    if pc is not None:
        pause(d)
        d.req({'event': 'cpu.breakpoint.add', 'address': pc,
               'enabled': True, 'log': False})
        ws_send(d.s, {'event': 'cpu.resume'})
        stop = d.wait_event('cpu.stepping', timeout=10)
        print('EXEC HIT', json.dumps(stop, ensure_ascii=False), flush=True)
        print('DISASM', json.dumps(d.req({
            'event': 'memory.disasm', 'address': max(0, pc - 64),
            'count': 40, 'compact': True,
        }), ensure_ascii=False), flush=True)
        print('REGS', json.dumps(d.req({'event': 'cpu.getAllRegs'}),
                                      ensure_ascii=False), flush=True)
        print('BACKTRACE', json.dumps(d.req({'event': 'hle.backtrace'}),
                                           ensure_ascii=False), flush=True)
    ws_send(d.s, {'event': 'cpu.resume'})


if __name__ == '__main__':
    main()
