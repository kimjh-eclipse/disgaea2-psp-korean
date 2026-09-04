# -*- coding: utf-8 -*-
"""바이너리에서 NUL 경계 CP932 문자열 후보를 출력한다."""
import sys
from pathlib import Path


def visible(text):
    return sum(c.isprintable() and c not in '\x00\r\n\t' for c in text) >= 2


def main():
    for arg in sys.argv[1:]:
        path = Path(arg)
        data = path.read_bytes()
        print(f'\n== {path} ==')
        start = 0
        while start < len(data):
            end = data.find(b'\0', start)
            if end < 0:
                end = len(data)
            raw = data[start:end]
            if raw:
                # 구조 바이트가 앞에 붙는 경우를 위해 0..7바이트를 건너뛰어 본다.
                for skip in range(min(8, len(raw))):
                    try:
                        text = raw[skip:].decode('cp932')
                    except UnicodeDecodeError:
                        continue
                    if visible(text):
                        print(f'0x{start + skip:06X}\t{text!r}')
                        break
            start = end + 1


if __name__ == '__main__':
    main()
