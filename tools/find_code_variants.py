# -*- coding: utf-8 -*-
"""PPSSPP 메모리스틱 파일에서 현재/20260830 코드값 문자열을 찾는다."""
import base64
import glob
import importlib.util
import os
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
os.chdir(ROOT)

import hangul_rank
from krfont import HANGUL_LIMIT, n_to_code
from krtext import encode as stable_encode


def used():
    out = set()
    for n, path in enumerate(sorted(glob.glob('work/tr_*.py'))):
        spec = importlib.util.spec_from_file_location('filediag_' + str(n), path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for value in mod.T.values():
            out |= {c for c in value if 0xAC00 <= ord(c) <= 0xD7A3}
    return out


def encoder(chars, text):
    table = {ch: bytes(n_to_code(i)) for i, ch in enumerate(chars)}
    out = bytearray()
    for ch in text:
        if ch in table:
            out += table[ch]
        elif 0x20 <= ord(ch) < 0x7F:
            out.append(ord(ch))
        else:
            out += ch.encode('cp932')
    return bytes(out)


def scan_blob(label, data, variants):
    for variant, needle in variants.items():
        start = 0
        while True:
            at = data.find(needle, start)
            if at < 0:
                break
            print(f'{variant}\t{label}\t0x{at:X}')
            start = at + 1


def main():
    text = ' '.join(sys.argv[1:]) or '연무의 동굴 게이트 열기'
    unstable = hangul_rank.pick(HANGUL_LIMIT, must=used())
    variants = {
        'stable': stable_encode(text),
        'unstable-v20260830': encoder(unstable, text),
    }
    roots = [
        Path.home() / 'Documents' / 'PPSSPP' / 'PSP' / 'SAVEDATA',
        Path.home() / 'Documents' / 'PPSSPP' / 'PSP' / 'GAME' / 'ULJS00183',
    ]
    count = 0
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob('*'):
            if not path.is_file():
                continue
            try:
                data = path.read_bytes()
            except OSError:
                continue
            scan_blob(str(path), data, variants)
            count += 1
            if zipfile.is_zipfile(path):
                with zipfile.ZipFile(path) as zf:
                    for name in zf.namelist():
                        scan_blob(f'{path}!{name}', zf.read(name), variants)
    print(f'scanned_files={count}')


if __name__ == '__main__':
    main()
