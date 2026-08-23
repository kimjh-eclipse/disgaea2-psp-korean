"""한글 텍스트 -> 게임 바이트 인코더 (디스가이아2 JP 베이스)

통과 규칙:
  - ASCII (0x20-0x7E)          : 그대로 (원본 글리프 보존됨)
  - 한글 2350자               : 전용 코드 0x8840~0x946D
  - lead 0x81 전각기호/버튼아이콘 : 원본 SJIS 바이트 (글리프 보존됨) ○△□×！？「」…
  - 가나(히라가나·가타카나) : 보존됨 — 미번역 일본어가 읽히도록 남겨둠
  - 그 외 (한자·전각영숫자·그리스) : 예외 발생 — 글리프를 지웠으므로 쓰면 안 됨
"""
import os
_DIR=os.path.dirname(os.path.abspath(__file__))
_TSV=os.path.join(_DIR,'..','build_jp','hangul_codes.tsv')
_HAN=None; _SYM=None

def _load():
    global _HAN,_SYM
    if _HAN is None:
        _HAN={}
        for line in open(_TSV,encoding='utf-8').read().splitlines()[1:]:
            ch,c1,c2,i,g=line.split('\t')
            _HAN[ch]=bytes([int(c1,16),int(c2,16)])
        # 보존 구간: lead 0x81 전체 (idx 95..286 -> gid 78..131)
        _SYM={}
        for c2 in range(0x40,0x100):
            if c2==0x7f: continue
            b=bytes([0x81,c2])
            for enc in ('cp932','shift_jis'):     # 두 코덱의 유니코드 매핑 차이 모두 수용
                try: _SYM.setdefault(b.decode(enc),b)
                except Exception: pass
        # 보존 이전분 (가나 + lead 0x84/0x87 기호) — moved_codes.tsv 에 전부 들어있다
        mv=os.path.join(_DIR,'..','build_jp','moved_codes.tsv')
        if os.path.exists(mv):
            for line in open(mv,encoding='utf-8').read().splitlines()[1:]:
                c1,c2,o,n=line.split('	')
                b=bytes([int(c1,16),int(c2,16)])
                for enc in ('cp932','shift_jis'):
                    try: _SYM.setdefault(b.decode(enc),b)
                    except Exception: pass
    return _HAN,_SYM

def encode(s):
    han,sym=_load(); out=bytearray()
    for ch in s:
        o=ord(ch)
        if 0x20<=o<0x7f: out.append(o)
        elif ch in han: out+=han[ch]
        elif ch in sym: out+=sym[ch]
        else:
            raise KeyError(f'인코딩 불가 문자 {ch!r} (U+{o:04X}) — 글리프 없음')
    return bytes(out)

def _blank_ascii():
    """빌드된 맵에서 gid 0(글리프 없음)인 ASCII 문자 집합

    ★ 예전에는 ASCII 0x20~0x7E 를 전부 무조건 통과시켰다. 그런데 원본 폰트에는
      `? ~ : & < > ' v q z $ * @ \\ ^ | \x60` 의 글리프가 아예 없어서, 번역의
      물음표 1,984회가 인게임에서 전부 빈칸으로 나왔는데도 QA 가 통과시켰다.
      지금은 bake_ascii 가 이들을 새로 구워 넣지만, 맵을 직접 읽어 확인한다.
    """
    global _BLANK
    try: return _BLANK
    except NameError: pass
    import struct
    _BLANK=set()
    mp=os.path.join(_DIR,'..','build_jp','talk00.dat')
    if os.path.exists(mp):
        d=open(mp,'rb').read()
        for c in range(0x20,0x7f):
            if struct.unpack_from('<H',d,2+2*(c-0x20))[0]==0 and c!=0x20:
                _BLANK.add(chr(c))
    return _BLANK

def validate(s):
    """인코딩 가능 + 글리프 존재 검사. 문제 문자 목록 반환(빈 리스트면 정상)."""
    han,sym=_load(); blank=_blank_ascii(); bad=[]
    for ch in s:
        o=ord(ch)
        if ch in blank: bad.append(ch); continue
        if 0x20<=o<0x7f or ch in han or ch in sym: continue
        bad.append(ch)
    return bad

def symbols():
    """사용 가능한 보존 기호 목록"""
    return ''.join(sorted(_load()[1]))
