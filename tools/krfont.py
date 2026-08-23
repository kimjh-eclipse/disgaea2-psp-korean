"""디스가이아2 JP판 한글 글리프 베이크 + 코드 매핑
- 셀 14x14, 페이지당 36열, divisor 1296
- 페이지: fontB.ftd=page0, FontB0000.txp=page1, FontB0001.txp=page2
- 보존: gid 1..131 (ASCII + 0x81 전각기호/버튼아이콘)
- 한글: gid 132.. , 코드 0x8840부터 순차 (자간은 EBOOT 고정 15px)
"""
import struct, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import txp
from PIL import Image, ImageFont, ImageDraw

CELL, COLS, DIV = 14, 36, 1296
GID_BASE   = 132          # 한글 시작 gid (1..131 보존)
KEEP_IDX_MAX = 286        # idx 0..286 (ASCII + lead 0x81) 보존
CODE_C1_BASE = 0xF0       # 한글 코드 시작 선행바이트
# ★ 0xF0~0xFC = SJIS 사용자정의(외자) 영역 — 상용한자와 겹치지 않는다.
#   0x88~0x93 을 쓰면 원본 한자 1,480개가 엉뚱한 한글로 렌더되어 미번역 대사가
#   더 혼란스러워진다. 사용자정의 영역은 원본이 전혀 쓰지 않는다(충돌 0).
FONT_PATH, FONT_INDEX, FONT_SIZE = r'C:\Windows\Fonts\gulim.ttc', 2, 12   # Dotum 12
MOVE_BASE = 2411          # 보존 글리프(가나+그리스+기호) 시작 gid
# lead 0x84 / 0x87 의 UI용 글리프(─ ① Ⅰ 등)는 한글 구간과 겹쳐 지워지므로
# 원본 셀에서 복사해 MOVE_BASE 이후로 이전시킨다.
MOVE_LEADS = (0x84, 0x87)
# 가나(히라가나·가타카나)는 보존한다 — 미번역 일본어가 읽히도록.
# 전각영숫자(ＡＢ０１)·그리스·키릴은 버린다(번역에서 ASCII 로 대체).
KEEP_KANA = True
TRAIL_BASE, TRAIL_N = 0x80, 125   # 후행바이트 0x80..0xFC 만 쓴다
# ★ 후행바이트를 0x40~0x7F 에 배정하면 안 된다.
#   게임 렌더러가 일부 값(관측: 0x4D 0x52 0x58 0x63 0x66 0x67)에서 포인터를
#   1바이트만 전진시켜, 글리프를 그린 뒤 후행바이트를 ASCII 로 한 번 더 그린다.
#   화면에 '해f도' '제R논' '필X요' 처럼 알파벳이 끼어든다 (인게임에서 실제로 발생).
#   같은 선행바이트라도 0xFB5D(하)는 정상, 0xFB66(해)는 깨지므로 선행바이트가 아니라
#   후행바이트 값 문제다. <0x80 이 전부 깨지는 것은 아니지만 깨지는 것은 전부 <0x80 이라
#   (표본: >=0x80 은 27자 전원 정상 / <0x80 은 13자 중 6자 깨짐) 그 범위를 통째로 피한다.
#   용량: 선행 0xF0~0xFC 13개 x 후행 125개 = 1625자 (실사용 1187자, 여유 438자)
HANGUL_LIMIT = 1625       # gid 132..1756, 보존분(가나169+기호12=181) = gid 2411..2591

def hangul_list():
    """KS X 1001 완성형 2350자 (EUC-KR 0xB0A1..0xC8FE 순서)"""
    out=[]
    for c1 in range(0xB0,0xC9):
        for c2 in range(0xA1,0xFF):
            try: out.append(bytes([c1,c2]).decode('euc-kr'))
            except UnicodeDecodeError: pass
    return out

def n_to_code(n):
    """한글 순번 n -> 게임 코드 (c1,c2). 후행은 0x80..0xFC 만 (위 TRAIL_BASE 주석 참고)"""
    return CODE_C1_BASE + n // TRAIL_N, TRAIL_BASE + n % TRAIL_N

def code_to_idx(c1,c2):
    row = c1-0x81 if c1 < 0xE0 else c1-0xC1
    return 0x5F + row*192 + (c2-0x40)

