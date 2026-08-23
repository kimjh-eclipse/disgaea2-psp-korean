# -*- coding: utf-8 -*-
"""고정 레코드 DB (HABIT / dungeon / charhelp / magic / mitem / music) 문자열 필드 입출력

포맷 (6개 파일 공통)
  +0x00  u32 count
  +0x04  u32 count (중복)
  +hdr   record[count], 각 rs 바이트. 문자열 필드는 레코드 내 고정 오프셋·고정 폭.

talk 계열과 달리 **필드 폭이 고정**이다. 번역문이 폭을 넘으면 다음 필드를 침범하므로
put() 이 예외를 던진다. 종단 NUL 1바이트를 위해 실제 가용은 (w-1) 바이트.

한글은 이 인코딩에서 2바이트/음절 = 한자와 동일하므로, 원문이 한자 위주면 대개 들어가고
가나 위주(1바이트 아님, 가나도 2바이트)여도 동일하다. 문제는 ASCII 위주 원문뿐이다.
"""
import struct

# 파일 -> (헤더크기, 레코드크기, [(필드오프셋, 필드폭), ...])
# 바이너리 필드는 제외하고 실제 텍스트 필드만 등록한다.
SPEC = {
    'HABIT.dat':    (8,  120, [(0x00, 21), (0x15, 87)]),
    'dungeon.dat':  (8,   64, [(0x00, 64)]),
    'charhelp.dat': (8,   80, [(0x00, 22)]),
    'magic.dat':    (8,  152, [(0x00, 50), (0x32, 50), (0x64, 50)]),
    'mitem.dat':    (16, 104, [(0x08, 24), (0x20, 72)]),
    'music.dat':    (8,  140, [(0x28, 47), (0x57, 53)]),
}


def count(data):
    a, b = struct.unpack_from('<II', data, 0)
    if a != b:
        raise ValueError(f'count 불일치 {a} != {b}')
    return a


def items(name, data):
    """[(rec_index, field_offset, width, raw_bytes)] — 비어있지 않은 필드만"""
    hdr, rs, fields = SPEC[name]
    n = count(data)
    if hdr + n * rs > len(data):
        raise ValueError('레코드 영역이 파일보다 큼')
    out = []
    for i in range(n):
        b = hdr + i * rs
        for off, w in fields:
            s = data[b + off:b + off + w]
            e = s.find(0)
            s = s[:e] if e >= 0 else s
            if s:
                out.append((i, off, w, bytes(s)))
    return out


def put(name, data, edits):
    """edits: {(rec_index, field_offset): new_bytes}. 폭 초과는 예외."""
    hdr, rs, fields = SPEC[name]
    width = {off: w for off, w in fields}
    out = bytearray(data)
    for (i, off), new in edits.items():
        w = width[off]
        if len(new) + 1 > w:
            raise ValueError(f'{name} rec{i} +{off:#x}: {len(new)}B > 가용 {w-1}B')
        b = hdr + i * rs + off
        out[b:b + w] = new + b'\0' * (w - len(new))
    return bytes(out)
