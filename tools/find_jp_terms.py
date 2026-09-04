# -*- coding: utf-8 -*-
"""추출된 일본판 데이터 전체에서 CP932 문자열 위치를 찾는다."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    terms = sys.argv[1:]
    if not terms:
        raise SystemExit('검색할 일본어 문자열을 지정하십시오.')
    files = [p for p in (ROOT / 'jp').rglob('*') if p.is_file() and p.suffix.lower() not in {'.png', '.txt'}]
    for term in terms:
        needle = term.encode('cp932')
        print(f'\n[{term}]')
        total = 0
        for path in files:
            data = path.read_bytes()
            start = 0
            hits = []
            while True:
                at = data.find(needle, start)
                if at < 0:
                    break
                hits.append(at)
                start = at + 1
            if hits:
                total += len(hits)
                print(f'  {path.relative_to(ROOT)}: {len(hits)} {" ".join(f"0x{x:X}" for x in hits[:16])}')
        print(f'  total={total}')


if __name__ == '__main__':
    main()
