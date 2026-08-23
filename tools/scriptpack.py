# -*- coding: utf-8 -*-
"""NISPACK 언팩/리팩 (SCRIPTPACK.DAT, TXPPACK.DAT 등)

포맷
  +0x00  char[8] "NISPACK\0"
  +0x08  u32     (0)
  +0x0C  u32     count
  +0x10  entry[count], 각 0x2C
           +0x00 char[32] 파일명 (NUL 종단)
           +0x20 u32 offset
           +0x24 u32 size
           +0x28 u32 해시/타임스탬프  ← 보존
  데이터는 0x800 정렬로 배치
"""
import struct

ALIGN = 0x800
ENT = 0x2C


def unpack(data):
    assert data[:8] == b'NISPACK\0', data[:8]
    cnt = struct.unpack('<I', data[0x0C:0x10])[0]
    out = []
    for i in range(cnt):
        o = 0x10 + i * ENT
        name = data[o:o + 32].split(b'\0')[0].decode('latin1')
        off, size, tag = struct.unpack('<III', data[o + 32:o + 44])
        out.append(dict(name=name, off=off, size=size, tag=tag,
                        data=data[off:off + size]))
    return out


def pack(entries):
    """entries: unpack() 결과 (data 를 교체해도 됨). 원래 순서/이름/tag 유지."""
    cnt = len(entries)
    head = bytearray(b'NISPACK\0' + struct.pack('<II', 0, cnt))
    head += bytes(ENT * cnt)
    # 데이터 시작을 ALIGN 으로 올림
    pos = (len(head) + ALIGN - 1) // ALIGN * ALIGN
    body = bytearray()
    placed = []
    # 원본과 같은 배치 순서(오프셋 순)를 유지
    order = sorted(range(cnt), key=lambda i: entries[i]['off'])
    for k, i in enumerate(order):
        e = entries[i]
        start = pos + len(body)
        body += e['data']
        if k != len(order) - 1:                 # 마지막 파일 뒤에는 패딩 없음
            body += bytes((-len(body)) % ALIGN)
        placed.append((i, start, len(e['data'])))
    for i, start, size in placed:
        o = 0x10 + i * ENT
        nm = entries[i]['name'].encode('latin1')
        head[o:o + 32] = nm + bytes(32 - len(nm))
        struct.pack_into('<III', head, o + 32, start, size, entries[i]['tag'])
    out = bytearray(head)
    out += bytes(pos - len(head))
    out += body
    return bytes(out)
