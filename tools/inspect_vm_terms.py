# -*- coding: utf-8 -*-
"""START_VM 원본/빌드에서 화면에 보인 일본어 조각의 위치를 찾는다."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

from nislzs import decompress


def context(data, at, needle):
    lo = max(0, data.rfind(b'\0', max(0, at - 256), at) + 1)
    hi = data.find(b'\0', at + len(needle), min(len(data), at + len(needle) + 256))
    if hi < 0:
        hi = min(len(data), at + len(needle) + 128)
    raw = data[lo:hi]
    try:
        return raw.decode('cp932')
    except UnicodeDecodeError:
        return raw.hex(' ')


def main():
    terms = sys.argv[1:] or [
        'どうしようもないクズ', 'おちこぼれ', 'はばたく', 'オーク',
        'すぎの', 'ダメージ', 'として', '認められている', 'りもいるよ', 'めて',
        '病院部屋', 'プチオーク部屋', 'オーク界賊団アジト',
        'ゴースト変化', '虹レンジャー変化',
    ]
    blobs = {
        'original': (ROOT / 'jp' / 'START_VM_JP.bin').read_bytes(),
        'built': decompress((ROOT / 'build_jp' / 'START_VM_JP.LZS').read_bytes()),
    }
    for term in terms:
        needle = term.encode('cp932')
        print(f'\n[{term}]')
        for label, data in blobs.items():
            hits = []
            start = 0
            while True:
                at = data.find(needle, start)
                if at < 0:
                    break
                hits.append(at)
                start = at + 1
            print(f'  {label}: {len(hits)} {" ".join(f"0x{x:X}" for x in hits[:12])}')
            for at in hits[:3]:
                print(f'    {context(data, at, needle)!r}')


if __name__ == '__main__':
    main()
