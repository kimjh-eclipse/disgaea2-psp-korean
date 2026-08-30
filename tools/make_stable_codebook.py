# -*- coding: utf-8 -*-
"""v20260829 코드 위치를 보존한 고정 한글 코드북을 한 번 생성한다.

일반 빌드에서는 실행하지 않는다. 결과인 work/hangul_codebook_v1.tsv를 소스로
보관하고 bake_font.py가 그대로 읽는다.
"""
import glob
import hashlib
import importlib.util
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
os.chdir(ROOT)
import hangul_rank

LIMIT = 1625
LEGACY_SHA = '5f4417c3909cbcd95d9c3b1afb1b4cd68ea392ea46f20b1cf611eb731ef64a32'
STABLE_SHA = 'c187262fab762e291da0e701f7da6ed402bd36a3cca3af401530613dd9c7f2c5'
EXPECTED_DROP = list('먁뽄셥쌈쏠켤퓌')
EXPECTED_ADD = list('댓멎뽑쏟쾅큠핏')
OUTPUT = Path('work/hangul_codebook_v1.tsv')


def used(paths):
    out = set()
    for n, path in enumerate(paths):
        spec = importlib.util.spec_from_file_location('codebook_' + str(n), path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for value in mod.T.values():
            out |= {c for c in value if 0xAC00 <= ord(c) <= 0xD7A3}
    return out


def digest(chars):
    return hashlib.sha256(''.join(chars).encode('utf-8')).hexdigest()


def main():
    paths = sorted(glob.glob('work/tr_*.py'))
    legacy_paths = [p for p in paths if not os.path.basename(p).startswith('tr_dlc')]
    legacy = hangul_rank.pick(LIMIT, must=used(legacy_paths))
    assert digest(legacy) == LEGACY_SHA, 'DLC 이전 코드표 재현값이 달라짐'

    must = used(paths)
    fresh = hangul_rank.pick(LIMIT, must=must)
    drop = [c for c in legacy if c not in fresh]
    add = [c for c in fresh if c not in legacy]
    assert drop == EXPECTED_DROP, (drop, EXPECTED_DROP)
    assert add == EXPECTED_ADD, (add, EXPECTED_ADD)

    stable = legacy[:]
    replacements = []
    for old, new in zip(drop, add):
        index = stable.index(old)
        stable[index] = new
        replacements.append((index, old, new))
    assert len(stable) == len(set(stable)) == LIMIT
    assert must <= set(stable)
    assert digest(stable) == STABLE_SHA

    with OUTPUT.open('w', encoding='utf-8', newline='\n') as f:
        f.write('index\tchar\tlegacy_char\n')
        old_at = {i: old for i, old, _new in replacements}
        for i, ch in enumerate(stable):
            f.write(f'{i}\t{ch}\t{old_at.get(i, ch)}\n')
    print(f'{OUTPUT}: {LIMIT}자, SHA-256 {STABLE_SHA}')
    for index, old, new in replacements:
        print(f'  코드 위치 {index:4d}: {old} -> {new}')


if __name__ == '__main__':
    main()
