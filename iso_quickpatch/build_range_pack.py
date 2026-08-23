"""디스가이아2 PSP 제자리 ISO 구간 패치 리소스 생성.

OGMD 패처(work_ogmd/iso_quickpatch)와 같은 방식이지만 D2 는 더 단순하다 —
원본과 패치본 ISO 크기가 완전히 동일하므로(854,360,064B) ISO 안의 파일 위치를
찾을 필요 없이 **절대 오프셋 구간**만 담으면 된다.

MERGE_GAP 이내로 떨어진 변경은 하나로 합쳐 런타임 복사 횟수를 줄인다.
"""
from __future__ import annotations

import hashlib
import os
import struct
from pathlib import Path

import numpy as np

MAGIC = b"D2PSPRNG1"
VERSION = 1
MERGE_GAP = 64
CHUNK = 16 * 1024 * 1024

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUTPUT = HERE / "D2_ISO_ranges.bin"

SOURCE = ROOT.parent / "Makai Senki Disgaea 2 Portable (Japan) (PSP) (PSN).iso"
TARGET = ROOT / "build_jp" / "D2_JP_KR.iso"
TITLE = "마계전기 디스가이아 2 PORTABLE 한국어화"


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb", buffering=0) as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
    return h.hexdigest().upper()


def find_ranges(source: Path, target: Path):
    if source.stat().st_size != target.stat().st_size:
        raise ValueError(f"크기 불일치: {source.stat().st_size} / {target.stat().st_size}")
    size = source.stat().st_size
    parts = []
    off = 0
    with source.open("rb", buffering=0) as a, target.open("rb", buffering=0) as b:
        while off < size:
            old = a.read(min(CHUNK, size - off))
            new = b.read(len(old))
            d = np.flatnonzero(
                np.frombuffer(old, dtype=np.uint8) != np.frombuffer(new, dtype=np.uint8)
            )
            if d.size:
                parts.append(d.astype(np.int64) + off)
            off += len(old)
    if not parts:
        return []
    pos = np.concatenate(parts)
    cuts = np.flatnonzero(np.diff(pos) > MERGE_GAP + 1)
    starts = np.r_[0, cuts + 1]
    ends = np.r_[cuts, len(pos) - 1]
    return [(int(pos[s]), int(pos[e] - pos[s] + 1)) for s, e in zip(starts, ends)]


def main() -> None:
    src_hash = file_hash(SOURCE)
    dst_hash = file_hash(TARGET)
    print(f"원본  {SOURCE.name}\n      {SOURCE.stat().st_size:,}B  {src_hash}")
    print(f"패치본 {TARGET.name}\n      {TARGET.stat().st_size:,}B  {dst_hash}")

    ranges = find_ranges(SOURCE, TARGET)
    payload = sum(n for _, n in ranges)
    print(f"\n변경 구간 {len(ranges):,}개 / 페이로드 {payload:,}B "
          f"({100*payload/SOURCE.stat().st_size:.2f}%)")

    tmp = OUTPUT.with_suffix(OUTPUT.suffix + ".tmp")
    title = TITLE.encode("utf-8")
    with tmp.open("wb", buffering=1 << 20) as out:
        out.write(MAGIC)
        out.write(struct.pack("<I", VERSION))
        out.write(struct.pack("<H", len(title)))
        out.write(title)
        out.write(struct.pack("<Q", SOURCE.stat().st_size))
        out.write(bytes.fromhex(src_hash))
        out.write(bytes.fromhex(dst_hash))
        out.write(struct.pack("<I", len(ranges)))
        with TARGET.open("rb", buffering=0) as t:
            for off, n in ranges:
                t.seek(off)
                data = t.read(n)
                if len(data) != n:
                    raise IOError(f"짧은 읽기 @{off}")
                out.write(struct.pack("<QI", off, n))
                out.write(data)
        out.flush()
        os.fsync(out.fileno())
    tmp.replace(OUTPUT)
    print(f"\n생성: {OUTPUT.name}  {OUTPUT.stat().st_size:,}B")
    print(f"SHA256 {file_hash(OUTPUT)}")


if __name__ == "__main__":
    main()
