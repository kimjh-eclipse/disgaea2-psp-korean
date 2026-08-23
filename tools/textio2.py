"""문자열 블록 재구성 — 길이 변경 허용판.
count 유지, 각 문자열을 새 길이로 다시 씀 (NUL + 여분NUL 규칙 유지).
"""
import struct
from textio import parse

def rebuild(data, edits, encoder):
    """edits: {id: '한글'} — 길이 제약 없음. 블록 전체를 재구성."""
    cnt,ptrs=parse(data)
    outs=[]
    for i,p in enumerate(ptrs):
        e=data.index(b'\0',p)
        outs.append(encoder(edits[i]) if i in edits else data[p:e])
    buf=bytearray(data[:8])          # u32 count, u32 count
    for s in outs:
        buf+=s+b'\0\0'
    return bytes(buf),cnt
