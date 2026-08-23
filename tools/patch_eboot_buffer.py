# -*- coding: utf-8 -*-
"""JP 복호 EBOOT ELF 패치 2종.

1) talk 공유 버퍼 0x318F8 -> 0x36000 (9워드)
2) 전각 공백 0x8140 의 자간 15px -> 7px (11워드)

(2) 배경: 그리기 루프(0x088A8748, 루프머리 0x088A8BEC)는 문자마다 자간을
   0x1C8(sp) 에 넣고 0x088A9D20 에서 x 좌표에 더한다. 후보는 세 개뿐이다.
     0x1BC(sp)=15  2바이트 글자 전부
     0x1C0(sp)= 7  ASCII 영문자
     0x1C4(sp)=14  0x849F(괘선 ─, 타일링용)
   ASCII 공백(0x20)은 0x088A8BFC 에서 따로 처리되며 자간을 f22(=15.0*배율)에서
   가져온다 — fontB.fnt 을 고쳐도 공백 폭이 변하지 않던 이유가 이것이다.
   그런데 우리 대사는 공백을 전부 전각(0x8140)으로 쓴다. 1바이트 공백을 쓰면
   렌더러의 줄자르기가 문자 경계를 무시해 글자가 쪼개지기 때문이다(HANDOFF 23).
   따라서 손댈 곳은 f22 가 아니라 **2바이트 0x8140 의 자간**이다.

   구현: 자간 선택은 0x088A8C7C 의 `beql a0, zero` 하나로 갈린다(a0!=0 이면 7px).
   a0 은 원래 "ASCII 영문자인가" 판정인데, 원본은 그 판정에 11워드를 쓴다
   (slti/xori/andi/and 조합). 이를 5워드로 압축하고 남은 6워드에 0x8140 검사를
   넣어 `a0 = 영문자 || 전각공백` 으로 만든다. 새 코드·새 상수·트램폴린이 필요
   없고 0x849F(괘선)의 14px 도 그대로 보존된다.

   0x8140 은 글리프가 비어 있어 폭만 줄고 그려지는 것은 없다.
   자간이 배율(f12)을 타는 성질도 0x1C0(sp) 를 그대로 쓰므로 유지된다.
"""

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

# --- (2) 전각 공백 자간 15px -> 7px : 0x088A8C1C..0x088A8C44 (11워드) ---
#   진입 시점: s2 = 선행바이트, fp = 후행바이트를 가리킴, v0 = (s2<0x41) (버림)
#   나갈 때  : a0 = (ASCII 영문자) || (문자 == 0x8140)
#   v0/v1 은 바로 뒤 0x8C4C/0x8C5C 에서 재정의되고, a0 은 0x088A9CA0 에서
#   덮어써지므로 여기서 클로버해도 안전하다. s1 은 건드리지 않는다.
ADVANCE_PATCHES = {
    #                     원본 (11워드 영문자 판정)        새 코드
    0x088A8C1C: (0x38420001, 0x2642FFBF),  # xori v0,v0,1     -> addiu v0, s2, -0x41
    0x088A8C20: (0x304300FF, 0x2C43001A),  # andi v1,v0,0xff  -> sltiu v1, v0, 26      ; A-Z
    0x088A8C24: (0x2A42005B, 0x2642FF9F),  # slti v0,s2,0x5b  -> addiu v0, s2, -0x61
    0x088A8C28: (0x00622024, 0x2C44001A),  # and  a0,v1,v0    -> sltiu a0, v0, 26      ; a-z
    0x088A8C2C: (0x2A420061, 0x00832025),  # slti v0,s2,0x61  -> or   a0, a0, v1       ; 영문자
    0x088A8C30: (0x38420001, 0x93C30000),  # xori v0,v0,1     -> lbu  v1, 0(fp)        ; 후행바이트
    0x088A8C34: (0x304300FF, 0x00121200),  # andi v1,v0,0xff  -> sll  v0, s2, 8
    0x088A8C38: (0x2A42007B, 0x00431025),  # slti v0,s2,0x7b  -> or   v0, v0, v1       ; 문자코드 16비트
    0x088A8C3C: (0x00621024, 0x38428140),  # and  v0,v1,v0    -> xori v0, v0, 0x8140
    0x088A8C40: (0x00821025, 0x2C420005),  # or   v0,a0,v0    -> sltiu v0, v0, 5       ; 0x8140~0x8144 (xori 라 정확히 5개)
    0x088A8C44: (0x0002202B, 0x00822025),  # sltu a0,zero,v0  -> or   a0, a0, v0       ; ★
}
PATCHES.update(ADVANCE_PATCHES)


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
