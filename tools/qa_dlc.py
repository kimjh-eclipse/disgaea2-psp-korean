# -*- coding: utf-8 -*-
"""DLC 번역 TSV의 제어문자·인코딩·고정 필드 예산을 검사한다."""
import csv
import pathlib
import sys
from collections import Counter

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import krtext


def has_japanese(text):
    return any('\u3040' <= c <= '\u30ff' or '\u3400' <= c <= '\u9fff' for c in text)


def main(path=None):
    path = pathlib.Path(path) if path else ROOT / 'work' / 'dlc_translated_nllb.tsv'
    with path.open(encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.DictReader(handle, delimiter='\t'))
    problems = Counter()
    details = []
    for row in rows:
        jp, ko = row['jp'], row['ko'].strip()
        reason = []
        if not ko:
            reason.append('빈 번역')
        if has_japanese(ko):
            reason.append('일본어 잔존')
        if jp.count('￥') != ko.count('￥'):
            reason.append('￥ 개수 변경')
        if jp == ko:
            reason.append('원문 동일')
        invalid = krtext.validate(ko)
        if invalid:
            reason.append('인코딩 불가:' + ''.join(invalid))
        length = len(krtext.encode(ko)) if not invalid else -1
        if row['capacity'] and length > int(row['capacity']):
            reason.append(f"용량 초과:{length}>{row['capacity']}")
        for item in reason:
            problems[item.split(':')[0]] += 1
        if reason:
            details.append((row, length, ', '.join(reason)))

    print(f'{path}: {len(rows):,}건')
    print('문제:', dict(problems))
    for row, length, reason in details[:120]:
        print(f"[{row['source']}] cap={row['capacity'] or '-'} len={length} {reason}")
        print('  JP:', row['jp'])
        print('  KO:', row['ko'])

    print('\n고정 필드 전체:')
    for row in rows:
        if not row['capacity']:
            continue
        invalid = krtext.validate(row['ko'])
        length = len(krtext.encode(row['ko'])) if not invalid else -1
        print(f"{row['source']:12s} cap={row['capacity']:>2s} len={length:>2d} | {row['jp']} => {row['ko']}")


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else None)
