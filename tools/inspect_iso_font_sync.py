# -*- coding: utf-8 -*-
"""최종 ISO의 START 글꼴 멤버와 현재 빌드 산출물을 바이트 단위로 비교한다."""
import hashlib
import struct
from pathlib import Path

from nislzs import decompress
from verify_iso import read_iso_file

ROOT = Path(__file__).resolve().parent.parent


def members(raw):
    count = struct.unpack_from('<I', raw, 0)[0]
    entries = []
    for i in range(count):
        at = 0x10 + i * 0x20
        offset = struct.unpack_from('<I', raw, at)[0] + 0x2B0
        name = raw[at + 4:at + 0x20].split(b'\0')[0].decode('latin1')
        entries.append((offset, name))
    ordered = sorted(entries)
    return {
        name: raw[offset:(ordered[i + 1][0] if i + 1 < len(ordered) else len(raw))]
        for i, (offset, name) in enumerate(ordered)
    }


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    with (ROOT / 'build_jp' / 'D2_JP_KR.iso').open('rb') as iso:
        packed, _, _ = read_iso_file(iso, 25, b'START_JP.LZS')
    actual = members(decompress(packed))
    for name in ('fontB.fnt', 'fontB.ftd', 'FontB0000.txp'):
        expected = (ROOT / 'build_jp' / name).read_bytes()
        got = actual[name]
        print(f'{name}: same={got == expected} size={len(got)}/{len(expected)}')
        print(f'  ISO   {digest(got)}')
        print(f'  build {digest(expected)}')


if __name__ == '__main__':
    main()
