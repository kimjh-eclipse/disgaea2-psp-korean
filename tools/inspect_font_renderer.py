# -*- coding: utf-8 -*-
"""공용 폰트 렌더러의 진입부와 호출부를 원격 디버거로 출력한다."""
import json

from ppsspp_dbg import Dbg
from ppsspp_ws import ws_send
from trace_nameplate import pause


def main():
    d = Dbg()
    pause(d)
    for address, count in ((0x088A8748, 96), (0x088A9C60, 64)):
        result = d.req({'event': 'memory.disasm', 'address': address,
                        'count': count, 'compact': True})
        print(json.dumps(result, ensure_ascii=False, indent=2))
    ws_send(d.s, {'event': 'cpu.resume'})


if __name__ == '__main__':
    main()
