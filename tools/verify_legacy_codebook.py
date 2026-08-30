# -*- coding: utf-8 -*-
"""v20260829 ISO의 실제 폰트와 DLC 이전 코드표 재현 결과를 비교한다."""
import glob
import hashlib
import importlib.util
import os
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
os.chdir(ROOT)

import hangul_rank
from nislzs import decompress
from krfont import (load_page, save_page, wipe, bake, build_tables,
                    collect_moves, collect_kana, collect_fullwidth_alnum,
                    move_glyphs, move_glyphs_to, rebake_symbols, rebake_cell,
                    GID_BASE, MOVE_BASE, FULLWIDTH_ALNUM_BASE, HANGUL_LIMIT,
                    FONT_PATH, FONT_INDEX, FONT_SIZE)
from PIL import ImageFont


def sha(data):
    return hashlib.sha256(data).hexdigest().upper()


def used_without_dlc():
    out = set()
    paths = sorted(glob.glob('work/tr_*.py'))
    paths = [p for p in paths if not os.path.basename(p).startswith('tr_dlc')]
    for n, path in enumerate(paths):
        spec = importlib.util.spec_from_file_location('legacy_' + str(n), path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for value in mod.T.values():
            out |= {c for c in value if 0xAC00 <= ord(c) <= 0xD7A3}
    return out


def read_iso_member(iso_path, wanted):
    with open(iso_path, 'rb') as f:
        f.seek(25 * 2048)
        directory = f.read(2048)
        pos = directory.find(b'START_JP.LZS')
        rec = pos - 33
        lba = struct.unpack_from('<I', directory, rec + 2)[0]
        size = struct.unpack_from('<I', directory, rec + 10)[0]
        f.seek(lba * 2048)
        raw = decompress(f.read(size))
    count = struct.unpack_from('<I', raw, 0)[0]
    entries = []
    for i in range(count):
        off = 0x10 + i * 0x20
        start = struct.unpack_from('<I', raw, off)[0] + 0x2B0
        name = raw[off + 4:off + 0x20].split(b'\0')[0].decode('latin1')
        entries.append((start, name))
    entries.sort()
    for i, (start, name) in enumerate(entries):
        if name == wanted:
            end = entries[i + 1][0] if i + 1 < len(entries) else len(raw)
            return raw[start:end]
    raise KeyError(wanted)


def main():
    if len(sys.argv) != 2:
        raise SystemExit('사용: python tools/verify_legacy_codebook.py <v20260829 ISO>')
    iso = sys.argv[1]
    chars = hangul_rank.pick(HANGUL_LIMIT, must=used_without_dlc())

    src = [load_page('jp/start/fontB.ftd'), load_page('jp/start/FontB0000.txp')]
    dst = [load_page('jp/start/fontB.ftd'), load_page('jp/start/FontB0000.txp')]
    map_src = Path('jp/start/talk00.dat').read_bytes()
    fnt_src = Path('jp/start/fontB.fnt').read_bytes()
    preserve = collect_kana(map_src) + collect_moves(map_src)
    alnum = collect_fullwidth_alnum(map_src)
    wipe(dst, GID_BASE, 2591)
    font = ImageFont.truetype(FONT_PATH, FONT_SIZE, index=FONT_INDEX)
    bake(dst, chars, font)
    alnum_moves = move_glyphs_to(dst, src, alnum, FULLWIDTH_ALNUM_BASE)
    for c1, c2, _old, new in alnum_moves:
        rebake_cell(dst, bytes([c1, c2]).decode('cp932'), new, font)
    rebake_symbols(dst, map_src, font)
    moves = move_glyphs(dst, src, preserve)
    table, fnt, _codes = build_tables(map_src, fnt_src, chars, alnum_moves + moves)

    out = ROOT / 'build_legacy_check' / 'generated'
    out.mkdir(parents=True, exist_ok=True)
    save_page(dst[0], str(out / 'fontB.ftd'))
    save_page(dst[1], str(out / 'FontB0000.txp'))
    (out / 'talk00.dat').write_bytes(table)
    (out / 'fontB.fnt').write_bytes(fnt)

    ok = True
    for name in ('fontB.ftd', 'FontB0000.txp', 'talk00.dat', 'fontB.fnt'):
        generated = (out / name).read_bytes()
        actual = read_iso_member(iso, name)[:len(generated)]
        same = generated == actual
        print(f'{name:16s} {"OK" if same else "DIFF"}  {sha(generated)} / {sha(actual)}')
        ok &= same
    print('legacy chars', len(chars), 'unique', len(set(chars)))
    if not ok:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
