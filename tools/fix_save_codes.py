# -*- coding: utf-8 -*-
"""세이브에 박힌 구(v20260830) 한글 코드를 현재 코드표로 바꾼다.

■ 왜 필요한가

디스가이아는 소지품·창고 아이템의 **이름 문자열을 세이브에 그대로 저장**한다.
v20260830 은 폰트 코드 위치가 자동 재배치된 빌드였고(HANDOFF §37), 그때 얻은
아이템은 그 시점 코드 바이트로 세이브에 박혔다. v20260831 에서 코드 위치를
되돌렸으므로 그 바이트가 엉뚱한 글자로 그려진다.

    화면: 젓례읖 맞토   실제: 정령의 망토
    화면: 칭타나        실제: 카타나

ISO·DLC 는 정상이다(전수 확인). 새로 얻는 아이템도 정상이다. 이 도구는 이미
세이브에 박힌 옛 바이트만 현재 바이트로 바꾼다.

■ 대상은 **평문** 세이브다

PSP 세이브는 기본적으로 암호화(KIRK)되어 있어 그대로는 고칠 수 없다.
PPSSPP 설정에서 `EncryptSave` 를 끄고 게임에서 새 슬롯에 저장하면 평문
DATA.BIN 이 나온다. 그 파일을 이 도구로 고친 뒤 다시 불러오면 된다.
암호화된 파일을 주면 거부한다(엔트로피로 판별).

■ 안전장치

- 원본은 절대 덮어쓰지 않는다. `<파일>.codefix` 로 새로 쓴다(--in-place 시 .bak 생성).
- 길이가 변하지 않는 치환만 한다(한글 1자 = 2바이트 고정).
- 구 코드와 현재 코드가 같은 글자는 건드리지 않는다.
- 바꾼 자리 수와 예시를 반드시 출력한다. --dry-run 으로 먼저 확인할 것.

사용:
    python tools/fix_save_codes.py <DATA.BIN> --dry-run
    python tools/fix_save_codes.py <DATA.BIN>              # <파일>.codefix 생성
    python tools/fix_save_codes.py <DATA.BIN> --in-place   # .bak 남기고 제자리
"""
import argparse
import collections
import glob
import importlib.util
import io
import os
import shutil
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
sys.path.insert(0, HERE)

import hangul_rank
from krfont import HANGUL_LIMIT, n_to_code


