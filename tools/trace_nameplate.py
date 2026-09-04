# -*- coding: utf-8 -*-
"""현재 대사창의 일본어 이름 문자열을 읽는 MIPS PC를 추적한다.

사용:
  1. PPSSPP를 RemoteDebuggerOnStartup=True(기본 포트 4543)로 실행한다.
  2. 일본어 이름표가 보이는 대사에서 멈춘다.
  3. python tools/trace_nameplate.py ママ

CPU를 잠깐 멈춰 RAM에서 문자열을 찾고 모든 사본에 read watchpoint를 건 뒤 재개한다.
이름표가 다음 프레임에 다시 그려지면 해당 읽기 PC에서 자동 정지한다.
"""
import base64
import sys

from ppsspp_dbg import Dbg
from ppsspp_ws import ws_send
import krtext

RAM_START = 0x08800000
RAM_END = 0x0A000000
CHUNK = 0x00100000


def pause(d):
    status = d.req({'event': 'cpu.status'})
    if not status.get('stepping') and not status.get('paused'):
        # PPSSPP 1.20.x의 stepping/resume은 즉시 ticket 응답을 주지 않는
        # 비동기 명령이다. req()로 기다리면 영원히 대기하므로 broadcast를 받는다.
        ws_send(d.s, {'event': 'cpu.stepping'})
        d.wait_event('cpu.stepping', timeout=5)


def scan(d, needle):
    hits = []
    for addr in range(RAM_START, RAM_END, CHUNK):
        size = min(CHUNK, RAM_END - addr)
        data = d.read(addr, size)
        pos = 0
        while True:
            pos = data.find(needle, pos)
            if pos < 0:
                break
            hits.append(addr + pos)
            pos += 1
    return hits


def main():
    text = sys.argv[1] if len(sys.argv) > 1 else 'ママ'
    # 한글 패치 문자열도 그대로 추적할 수 있게 게임 전용 인코더를 사용한다.
    # 원문 일본어는 기존과 같이 CP932로 처리한다.
    needle = (krtext.encode(text) if any('\uac00' <= ch <= '\ud7a3' for ch in text)
              else text.encode('cp932'))
    d = Dbg()
    print(d.req({'event': 'game.status'}))
    pause(d)

    hits = scan(d, needle)
    print(f'{text}: {len(hits)}개', ' '.join(f'{x:08X}' for x in hits))
    if not hits:
        print('현재 RAM에 문자열이 없다. 이름표가 보이는 프레임에서 다시 실행할 것.')
        d.req({'event': 'cpu.resume'})
        return 2

    for addr in hits:
        ctx = d.read(max(RAM_START, addr - 16), len(needle) + 32)
        print(f'  {addr:08X}: {ctx.hex(" ")}')
        d.req({
            'event': 'memory.breakpoint.add',
            'address': addr,
            'size': len(needle),
            'enabled': True,
            'log': False,
            'read': True,
            'write': False,
            'change': False,
        })

    print('read watchpoint 설정 완료. CPU 재개 — 히트를 기다린다.')
    d.req({'event': 'cpu.resume'})
    ev = d.wait_event('cpu.stepping', timeout=30)
    print('HIT', ev)
    pc = ev.get('pc')
    if pc is not None:
        print(d.req({'event': 'memory.disasm', 'address': max(0, pc - 32), 'count': 24}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
