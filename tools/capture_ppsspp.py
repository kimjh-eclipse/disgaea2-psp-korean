# -*- coding: utf-8 -*-
"""PPSSPP 원격 디버거의 현재 PSP 프레임버퍼를 PNG로 저장한다."""
import base64
import pathlib
import sys

from ppsspp_dbg import Dbg
from ppsspp_ws import ws_send
from trace_nameplate import pause


def main():
    target = pathlib.Path(sys.argv[1])
    d = Dbg()
    pause(d)
    response = d.req({'event': 'gpu.buffer.screenshot', 'type': 'uri'})
    uri = response.get('uri', '')
    prefix = 'data:image/png;base64,'
    if not uri.startswith(prefix):
        raise SystemExit(f'스크린샷 응답 오류: {response}')
    target.write_bytes(base64.b64decode(uri[len(prefix):]))
    ws_send(d.s, {'event': 'cpu.resume'})
    print(f'{response.get("width")}x{response.get("height")}: {target}')


if __name__ == '__main__':
    main()
