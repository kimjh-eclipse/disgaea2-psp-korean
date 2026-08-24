# -*- coding: utf-8 -*-
"""ISO 루트 `/PSP_GAME/USRDIR/DUNGEON.DAT` (스테이지·지명 이름 165개) 한글화.

스테이지 선택 화면에 나오는 이름들이다. 내가 패치 대상으로 잡지 않았던 루트 파일로,
ISO 전수 탐색(`tools/find_string.py`)으로 찾았다.

★ 주의: 한때 이 파일을 **지명 간판(`ホルルト村`)의 출처**로 단정했는데 **틀렸다.**
  간판은 이미지이고 출처는 `ANMPACK/anm7151.dat` 의 256x512 아틀라스다
  (`tools/build_signatlas.py`). 같은 문자열이 여러 파일에 있으므로,
  "문자열을 찾았다" 는 "그 화면의 출처다" 를 뜻하지 않는다. GE 디버거로 확인할 것.

포맷 (`recdat.ROOT_SPEC`)
    +0x00  u32 count(165) x2
    +0x08  record[165] x 0x50
             +0x00  이름   (진짜 폭 22B / 가용 21B)
             +0x16  u16 스테이지 ID + 파라미터   ← 바이너리, 절대 건드리지 않는다

번역은 새로 만들지 않는다. 97개 고유명이 **전부 기존 코퍼스(`work/tr_*.py`)에
이미 있고** 예산 안에 들어간다 — 같은 문자열이 `charhelp.dat` 에도 있었기 때문이다.
충돌(같은 원문에 다른 번역) 0건을 확인했다.

사용:
    python tools/build_dungeon.py           # build_jp/DUNGEON_root.DAT 생성
    python tools/build_dungeon.py --iso     # ISO 주입까지
"""
import glob
import importlib.util
import io
import os
import sys

if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
sys.path.insert(0, HERE)
import isopatch
import krtext
import recdat

NAME = 'DUNGEON.DAT'
SRC = 'jp/DUNGEON.DAT'
DST = 'build_jp/DUNGEON_root.DAT'   # ★ START 멤버 dungeon.dat 과 대소문자 충돌 회피
ISO = os.environ.get('D2_ISO_DST', 'build_jp/D2_JP_KR.iso')
USRDIR_LBA = 25          # CHAR.DAT 와 같은 디렉터리


def corpus():
    """work/tr_*.py 전체를 합친 {일본어: 한글}"""
    T = {}
    for p in sorted(glob.glob('work/tr_*.py')):
        sp = importlib.util.spec_from_file_location('b', p)
        m = importlib.util.module_from_spec(sp)
        try:
            sp.loader.exec_module(m)
        except Exception:
            continue
        for k, v in getattr(m, 'T', {}).items():
            if isinstance(k, str):
                T.setdefault(k, v)
    return T


def main(make_iso=False):
    data = open(SRC, 'rb').read()
    T = corpus()
    edits, miss, over = {}, [], []
    for i, off, w, raw in recdat.items(NAME, data):
        try:
            jp = raw.decode('cp932')
        except UnicodeDecodeError:
            continue
        if not any(ord(c) > 0x7f for c in jp):
            continue
        ko = T.get(jp)
        if ko is None:
            miss.append(jp)
            continue
        bad = krtext.validate(ko)
        if bad:
            raise SystemExit(f'인코딩 불가 {jp} -> {ko}: {"".join(bad)}')
        b = krtext.encode(ko)
        cap = recdat.capacity(NAME, data, i, off)
        if len(b) > cap:
            over.append((jp, ko, len(b), cap))
            continue
        edits[(i, off)] = b
    if over:
        print(f'!! 예산 초과 {len(over)}건')
        for a, b, c, d in over:
            print(f'   {a} -> {b} ({c}B > {d}B)')
        raise SystemExit(1)
    new = recdat.put(NAME, data, edits)
    assert len(new) == len(data), '크기 변경'
    open(DST, 'wb').write(new)
    print(f'{NAME}: {len(edits)}회 적용 / 미번역 {len(set(miss))}종')
    for x in sorted(set(miss))[:10]:
        print(f'   미번역: {x}')

    # 문자열 영역 밖 무손상 (아이템 DB 사고 재발 방지)
    hdr, rs, flds = recdat.spec(NAME)
    n = recdat.count(data)
    touched = bytearray(len(data))
    for i in range(n):
        for off, w in flds:
            cap = recdat.capacity(NAME, data, i, off)
            base = hdr + i * rs + off
            for k in range(base, base + cap + 1):
                touched[k] = 1
    hurt = sum(1 for k in range(len(data)) if data[k] != new[k] and not touched[k])
    print(f'문자열 영역 밖 손상: {hurt}바이트 ' + ('OK' if not hurt else '★★'))
    if hurt:
        raise SystemExit(1)

    if make_iso:
        r = isopatch.replace(ISO, USRDIR_LBA, NAME.encode('latin1'), new)
        print(f'ISO 갱신: {NAME} {r}')
    return 0


if __name__ == '__main__':
    sys.exit(main('--iso' in sys.argv))
