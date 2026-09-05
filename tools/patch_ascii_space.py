"""Narrow the shared renderer's ASCII space without resizing any glyph."""
import struct
from patch_eboot_buffer import ASCII_SPACE_PATCHES, load_segment


def patch(blob, verify_only=False):
    data = bytearray(blob)
    off, addr, size = load_segment(data)
    def pos(pc):
        assert 0 <= pc - addr <= size - 4
        return off + pc - addr
    guards = {
        0x088A8BF8: 0x24030020,  # compare against ASCII space
        0x088A8BFC: 0x56430007,  # bnel s2,v1: other characters skip this path
        0x088A8C00: 0x2A420041,  # branch-likely delay for non-space only
        0x088A8C14: 0x1000FFF5,  # return to next character
        0x088A8784: 0x3C0340E0,  # 7.0 spacing source
        0x088A883C: 0xAFA301C0,  # scaled advance stored on stack
    }
    for pc, expected in guards.items():
        assert struct.unpack_from('<I', data, pos(pc))[0] == expected, f'Space guard: {pc:#x}'
    for pc, (old, new) in ASCII_SPACE_PATCHES.items():
        word = struct.unpack_from('<I', data, pos(pc))[0]
        assert word in ((new,) if verify_only else (old, new)), f'Space opcode: {pc:#x}'
        struct.pack_into('<I', data, pos(pc), new)
    return bytes(data)
