"""Use a one-pixel outline on each class-description line.

Live trace: 0x08932E8C calls 0x088A84E0 -> 0x088A8748 five times
per magic.dat description line. User screenshots establish that the central
pass is dark and the offset passes provide the bright outline. Preserve both,
but narrow horizontal offsets from +/-2 to +/-1. Vertical offsets stay +/-1.
No global font metrics are changed. Accept the previous no-outline patch too.
"""
import struct
from patch_eboot_buffer import load_segment

DRAW = 0x0C000000 | (0x088A84E0 >> 2)
MAIN_CALLS = (0x08934338, 0x08934418, 0x089344F8)
OFFSET_CALLS = (
    0x08934364, 0x08934390, 0x089343BC, 0x089343E8,
    0x08934444, 0x08934470, 0x0893449C, 0x089344C8,
    0x08934524, 0x08934550, 0x0893457C, 0x089345A8,
)
X_POSITIONS = {
    0x08934348: (77, 76), 0x08934374: (73, 74),
    0x08934428: (77, 76), 0x08934454: (73, 74),
    0x08934508: (77, 76), 0x08934534: (73, 74),
}


def patch(blob, verify_only=False):
    data = bytearray(blob)
    off, addr, size = load_segment(data)
    for pc in MAIN_CALLS + OFFSET_CALLS:
        assert 0 <= pc - addr < size - 7, f'Out of ELF segment: {pc:#x}'
        pos = off + pc - addr
        word, delay = struct.unpack_from('<II', data, pos)
        assert delay == 0x00005021, f'Unexpected delay slot: {pc:#x}'  # addu t2,zero,zero
        if pc in MAIN_CALLS:
            assert word == DRAW, f'Main text call altered: {pc:#x}'
        elif verify_only:
            assert word == DRAW, f'Outline pass missing: {pc:#x}'
        else:
            assert word in (DRAW, 0), f'Unexpected instruction: {pc:#x}: {word:#x}'
            struct.pack_into('<I', data, pos, DRAW)
    for pc, (old_x, new_x) in X_POSITIONS.items():
        pos = off + pc - addr
        word = struct.unpack_from('<I', data, pos)[0]
        old, new = 0x24040000 | old_x, 0x24040000 | new_x
        if verify_only:
            assert word == new, f'Outline horizontal offset mismatch: {pc:#x}'
        else:
            assert word in (old, new), f'Unexpected X instruction: {pc:#x}: {word:#x}'
            struct.pack_into('<I', data, pos, new)
    return bytes(data)
