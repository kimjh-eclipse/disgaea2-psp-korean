# -*- coding: utf-8 -*-
"""세이브 글자 복구용 코드 매핑 파일 생성 — 패처가 읽는 sidecar.

v20260830 코드표 -> 현재 코드표 매핑을 담는다. 아이템 이름이 세이브에
문자열로 저장되므로, 그때 얻은 아이템은 코드표를 되돌린 뒤 깨져 보인다.

포맷 (D2_SAVE_codemap.bin)
    +0x00  char[9]  "D2SAVMAP1"
    +0x09  u32      version (1)
    +0x0D  u16      titleLen + utf8 title
    +...   u32      pairCount
    +...   pairCount x { u8 oldC1, u8 oldC2, u8 newC1, u8 newC2 }

사용:
    python tools/make_save_codemap.py
"""
import glob
import importlib.util
import io
import os
import struct
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
sys.path.insert(0, HERE)

import hangul_rank
from krfont import HANGUL_LIMIT, n_to_code

MAGIC = b'D2SAVMAP1'
VERSION = 1
TITLE = '마계전기 디스가이아 2 PORTABLE 세이브 글자 복구'
OUT = 'iso_quickpatch/D2_SAVE_codemap.bin'


def used_syllables():
    out = set()
    for n, path in enumerate(sorted(glob.glob('work/tr_*.py'))):
        spec = importlib.util.spec_from_file_location('u%d' % n, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for v in getattr(mod, 'T', {}).values():
            if isinstance(v, str):
                out |= {c for c in v if 0xAC00 <= ord(c) <= 0xD7A3}
    return out


def main():
    chars = hangul_rank.pick(HANGUL_LIMIT, must=used_syllables())
    old = {ch: bytes(n_to_code(i)) for i, ch in enumerate(chars)}

    new = {}
    for line in open('build_jp/hangul_codes.tsv', encoding='utf-8').read().splitlines()[1:]:
        ch, c1, c2, i, g = line.split('\t')
        new[ch] = bytes([int(c1, 16), int(c2, 16)])

    pairs = []
    for ch, ob in old.items():
        nb = new.get(ch)
        if nb is None or nb == ob or len(ob) != 2 or len(nb) != 2:
            continue
        pairs.append((ob, nb, ch))

    # 구 코드가 겹치면 안 된다(같은 바이트가 두 글자로 매핑되면 판단 불가)
    seen = {}
    for ob, nb, ch in pairs:
        if ob in seen and seen[ob] != nb:
            raise SystemExit(f'★ 구 코드 {ob.hex()} 가 두 글자로 충돌: {seen[ob].hex()} / {nb.hex()}')
        seen[ob] = nb

    pairs.sort(key=lambda x: x[0])
    title = TITLE.encode('utf-8')
    buf = bytearray()
    buf += MAGIC
    buf += struct.pack('<I', VERSION)
    buf += struct.pack('<H', len(title)) + title
    buf += struct.pack('<I', len(pairs))
    for ob, nb, ch in pairs:
        buf += bytes([ob[0], ob[1], nb[0], nb[1]])

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, 'wb').write(bytes(buf))
    print(f'매핑 {len(pairs)}쌍')
    print(f'생성: {OUT}  {len(buf):,}B')
    import hashlib
    print(f'SHA256 {hashlib.sha256(bytes(buf)).hexdigest().upper()}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
