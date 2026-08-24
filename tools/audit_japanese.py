# -*- coding: utf-8 -*-
"""빌드된 ISO 전체에서 **아직 일본어가 남은 파일**을 찾는다.

번역률 통계는 "내가 아는 소스" 안에서만 계산되므로, 애초에 소스로 잡지 못한
파일은 통계에 나타나지 않는다. 실제로 지명 간판(`ホルルト村`)의 출처인 루트
`/PSP_GAME/USRDIR/DUNGEON.DAT` 을 이 방식으로 뒤늦게 찾았다.

판정: cp932 로 디코드했을 때 가나(ひらがな·カタカナ)가 들어간 문자열을 센다.
  · 가나는 우리 폰트에 보존돼 있어 **화면에 일본어로 그대로 보인다** = 확실한 미번역
  · 한자는 글리프를 지웠으므로 빈칸으로 보인다 (별도 도구 scan_kanji.py 담당)

사용:
    python tools/audit_japanese.py <ISO>
"""
import io
import os
import struct
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nislzs
from find_string import iso_files, try_lzs, try_nispack, try_start

S = 2048


def kana_strings(blob):
    """가나가 포함된 cp932 문자열을 뽑는다 -> [(offset, text)]"""
    out = []
    i = 0
    n = len(blob)
    while i < n:
        b = blob[i]
        # 문자열 시작 후보: 2바이트 문자 선행바이트
        if 0x81 <= b <= 0x9F or 0xE0 <= b <= 0xEF:
            j = i
            buf = bytearray()
            while j < n:
                c = blob[j]
                if (0x81 <= c <= 0x9F or 0xE0 <= c <= 0xEF) and j + 1 < n \
                        and 0x40 <= blob[j + 1] <= 0xFC and blob[j + 1] != 0x7F:
                    buf += blob[j:j + 2]
                    j += 2
                elif 0x20 <= c <= 0x7E:
                    buf += blob[j:j + 1]
                    j += 1
                else:
                    break
            if len(buf) >= 4:
                try:
                    t = buf.decode('cp932')
                except Exception:
                    t = None
                if t and any('぀' <= ch <= 'ヿ' for ch in t):
                    out.append((i, t))
            i = max(j, i + 1)
        else:
            i += 1
    return out


def walk(blob, where, depth, acc):
    hits = kana_strings(blob)
    if hits:
        acc.setdefault(where, []).extend(hits)
    if depth >= 3:
        return
    d = try_lzs(blob)
    base = blob
    if d is not None:
        walk(d, where + ' [LZS]', depth + 1, acc)
        base = d
    for tag, fn in (('NISPACK', try_nispack), ('START', try_start)):
        mem = fn(base)
        if mem:
            for nm, sub in mem:
                walk(sub, f'{where} [{tag}::{nm}]', depth + 1, acc)
            break


def main():
    iso = sys.argv[1]
    files = iso_files(iso)
    f = open(iso, 'rb')
    acc = {}
    for path, lba, size in files:
        if size == 0 or size > 200 * 1024 * 1024:
            continue
        f.seek(lba * S)
        walk(f.read(size), path, 0, acc)
    f.close()
    # 상위 컨테이너는 하위 멤버와 중복되므로 멤버 단위만 남긴다
    rows = sorted(acc.items(), key=lambda kv: -len(kv[1]))
    print('가나가 남은 위치 %d곳\n' % len(rows))
    print('%-56s %6s  %s' % ('위치', '건수', '예시'))
    print('-' * 110)
    for where, hits in rows[:40]:
        ex = ' / '.join(t for _, t in hits[:2])
        print('%-56s %6d  %s' % (where[:56], len(hits), ex[:44]))
    print('\n총 %d건' % sum(len(v) for v in acc.values()))


if __name__ == '__main__':
    main()
