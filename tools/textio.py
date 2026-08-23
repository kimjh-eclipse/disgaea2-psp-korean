"""디스가이아2 문자열 블록(script00.dat 형식) 덤프/패치
포맷: u32 count, u32 count, 이후 각 문자열 NUL종단 + 여분NUL 1개
"""
import struct

def parse(data):
    cnt=struct.unpack('<I',data[:4])[0]
    a=8; ptrs=[]
    for i in range(cnt):
        ptrs.append(a)
        if data[a]!=0:
            while data[a]!=0: a+=1
        a+=2
    return cnt,ptrs

def dump(data):
    cnt,ptrs=parse(data)
    out=[]
    for i,p in enumerate(ptrs):
        e=data.index(b'\0',p)
        raw=data[p:e]
        # cp932 를 먼저 쓴다. ⑪ ④ ㍉ 같은 NEC 특수문자는 strict shift_jis 로는
        # 디코드에 실패해 text=None 이 되고, 그 문자열이 인벤토리에서 조용히 탈락한다.
        # 실제로 메모리스틱 관련 시스템 메시지 8건이 이렇게 누락됐다.
        s=None
        for enc in ('cp932','shift_jis'):
            try: s=raw.decode(enc); break
            except Exception: pass
        out.append(dict(id=i,off=p,nbytes=e-p,raw=raw,text=s))
    return out

def patch(data, edits, encoder):
    """edits: {id: '한글문자열'} / encoder: str->bytes"""
    buf=bytearray(data)
    cnt,ptrs=parse(data)
    applied=[]
    for sid,ko in edits.items():
        p=ptrs[sid]; e=buf.index(b'\0',p); n=e-p
        b=encoder(ko)
        if len(b)>n:
            raise ValueError(f'id {sid:#x}: {ko!r} {len(b)}B > 원본 {n}B')
        buf[p:p+n]=b+b' '*(n-len(b))
        applied.append((sid,n,len(b),ko))
    return bytes(buf),applied
