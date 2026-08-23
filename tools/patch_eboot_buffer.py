# -*- coding: utf-8 -*-
"""Patch the JP decrypted EBOOT ELF talk buffer from 0x318F8 to 0x36000."""

import argparse
import hashlib
import struct
from pathlib import Path


LOAD_ADDR = 0x08804000
PATCHES = {
    0x0887A0BC: (0x344718F8, 0x34476000),
    0x08892A80: (0x344518F8, 0x34456000),
    0x08928F80: (0x344718F8, 0x34476000),
    0x0892A35C: (0x344718F8, 0x34476000),
    0x0892A39C: (0x344718F8, 0x34476000),
    0x0892A640: (0x344718F8, 0x34476000),
    0x0892A680: (0x344718F8, 0x34476000),
    0x0892B57C: (0x344718F8, 0x34476000),
    0x0892B5BC: (0x344718F8, 0x34476000),
}


def load_segment(data):
    if data[:4] != b"\x7fELF":
        raise ValueError("input is not an ELF")
    if data[4:7] != b"\x01\x01\x01":
        raise ValueError("expected 32-bit little-endian ELF")
    if struct.unpack_from("<H", data, 18)[0] != 8:
        raise ValueError("expected MIPS ELF")

    phoff = struct.unpack_from("<I", data, 28)[0]
    phentsize, phnum = struct.unpack_from("<HH", data, 42)
    for i in range(phnum):
        off = phoff + i * phentsize
        p_type, p_offset, p_vaddr, _, p_filesz = struct.unpack_from("<IIIII", data, off)
        if p_type == 1 and p_vaddr <= LOAD_ADDR < p_vaddr + p_filesz:
            return p_offset, p_vaddr, p_filesz
    raise ValueError("load segment containing 0x08804000 not found")


def patch_elf(src, dst):
    data = bytearray(Path(src).read_bytes())
    seg_off, seg_addr, seg_size = load_segment(data)

    for address, (expected, replacement) in PATCHES.items():
        rel = address - seg_addr
        if rel < 0 or rel + 4 > seg_size:
            raise ValueError(f"patch address outside load segment: {address:#010x}")
        file_off = seg_off + rel
        actual = struct.unpack_from("<I", data, file_off)[0]
        if actual != expected:
            raise ValueError(
                f"unexpected word at {address:#010x} / file {file_off:#x}: "
                f"{actual:#010x} != {expected:#010x}"
            )
        struct.pack_into("<I", data, file_off, replacement)
        print(f"{address:#010x}  file {file_off:#08x}  {expected:#010x} -> {replacement:#010x}")

    Path(dst).write_bytes(data)
    print(f"wrote {dst} ({len(data)} bytes)")
    print(f"sha256 {hashlib.sha256(data).hexdigest()}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    args = ap.parse_args()
    patch_elf(args.src, args.dst)


if __name__ == "__main__":
    main()
