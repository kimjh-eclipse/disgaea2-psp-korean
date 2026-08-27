# -*- coding: utf-8 -*-
"""오프닝 나레이션 아틀라스 패치 검증 — 지정 픽셀 영역 밖은 변하지 않았음을 증명.

★ 예전에는 중간 ISO 두 개(D2_JP_KR_title.iso -> D2_JP_KR_opening.iso)를
  바이트 비교했다. 지금은 빌드가 build_jp/D2_JP_KR.iso 를 제자리에서 고치므로
  "패치 전 ISO" 가 존재하지 않는다. 그래서 비교 기준을 **원본 ISO 안의 같은
  멤버**로 바꿨다 — 중간 ISO 없이도 같은 것을 증명한다.

검사 내용
  1. 현재 ISO 의 anm7101.dat 안 나레이션 리소스가 build_jp 산출물과 바이트 일치
  2. 원본 ISO 의 anm7101.dat 과 비교해, 달라진 바이트가 **아틀라스 픽셀 영역
     안에만** 있는지 (팔레트·헤더·다른 리소스 무손상)

사용:
    python tools/verify_opening.py
    D2_ISO_DST=build_jp/D2_JP_KR.iso python tools/verify_opening.py
"""
from pathlib import Path
import glob
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import scriptpack


CURRENT = ROOT / os.environ.get("D2_ISO_DST", "build_jp/D2_JP_KR.iso")
ANMPACK_LBA = 282896
ANMPACK_SIZE = 68324111
MEMBER = "anm7101.dat"
RESOURCE_OFFSET = 0x40660
RESOURCE_SIZE = 0x20720
PIXEL_OFFSET = 0x720
PIXEL_SIZE = 512 * 512 // 2


def source_iso():
    hits = sorted(glob.glob(str(ROOT.parent / "Makai*Disgaea*.iso")))
    if not hits:
        raise SystemExit("원본 ISO 를 찾을 수 없습니다 (../Makai*Disgaea*.iso)")
    return Path(hits[0])


def member(iso_path):
    with iso_path.open("rb") as stream:
        stream.seek(ANMPACK_LBA * 2048)
        pack = stream.read(ANMPACK_SIZE)
    return next(e["data"] for e in scriptpack.unpack(pack) if e["name"] == MEMBER)


def main():
    cur = member(CURRENT)
    orig = member(source_iso())
    if len(cur) != len(orig):
        raise SystemExit(f"{MEMBER} 크기가 다르다: {len(orig)} -> {len(cur)}")

    # 1) 리소스가 산출물과 일치
    expected = (ROOT / "build_jp/opening_text_resource_kr.bin").read_bytes()
    actual = cur[RESOURCE_OFFSET:RESOURCE_OFFSET + RESOURCE_SIZE]
    if actual != expected:
        raise SystemExit("나레이션 리소스가 build_jp 산출물과 다르다")
    print("리소스 일치: OK")

    # 2) 달라진 바이트가 픽셀 영역 안에만 있는지
    lo = RESOURCE_OFFSET + PIXEL_OFFSET
    hi = lo + PIXEL_SIZE
    changed = outside = 0
    first = last = None
    for i, (a, b) in enumerate(zip(orig, cur)):
        if a == b:
            continue
        changed += 1
        first = i if first is None else first
        last = i
        if not (lo <= i < hi):
            outside += 1

    print(f"변경 바이트: {changed:,}")
    if changed:
        print(f"변경 범위  : {first:#x}..{last + 1:#x}")
    print(f"허용 범위  : {lo:#x}..{hi:#x}")
    print(f"허용 밖 변경: {outside}")
    if changed == 0:
        raise SystemExit("★ 나레이션이 적용되지 않았다 (변경 0바이트)")
    if outside:
        raise SystemExit(f"★ 허용 범위 밖 {outside}바이트가 변경됐다")
    print("\n=== 오프닝 나레이션 검증 OK ===")


if __name__ == "__main__":
    main()
