"""전체 텍스트 소스 통합 인벤토리 (원문 바이트 기준 중복 제거)"""
import struct,glob,os,csv,collections

def jp_runs(data,minlen=2):
    """(offset, raw_bytes) 리스트. SJIS 유효 런만."""
    res=[]; i=0; n=len(data); start=None; cur=bytearray(); jp=0
    def flush():
        nonlocal cur,jp,start
        if jp>=minlen and start is not None:
            res.append((start,bytes(cur)))
        cur=bytearray(); jp=0; start=None
    while i<n:
        b=data[i]
        if 0x20<=b<0x7f:
            if start is None: start=i
            cur.append(b); i+=1
        elif (0x81<=b<=0x9f or 0xe0<=b<=0xef) and i+1<n and 0x40<=data[i+1]<=0xfc and data[i+1]!=0x7f:
            if start is None: start=i
            cur+=data[i:i+2]; jp+=1; i+=2
        else:
            flush(); i+=1
    flush(); return res

def sources():
    out=[('start/script00.dat','jp/start/script00.dat'),
         ('start/InProgramTxtDB.dat','jp/start/InProgramTxtDB.dat')]
    for p in sorted(glob.glob('jp/scriptpack/*.dat')):
        out.append(('scriptpack/'+os.path.basename(p),p))
    return out

def build():
    uniq=collections.OrderedDict()   # raw -> dict(text, nbytes, occ=[(src,off)])
    for tag,path in sources():
        d=open(path,'rb').read()
        for off,raw in jp_runs(d):
            e=uniq.get(raw)
            if e is None:
                try: txt=raw.decode('shift_jis')
                except Exception: continue
                e=uniq[raw]=dict(text=txt,nbytes=len(raw),occ=[])
            e['occ'].append((tag,off))
    return uniq
