"""Undo the rejected title scaling; preserve native glyph size and position.

User wants spaces removed, not compressed glyphs. The script00 translations
are already '장비적성' and '기본능력'. Do not change global glyph advance.
"""
import struct
from patch_eboot_buffer import load_segment

PATCHES = {
    0x08933C44: (0x44826000, 0x44826800),  # mtc1 v0,f13 (height)
    0x08933C4C: (0x2404002F, 0x24040037),  # x 47 -> 55
    0x08933C5C: (0x46006346, 0x3C023F40),  # lui v0,0x3f40 (0.75)
    0x08933C68: (0x00005021, 0x44826000),  # delay: mtc1 v0,f12
    0x08933F94: (0x44826000, 0x44826800),
    0x08933F9C: (0x24040085, 0x2404008D),  # x 133 -> 141
    0x08933FAC: (0x46006346, 0x3C023F40),
    0x08933FB8: (0x00005021, 0x44826000),
}
GUARDS = {
    0x08933C38: 0x2404023A, 0x08933F88: 0x2404023B,
    0x08933C40: 0x3C023F80, 0x08933F90: 0x3C023F80,
    0x08933C64: 0x0E22A138, 0x08933FB4: 0x0E22A138,
    0x088A84E0: 0x90EA000C,  # wrapper overwrites t2
}


def patch(blob, verify_only=False):
    data = bytearray(blob)
    off, addr, size = load_segment(data)
    def pos(pc):
        assert 0 <= pc - addr <= size - 4
        return off + pc - addr
    for pc, expected in GUARDS.items():
        assert struct.unpack_from('<I', data, pos(pc))[0] == expected, f'Title guard: {pc:#x}'
    for pc, (old, new) in PATCHES.items():
        actual = struct.unpack_from('<I', data, pos(pc))[0]
        assert actual in ((old,) if verify_only else (old, new)), f'Title opcode: {pc:#x}'
        struct.pack_into('<I', data, pos(pc), old)
    return bytes(data)
