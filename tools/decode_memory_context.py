# -*- coding: utf-8 -*-
"""PPSSPP memory.read의 base64 응답을 현재 한글 코드표로 가볍게 표시한다."""
import argparse
import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('base64')
    ap.add_argument('--offset', type=lambda x: int(x, 0), default=0)
    ap.add_argument('--length', type=lambda x: int(x, 0), default=0x100)
    args = ap.parse_args()
    raw = base64.b64decode(args.base64)[args.offset:args.offset + args.length]
    table = {}
    for line in (ROOT / 'build_jp' / 'hangul_codes.tsv').read_text(encoding='utf-8').splitlines()[1:]:
        ch, c1, c2, _i, _g = line.split('\t')
        table[bytes((int(c1, 16), int(c2, 16)))] = ch
    out = []
    i = 0
    while i < len(raw):
        pair = raw[i:i + 2]
        if pair in table:
            out.append(table[pair]); i += 2
        elif 0x20 <= raw[i] < 0x7F:
            out.append(chr(raw[i])); i += 1
        elif raw[i] == 0:
            out.append('·'); i += 1
        else:
            out.append('□'); i += 1
    print(raw.hex(' '))
    print(''.join(out))


if __name__ == '__main__':
    main()