def load_page(path):
    d=open(path,'rb').read()
    w,h = struct.unpack('<HH', d[:4])
    pb  = struct.unpack('<H', d[0x0A:0x0C])[0]
    ncol= 16*pb
    hdr = d[:0x10]
    pal = d[0x10:0x10+ncol*4]
    px  = txp.unswizzle(d[0x10+ncol*4:0x10+ncol*4+w*h//2], w//2, h)
    idx = bytearray(w*h)
    for i,b in enumerate(px):
        idx[i*2]=b&0xF; idx[i*2+1]=b>>4
    return dict(w=w,h=h,hdr=hdr,pal=pal,idx=idx)

def save_page(p, path):
    w,h,idx = p['w'],p['h'],p['idx']
    px=bytearray(w*h//2)
    for i in range(0,w*h,2):
        px[i//2]=(idx[i]&0xF)|((idx[i+1]&0xF)<<4)
    open(path,'wb').write(p['hdr']+p['pal']+txp.swizzle(bytes(px), w//2, h))

def cell_rect(gid):
    """gid -> (page, x, y)"""
    pg, c = divmod(gid, DIV)
    r, cc = divmod(c, COLS)
    return pg, cc*CELL, r*CELL

def wipe(pages, gid_lo, gid_hi):
    n=0
    for g in range(gid_lo, gid_hi+1):
        pg,x,y = cell_rect(g)
        if pg>=len(pages): continue
        p=pages[pg]
        if y+CELL>p['h'] or x+CELL>p['w']: continue
        for yy in range(CELL):
            base=(y+yy)*p['w']+x
            for xx in range(CELL): p['idx'][base+xx]=0
        n+=1
    return n

# ★ 원본 폰트에 글리프가 아예 없는 ASCII — 매핑이 gid 0(빈칸)이다.
#   번역이 `?` 1,984회 · `~` 538회를 쓰는데 인게임에서 전부 안 보였다(실제로 겪음).
#   한글을 1,625자로 줄여 생긴 빈 gid(1757..2410)에 새로 구워 넣는다.
ASCII_FIX = "?~:&<>'vqz$*@\\^|`"
ASCII_BASE = GID_BASE + HANGUL_LIMIT      # 1757 — 한글 바로 뒤
FULLWIDTH_ALNUM_BASE = ASCII_BASE         # 1757..1818 — 원본 전각 ０..９Ａ..Ｚａ..ｚ 복사
HALF = 0x0700                             # 반각 자간 (원본 ASCII 숫자·영문과 동일)


def bake_ascii(pages, font):
    """글리프 없는 ASCII 를 ASCII_BASE 이후에 반각으로 구워 넣는다 -> [(ch,gid)]"""
    out = []
    for n, ch in enumerate(ASCII_FIX):
        gid = ASCII_BASE + n
        pg, x, y = cell_rect(gid)
        if pg >= len(pages):
            raise RuntimeError(f'ASCII 보충 페이지 초과: gid {gid}')
        p = pages[pg]
        im = Image.new('L', (CELL, CELL), 0); d = ImageDraw.Draw(im)
        bb = font.getbbox(ch); w = bb[2]-bb[0]; h = bb[3]-bb[1]
        # 반각이므로 셀 왼쪽 7px 안에 그린다(자간 트림이 오른쪽 7px 을 잘라낸다)
        d.text(((7-w)//2-bb[0], (CELL-h)//2-bb[1]), ch, 255, font=font)
        for yy in range(CELL):
            base = (y+yy)*p['w']+x
            for xx in range(CELL):
                p['idx'][base+xx] = im.getpixel((xx, yy)) >> 4
        out.append((ch, gid))
    return out


def bake(pages, chars, font):
    """chars[n] -> gid GID_BASE+n"""
    placed=[]
    for n,ch in enumerate(chars):
        gid=GID_BASE+n
        pg,x,y = cell_rect(gid)
        if pg>=len(pages): raise RuntimeError(f'페이지 초과: gid {gid}')
        p=pages[pg]
        if y+CELL>p['h'] or x+CELL>p['w']:
            raise RuntimeError(f'셀 범위 초과: gid {gid} page{pg} ({x},{y})')
        im=Image.new('L',(CELL,CELL),0); d=ImageDraw.Draw(im)
        bb=font.getbbox(ch); w=bb[2]-bb[0]; h=bb[3]-bb[1]
        d.text(((CELL-w)//2-bb[0],(CELL-h)//2-bb[1]),ch,255,font=font)
        for yy in range(CELL):
            base=(y+yy)*p['w']+x
            for xx in range(CELL):
                p['idx'][base+xx]=im.getpixel((xx,yy))>>4
        placed.append((n,ch,gid,pg,x,y))
    return placed

def collect_kana(map_src):
    """보존할 가나 (c1,c2,old_gid) 목록 — 히라가나/가타카나만"""
    import struct as _s
    cnt=_s.unpack('<H',map_src[:2])[0]
    out=[]
    for c1 in (0x82,0x83):
        for c2 in range(0x40,0x100):
            if c2==0x7f: continue
            i=code_to_idx(c1,c2)
            if i>=cnt: continue
            g=_s.unpack('<H',map_src[2+2*i:4+2*i])[0]
            if not g: continue
            b=bytes([c1,c2])
            ch=None
            for enc in ('cp932','shift_jis'):
                try: ch=b.decode(enc); break
                except Exception: pass
            if ch is None: continue
            o=ord(ch)
            # 가나 + 그리스/키릴(상태이상 마커 ω ξ 등 게임상 의미 있음)
            # 전각영숫자(ＦＦ01~ＦＦ5E)만 제외 — 번역에서 ASCII 로 대체
            if not (0xFF01<=o<=0xFF5E):
                out.append((c1,c2,g))
    return out

def collect_moves(map_src):
    """이전 대상: MOVE_LEADS 에서 실제 매핑된 (c1,c2,old_gid) 목록"""
    import struct as _s
    cnt=_s.unpack('<H',map_src[:2])[0]
    out=[]
    for c1 in MOVE_LEADS:
        for c2 in range(0x40,0x100):
            if c2==0x7f: continue
            i=code_to_idx(c1,c2)
            if i>=cnt: continue
            g=_s.unpack('<H',map_src[2+2*i:4+2*i])[0]
            if g: out.append((c1,c2,g))
    return out

def collect_fullwidth_alnum(map_src):
    """원본 전각 영숫자 ０-９Ａ-Ｚａ-ｚ의 (c1,c2,old_gid) 목록.

    대사 렌더러가 고정 바이트 오프셋으로 줄을 자르므로 대사의 모든 문자는 2바이트여야
    한다. 숫자 722회·대문자 444회가 대사에 쓰이므로 전각 영숫자 글리프를 원본에서
    복원해(빈 gid 1757~) 치환할 수 있게 한다. SJIS 824F-8258 / 8260-8279 / 8281-829A.
    """
    import struct as _s
    cnt=_s.unpack('<H',map_src[:2])[0]
    out=[]
    for c2 in list(range(0x4F,0x59))+list(range(0x60,0x7A))+list(range(0x81,0x9B)):
        i=code_to_idx(0x82,c2)
        if i>=cnt: raise RuntimeError(f'전각 영숫자 맵 범위 초과: 82{c2:02X}')
        g=_s.unpack('<H',map_src[2+2*i:4+2*i])[0]
        if not g: raise RuntimeError(f'원본 전각 영숫자 글리프 없음: 82{c2:02X}')
        out.append((0x82,c2,g))
    return out

def move_glyphs_to(dst_pages, src_pages, moves, base):
    """원본 페이지의 셀을 새 gid 위치로 복사"""
    done=[]
    for k,(c1,c2,old) in enumerate(moves):
        new=base+k
        sp,sx,sy = cell_rect(old)
        dp,dx,dy = cell_rect(new)
        if sp>=len(src_pages) or dp>=len(dst_pages):
            raise RuntimeError(f'이전 실패 {c1:02X}{c2:02X}')
        S=src_pages[sp]; D=dst_pages[dp]
        for y in range(CELL):
            sb=(sy+y)*S['w']+sx; db=(dy+y)*D['w']+dx
            for x in range(CELL): D['idx'][db+x]=S['idx'][sb+x]
        done.append((c1,c2,old,new))
    return done

def move_glyphs(dst_pages, src_pages, moves):
    return move_glyphs_to(dst_pages, src_pages, moves, MOVE_BASE)

def build_tables(map_src, fnt_src, chars, moves=(), ascii_fix=()):
    mp=bytearray(map_src); ft=bytearray(fnt_src)
    cnt=struct.unpack('<H',mp[:2])[0]
    # 보존 구간 밖은 전부 0으로
    for i in range(KEEP_IDX_MAX+1, cnt):
        struct.pack_into('<H',mp,2+2*i,0)
        struct.pack_into('<H',ft,2+2*i,0)
    codes=[]
    for n,ch in enumerate(chars):
        c1,c2=n_to_code(n); i=code_to_idx(c1,c2)
        if i>=cnt: raise RuntimeError(f'맵 범위 초과 idx {i}')
        struct.pack_into('<H',mp,2+2*i,GID_BASE+n)
        struct.pack_into('<H',ft,2+2*i,0x0000)   # 한자와 동일 = 전각 풀셀
        codes.append((ch,c1,c2,i,GID_BASE+n))
    # 이전 보존 글리프 재매핑 (원본 fnt 값도 함께 이전)
    for c1,c2,old,new in moves:
        i=code_to_idx(c1,c2)
        struct.pack_into('<H',mp,2+2*i,new)
        struct.pack_into('<H',ft,2+2*i,struct.unpack_from('<H',fnt_src,2+2*i)[0])
    # 글리프 없던 ASCII 를 새 셀로 매핑 (반각)
    for ch,gid in ascii_fix:
        i=ord(ch)-0x20
        struct.pack_into('<H',mp,2+2*i,gid)
        struct.pack_into('<H',ft,2+2*i,HALF)
    # ★ ASCII 공백을 반각으로. 원본은 fnt=0x0000 = 한자와 같은 전각 15px 이라
    #   공백 44,597회가 각각 한 칸을 먹어 대사가 창을 넘쳤다(실제로 겪음).
    #   일본어 원문은 공백을 쓰지 않으므로 원본 값이 그대로 남아 있었다.
    struct.pack_into('<H',ft,2+2*0,HALF)
    return bytes(mp), bytes(ft), codes


# ★ 원본 전각 기호·영숫자 글리프는 일본어 폰트용으로 커서(높이 12~13px) 한글(11px) 옆에
#   놓이면 튄다. 인게임에서 `？ ！` 와 숫자가 커 보인다는 지적을 받았다.
#   그래서 원본 셀을 복사하는 대신 **같은 서체(돋움 12)로 다시 구워** 크기를 맞춘다.
#   대상: 대사에서 실제로 쓰는 전각 기호 + 전각 영숫자.
REBAKE_SYMS = '？！：；，．（）－／～'


def rebake_cell(pages, ch, gid, font, halfwidth=False):
    """gid 셀을 우리 서체로 다시 그린다 (기존 픽셀은 지운다)

    ★ 세로 위치는 getbbox 로 예측하지 않는다 — 폰트마다 어긋난다(실제로 ～ 가 상단에 붙었다).
      일단 그린 뒤 **잉크 박스를 재서 옮긴다.**
        마침표류(，．、。・)  잉크 하단을 y=11 에 (원본처럼 베이스라인)
        물결·붙임표(～－)     잉크 중심을 y=6 에
        그 외                 잉크를 한글 박스(y 1..11) 중앙에
    """
    pg, x, y = cell_rect(gid)
    if pg >= len(pages):
        return False
    p = pages[pg]
    PAD = 8
    im = Image.new('L', (CELL + PAD * 2, CELL + PAD * 2), 0)
    d = ImageDraw.Draw(im)
    box = 7 if halfwidth else CELL
    d.text((PAD, PAD), ch, 255, font=font)
    ink = im.getbbox()
    if ink is None:
        return False
    x0, y0, x1, y1 = ink
    iw, ih = x1 - x0, y1 - y0
    # 가로: 셀(또는 반각 박스) 중앙
    tx = (box - iw) // 2
    # 세로: 위 규칙
    if ch in '，．、。・':
        ty = 12 - ih
    elif ch in '～－':
        ty = 6 - ih // 2
    else:
        ty = 1 + (11 - ih) // 2
    for yy in range(CELL):
        base = (y + yy) * p['w'] + x
        for xx in range(CELL):
            sx, sy = x0 + xx - tx, y0 + yy - ty
            v = im.getpixel((sx, sy)) if (0 <= sx < im.width and 0 <= sy < im.height) else 0
            p['idx'][base + xx] = v >> 4
    return True

def rebake_symbols(pages, map_src, font):
    """lead 0x81 전각기호를 원위치 gid 에서 다시 굽는다 -> [(문자, gid)]"""
    import struct as _s
    out = []
    for ch in REBAKE_SYMS:
        b = ch.encode('cp932')
        i = code_to_idx(b[0], b[1])
        gid = _s.unpack_from('<H', map_src, 2 + 2 * i)[0]
        if not gid:
            continue
        if rebake_cell(pages, ch, gid, font):
            out.append((ch, gid))
    return out