def used_syllables():
    """번역문에 실제로 쓰인 한글 — 0830 자동 선정 재현에 필요."""
    out = set()
    for n, path in enumerate(sorted(glob.glob('work/tr_*.py'))):
        spec = importlib.util.spec_from_file_location('u%d' % n, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for v in getattr(mod, 'T', {}).values():
            if isinstance(v, str):
                out |= {c for c in v if 0xAC00 <= ord(c) <= 0xD7A3}
    return out


def old_table():
    """v20260830 코드표: 빈도 기반 자동 선정(코드북 고정 전 로직)."""
    chars = hangul_rank.pick(HANGUL_LIMIT, must=used_syllables())
    return {ch: bytes(n_to_code(i)) for i, ch in enumerate(chars)}


def new_table():
    """현재 코드표: build_jp/hangul_codes.tsv"""
    t = {}
    path = 'build_jp/hangul_codes.tsv'
    if not os.path.exists(path):
        raise SystemExit('build_jp/hangul_codes.tsv 가 없다 — bake_font 를 먼저 돌려라')
    for line in open(path, encoding='utf-8').read().splitlines()[1:]:
        ch, c1, c2, i, g = line.split('\t')
        t[ch] = bytes([int(c1, 16), int(c2, 16)])
    return t


def looks_encrypted(data):
    """암호화된 세이브면 True. 바이트 분포가 균일하고 0x00 이 거의 없다."""
    if not data:
        return False
    c = collections.Counter(data)
    zero_ratio = c[0] / len(data)
    distinct = len(c)
    # 평문 세이브는 0x00 패딩이 많다(보통 10% 이상). 암호문은 1% 미만.
    return zero_ratio < 0.03 and distinct > 250


def build_map():
    """구 코드 -> 새 코드 (다른 것만). 2바이트 고정."""
    old, new = old_table(), new_table()
    m = {}
    for ch, ob in old.items():
        nb = new.get(ch)
        if nb is None or nb == ob:
            continue
        if len(ob) != 2 or len(nb) != 2:
            continue
        m[ob] = (nb, ch)
    return m


def convert(data, cmap, lead_lo=0xF0, lead_hi=0xFC):
    """문자 **경계를 복원한 뒤** 치환한다.

    ★ 처음엔 바이트를 1칸씩 밀며 짝을 맞춰봤는데, 인접한 두 글자에 걸친
      바이트쌍이 우연히 다른 코드와 일치해 **엉뚱한 글자로 바꿔버렸다**
      (포스 스태프 -> 포빵 스태프, 글러브 -> 글독브). 합성 세이브 검증에서 잡았다.

      그래서 한글 코드의 **선행바이트 구간(0xF0~0xFC)** 을 이용해 문자열의
      시작점을 잡고, 그 안에서만 2바이트씩 정렬해 나아간다. 선행바이트가
      아닌 값을 만나면 1바이트 문자(ASCII 등)로 보고 정렬을 유지한다.
    """
    out = bytearray(data)
    hits = collections.Counter()
    skipped = 0
    n = len(out)
    i = 0
    while i < n:
        b = out[i]
        if lead_lo <= b <= lead_hi and i + 1 < n:
            pair = bytes(out[i:i + 2])
            rep = cmap.get(pair)
            if rep is not None:
                out[i:i + 2] = rep[0]
                hits[rep[1]] += 1
            else:
                skipped += 1
            i += 2                      # 한글 1자 = 항상 2바이트
        else:
            i += 1                      # 1바이트 문자 / 바이너리
    return bytes(out), hits, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('target', help='평문 DATA.BIN 경로')
    ap.add_argument('--dry-run', action='store_true', help='쓰지 않고 결과만 보고')
    ap.add_argument('--in-place', action='store_true', help='.bak 남기고 제자리 수정')
    ap.add_argument('--force', action='store_true', help='암호화 판정을 무시')
    a = ap.parse_args()

    data = open(a.target, 'rb').read()
    print(f'대상: {a.target}  {len(data):,}B')

    if looks_encrypted(data) and not a.force:
        raise SystemExit(
            '★ 암호화된 세이브로 보인다 — 이 도구로는 고칠 수 없다.\n'
            '   PPSSPP 설정에서 EncryptSave 를 끄고 게임에서 새 슬롯에 저장한 뒤,\n'
            '   그 평문 DATA.BIN 을 지정하라. (확신하면 --force)')

    cmap = build_map()
    print(f'구 코드 -> 현재 코드 매핑: {len(cmap)}자리')

    fixed, hits, skipped = convert(data, cmap)
    total = sum(hits.values())
    print(f'치환한 글자: {total}자 (현재 코드 그대로여서 건너뜀: {skipped}자)')
    if len(fixed) != len(data):
        raise SystemExit('★ 길이가 변했다 — 중단')

    if total:
        print('가장 많이 바뀐 글자 20개:')
        for ch, c in hits.most_common(20):
            print(f'   {ch} x{c}')
    else:
        print('바꿀 것이 없다 — 이미 현재 코드이거나 대상이 아니다.')

    if a.dry_run:
        print('\n--dry-run 이므로 아무것도 쓰지 않았다.')
        return 0
    if not total:
        return 0

    if a.in_place:
        bak = a.target + '.bak'
        if not os.path.exists(bak):
            shutil.copyfile(a.target, bak)
            print(f'백업: {bak}')
        open(a.target, 'wb').write(fixed)
        print(f'제자리 수정 완료: {a.target}')
    else:
        out = a.target + '.codefix'
        open(out, 'wb').write(fixed)
        print(f'생성: {out}  (원본은 그대로)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
