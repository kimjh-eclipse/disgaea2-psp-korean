# -*- coding: utf-8 -*-
"""Verify the opening atlas patch and prove no ISO bytes changed elsewhere."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import scriptpack


BASE = ROOT / "build_jp/D2_JP_KR_title.iso"
OUTPUT = ROOT / "build_jp/D2_JP_KR_opening.iso"
ANMPACK_LBA = 282896
ANMPACK_SIZE = 68324111
MEMBER_OFFSET = 0x1D9B800
RESOURCE_OFFSET = 0x40660
RESOURCE_SIZE = 0x20720
PIXEL_OFFSET = 0x720


def main():
    expected = (ROOT / "build_jp/opening_text_resource_kr.bin").read_bytes()
    with OUTPUT.open("rb") as stream:
        stream.seek(ANMPACK_LBA * 2048)
        pack = stream.read(ANMPACK_SIZE)
    entry = next(e for e in scriptpack.unpack(pack) if e["name"] == "anm7101.dat")
    actual = entry["data"][RESOURCE_OFFSET:RESOURCE_OFFSET + RESOURCE_SIZE]
    assert actual == expected

    allowed_start = (
        ANMPACK_LBA * 2048 + MEMBER_OFFSET + RESOURCE_OFFSET + PIXEL_OFFSET
    )
    allowed_end = allowed_start + 512 * 512 // 2
    assert BASE.stat().st_size == OUTPUT.stat().st_size
    changed = 0
    outside = 0
    first = None
    last = None
    position = 0
    with BASE.open("rb") as before, OUTPUT.open("rb") as after:
        while True:
            a = before.read(1 << 20)
            b = after.read(1 << 20)
            if not a:
                break
            if a == b:
                position += len(a)
                continue
            for i, (x, y) in enumerate(zip(a, b)):
                if x == y:
                    continue
                absolute = position + i
                changed += 1
                first = absolute if first is None else first
                last = absolute
                if not (allowed_start <= absolute < allowed_end):
                    outside += 1
            position += len(a)
    assert changed > 0
    assert outside == 0
    print("resource exact: OK")
    print(f"changed bytes: {changed:,}")
    print(f"changed range: {first:#x}..{last + 1:#x}")
    print(f"allowed range: {allowed_start:#x}..{allowed_end:#x}")
    print("outside changes: 0")


if __name__ == "__main__":
    main()
