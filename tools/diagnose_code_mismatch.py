# -*- coding: utf-8 -*-
"""문자열이 현재/구 자동선정 코드 중 어느 쪽으로 저장됐는지 주요 컨테이너에서 찾는다."""
import glob
import importlib.util
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
os.chdir(ROOT)

import hangul_rank
from krfont import HANGUL_LIMIT, n_to_code
from krtext import encode as stable_encode
from nislzs import decompress
from verify_iso import read_iso_file


def used():
    out = set()
    for n, path in enumerate(sorted(glob.glob('work/tr_*.py'))):
        spec = importlib.util.spec_from_file_location('diag_' + str(n), path)
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


def decode_with(chars, raw):
    table = {bytes(n_to_code(i)): ch for i, ch in enumerate(chars)}
    out = []
    i = 0
    while i < len(raw):
        if raw[i] < 0x80:
            out.append(chr(raw[i])); i += 1
        else:
            out.append(table.get(raw[i:i + 2], '·')); i += 2
    return ''.join(out)


def main():
    texts = sys.argv[1:] or [
        '연무의 동굴 게이트 열기',
        '연무의 동굴에 갈 수 있게 됩니다',
    ]
    iso = Path('build_jp/D2_JP_KR.iso')
    with iso.open('rb') as f:
        start = decompress(read_iso_file(f, 25, b'START_JP.LZS')[0])
        vm = decompress(read_iso_file(f, 25, b'START_VM_JP.LZS')[0])
        scriptpack = read_iso_file(f, 25, b'SCRIPTPACK.DAT')[0]
        image = iso.read_bytes()
    containers = {
        'START_JP(raw)': start,
        'START_VM(raw)': vm,
        'SCRIPTPACK': scriptpack,
        'ISO(raw only)': image,
    }
    unstable_chars = hangul_rank.pick(HANGUL_LIMIT, must=used())
    for text in texts:
        print('\n' + text)
        variants = {
            'stable': stable_encode(text),
            'unstable-v20260830': encoder(unstable_chars, text),
        }
        stable_chars = [line.split('\t')[1] for line in Path('work/hangul_codebook_v1.tsv').read_text(encoding='utf-8').splitlines()[1:]]
        print('  stable text + unstable font:', decode_with(unstable_chars, variants['stable']))
        print('  unstable text + stable font:', decode_with(stable_chars, variants['unstable-v20260830']))
        print('  encodings equal:', variants['stable'] == variants['unstable-v20260830'])
        for label, data in variants.items():
            found = []
            for cname, blob in containers.items():
                at = blob.find(data)
                if at >= 0:
                    found.append(f'{cname}@0x{at:X}')
            print(f'  {label:20s}: ' + (', '.join(found) if found else '없음'))


if __name__ == '__main__':
    main()
