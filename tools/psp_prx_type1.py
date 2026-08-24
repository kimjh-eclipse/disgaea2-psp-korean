#!/usr/bin/env python3
"""Re-encrypt and verify a PSP type-1 (~PSP) PRX using an original header.

This intentionally supports only the C0CB167C/type-1 case needed by the
paired Disgaea 2 EBOOT files in this work directory.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.cmac import CMAC


TAG = 0xC0CB167C
KIRK1_KEY = bytes.fromhex("98 C9 40 97 5C 1D 10 E8 7F E6 0E A3 FD 03 A8 BA")
KIRK7_KEY_5D = bytes.fromhex("11 5A 5D 20 D5 3A 8D D3 9C C5 AF 41 0F 0F 18 6F")
EBOOT2XX_WORDS = (
    0xDA8E36FA, 0x5DD97447, 0x76C19874, 0x97E57EAF, 0x1CAB09BD, 0x9835BAC6,
    0x03D39281, 0x03B205CF, 0x2882E734, 0xE714F663, 0xB96E2775, 0xBD8AAFC7,
    0x1DD3EC29, 0xECA4A16C, 0x5F69EC87, 0x85981E92, 0x7CFCAE21, 0xBAE9DD16,
    0xE6A97804, 0x2EEE02FC, 0x61DF8A3D, 0xDD310564, 0x9697E149, 0xC2453F3B,
    0xF91D8456, 0x39DA6BC8, 0xB3E5FEF5, 0x89C593A3, 0xFB5C8ABC, 0x6C0B7212,
    0xE10DD3CB, 0x98D0B2A8, 0x5FD61847, 0xF0DC2357, 0x7701166A, 0x0F5C3B68,
)
XORBUF = struct.pack("<36I", *EBOOT2XX_WORDS)
ZERO_IV = bytes(16)


def align16(size: int) -> int:
    return (size + 15) & ~15


def aes_cbc(data: bytes, key: bytes, *, encrypt: bool) -> bytes:
    if len(data) % 16:
        raise ValueError("AES-CBC input is not 16-byte aligned")
    ctx = Cipher(algorithms.AES(key), modes.CBC(ZERO_IV))
    op = ctx.encryptor() if encrypt else ctx.decryptor()
    return op.update(data) + op.finalize()


def cmac(data: bytes, key: bytes) -> bytes:
    ctx = CMAC(algorithms.AES(key))
    ctx.update(data)
    return ctx.finalize()


def xor_bytes(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right, strict=True))


def unpack_outer(original: bytes) -> tuple[bytearray, bytes]:
    if original[:4] != b"~PSP":
        raise ValueError("original is not a ~PSP file")
    if struct.unpack_from("<I", original, 0xD0)[0] != TAG:
        raise ValueError("original does not use tag C0CB167C")

    prx_header = original[:0x80]
    sha1 = original[0xD4:0xE8]
    unused = original[0xE8:0x110]
    kirk_block = original[0x110:0x150] + original[0x80:0xD0]

    type1_region = bytearray(sha1 + unused + kirk_block)
    type1_region[0x0C:0xAC] = aes_cbc(
        bytes(type1_region[0x0C:0xAC]), KIRK7_KEY_5D, encrypt=False
    )
    sha1 = bytes(type1_region[:0x14])
    unused = bytes(type1_region[0x14:0x3C])
    kirk_block = bytearray(type1_region[0x3C:0xCC])

    expected_sha1 = hashlib.sha1(XORBUF[:0x14] + unused + kirk_block + prx_header).digest()
    if sha1 != expected_sha1:
        raise ValueError("type-1 outer SHA-1 check failed")

    stage = xor_bytes(bytes(kirk_block[:0x70]), XORBUF[0x14:0x84])
    stage = aes_cbc(stage, KIRK7_KEY_5D, encrypt=False)
    kirk_block[:0x70] = xor_bytes(stage, XORBUF[0x20:0x90])
    return kirk_block, prx_header


def decrypt_prx(original: bytes) -> bytes:
    kirk_header, prx_header = unpack_outer(original)
    data_size, data_offset = struct.unpack_from("<II", kirk_header, 0x70)
    aligned_size = align16(data_size)
    combined = bytes(kirk_header) + prx_header + original[0x150:]
    required = 0x90 + data_offset + aligned_size
    if len(combined) < required:
        raise ValueError("encrypted body is truncated")

    keys = aes_cbc(bytes(kirk_header[:0x20]), KIRK1_KEY, encrypt=False)
    aes_key, cmac_key = keys[:16], keys[16:]
    header_hash = cmac(combined[0x60:0x90], cmac_key)
    data_hash = cmac(combined[0x60:required], cmac_key)
    if header_hash != kirk_header[0x20:0x30]:
        raise ValueError("KIRK header CMAC check failed")
    if data_hash != kirk_header[0x30:0x40]:
        raise ValueError("KIRK data CMAC check failed")

    body = combined[0x90 + data_offset:required]
    return aes_cbc(body, aes_key, encrypt=False)[:data_size]


def encrypt_prx(elf: bytes, original: bytes) -> bytes:
    if elf[:4] != b"\x7fELF":
        raise ValueError("input is not an ELF file")

    original_kirk, original_prx_header = unpack_outer(original)
    original_limit = struct.unpack_from("<I", original_kirk, 0x70)[0]
    if len(elf) > original_limit:
        raise ValueError(f"ELF is too large: {len(elf)} > {original_limit}")

    kirk_header = bytearray(original_kirk)
    prx_header = bytearray(original_prx_header)
    data_offset = struct.unpack_from("<I", kirk_header, 0x74)[0]
    struct.pack_into("<I", kirk_header, 0x70, len(elf))
    struct.pack_into("<I", prx_header, 0x28, len(elf))

    padded = elf + bytes(align16(len(elf)) - len(elf))
    output_size = 0x150 + len(padded)
    struct.pack_into("<I", prx_header, 0x2C, output_size)

    keys = aes_cbc(bytes(original_kirk[:0x20]), KIRK1_KEY, encrypt=False)
    aes_key, cmac_key = keys[:16], keys[16:]
    encrypted_body = aes_cbc(padded, aes_key, encrypt=True)

    raw = bytearray(kirk_header + prx_header + bytes(data_offset - 0x80) + encrypted_body)
    raw[:0x20] = keys
    raw[0x20:0x40] = bytes(0x20)
    raw[0x20:0x30] = cmac(bytes(raw[0x60:0x90]), cmac_key)
    raw[0x30:0x40] = cmac(bytes(raw[0x60:]), cmac_key)
    raw[:0x20] = aes_cbc(bytes(raw[:0x20]), KIRK1_KEY, encrypt=True)

    new_kirk = bytearray(raw[:0x90])
    stage = xor_bytes(bytes(new_kirk[:0x70]), XORBUF[0x20:0x90])
    stage = aes_cbc(stage, KIRK7_KEY_5D, encrypt=True)
    new_kirk[:0x70] = xor_bytes(stage, XORBUF[0x14:0x84])

    unused = bytearray(0x28)
    digest = hashlib.sha1(XORBUF[:0x14] + unused + new_kirk + prx_header).digest()
    type1_region = bytearray(digest + unused + new_kirk)
    type1_region[0x0C:0xAC] = aes_cbc(
        bytes(type1_region[0x0C:0xAC]), KIRK7_KEY_5D, encrypt=True
    )
    enc_sha1 = type1_region[:0x14]
    enc_unused = type1_region[0x14:0x3C]
    enc_kirk = type1_region[0x3C:0xCC]

    out = bytearray(output_size)
    out[:0x80] = prx_header
    out[0x80:0xD0] = enc_kirk[0x40:0x90]
    struct.pack_into("<I", out, 0xD0, TAG)
    out[0xD4:0xE8] = enc_sha1
    out[0xE8:0x110] = enc_unused
    out[0x110:0x150] = enc_kirk[:0x40]
    out[0x150:] = encrypted_body
    return bytes(out)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("elf", type=Path)
    parser.add_argument("original", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    elf = args.elf.read_bytes()
    original = args.original.read_bytes()
    encrypted = encrypt_prx(elf, original)
    roundtrip = decrypt_prx(encrypted)
    if roundtrip != elf:
        raise RuntimeError("round-trip verification failed")
    args.output.write_bytes(encrypted)
    print(f"input_sha256={sha256(elf)}")
    print(f"output_sha256={sha256(encrypted)}")
    print(f"size={len(encrypted)} tag=0x{struct.unpack_from('<I', encrypted, 0xD0)[0]:08X}")
    print("roundtrip=exact")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
