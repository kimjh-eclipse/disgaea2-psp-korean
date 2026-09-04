# -*- coding: utf-8 -*-
"""복호 EBOOT에서 공용 폰트 렌더러 호출부를 찾고 주변을 역어셈블한다."""
import struct
from pathlib import Path

from capstone import Cs, CS_ARCH_MIPS, CS_MODE_LITTLE_ENDIAN, CS_MODE_MIPS32
from patch_eboot_buffer import load_segment

ROOT = Path(__file__).resolve().parent.parent
EBOOT = ROOT / 'build_jp' / 'EBOOT_KR.BIN'
TARGETS = (0x088A8748,)


def main():
    data = EBOOT.read_bytes()
    seg_off, seg_addr, seg_size = load_segment(data)
    segment = data[seg_off:seg_off + seg_size]
    md = Cs(CS_ARCH_MIPS, CS_MODE_MIPS32 | CS_MODE_LITTLE_ENDIAN)
    for target in TARGETS:
        word = 0x0C000000 | ((target >> 2) & 0x03FFFFFF)
        needle = struct.pack('<I', word)
        hits = []
        start = 0
        while True:
            off = segment.find(needle, start)
            if off < 0:
                break
            hits.append(seg_addr + off)
            start = off + 4
        print(f'target {target:08X}: {len(hits)} callers')
        for address in hits:
            begin = max(seg_addr, address - 0x40)
            blob = segment[begin - seg_addr:begin - seg_addr + 0x70]
            print(f'\n-- caller {address:08X} --')
            for ins in md.disasm(blob, begin):
                mark = '>>' if ins.address == address else '  '
                print(f'{mark} {ins.address:08X}  {ins.mnemonic:8s} {ins.op_str}')
        if not hits:
            begin = target - 0x180
            blob = segment[begin - seg_addr:target - seg_addr + 0x280]
            print(f'\n-- target vicinity {begin:08X}..{target + 0x280:08X} --')
            for ins in md.disasm(blob, begin):
                print(f'   {ins.address:08X}  {ins.mnemonic:8s} {ins.op_str}')


if __name__ == '__main__':
    main()
