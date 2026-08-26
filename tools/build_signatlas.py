# -*- coding: utf-8 -*-
"""지명 간판 아틀라스 한글화 — ANMPACK/anm7151.dat 안의 256x512 CLUT4 이미지.

★ 이것이 거점 진입 시 나오는 지명 간판(`ホルルト村`)의 진짜 출처다.

경위: 처음에 "이미지라서 못 찾았다"고 알려진 미번역으로 남겼고, 그 뒤 루트
`DUNGEON.DAT` 에서 같은 문자열을 찾아 "텍스트였다"고 정정했는데 **그것도 틀렸다**
(DUNGEON.DAT 은 스테이지 선택용 이름이고 간판이 아니다). GE 디버거 제보로
`Texture L0: 0x098a6600 (256x512)` / `CLUT: 0x098a6200` 을 얻어 RAM 을 떠서
(`tools/dump_texture.py`) 픽셀 지문으로 원본을 특정했다(`tools/match_texture.py`).

결정적 근거: 아틀라스에 있는 `ダロスの大河` `謎の城` 는 **ISO 어디에도 텍스트로
존재하지 않는다**. 개발 시점에 구워 넣은 이미지다.

레이아웃 (anm7151.dat)
    +0x10C0  RGBA 팔레트 (첫 16색이 간판용 알파 램프)
    +0x14C0  256x512 CLUT4 간판 시트 (65536B, PSP swizzled)
    +0x114C0 256x512 CLUT4 캐릭터 시트 (65536B) ← 절대 건드리지 않는다
      y   0.. 31  상단 바 장식      ← 건드리지 않는다
      y  64..447  지명 12줄         ← 여기만 다시 그린다 (줄당 32px)

중요: 뒤의 캐릭터 시트까지 합쳐 131072B를 8bpp 한 장으로 해석하면 글자가
겹치거나 점선으로 갈라진다. PPSSPP 실제 텍스처 덤프(256x512)와 두 시트의
독립 디코딩으로 규격을 확정했다. 팔레트 자체는 절대 변경하지 않는다.

사용:
    python tools/build_signatlas.py            # build_jp/ANMPACK.DAT 갱신 + 미리보기
    python tools/build_signatlas.py --iso      # ISO 주입까지
"""
import io
import os
import struct
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
sys.path.insert(0, HERE)

from PIL import Image, ImageDraw, ImageFont
import isopatch
import scriptpack
from txp import swizzle, unswizzle

MEMBER = 'anm7151.dat'
PAL_OFF, TEX_OFF = 0x10C0, 0x14C0
W, H = 256, 512
ROWBYTES = W // 2
ROW_Y0, ROWS, ROW_H = 64, 12, 32
COL_W = W
FONT_PATH, FONT_INDEX, FONT_SIZE = r'C:\Windows\Fonts\gulim.ttc', 2, 22
SPACE_PX = 4

# 원문 12줄 (위→아래) 과 번역. 용어는 기존 코퍼스·script00 번역과 일치시킨다.
#   ダロス大河 -> 다로스 대하 (기존 용례) / 謎の -> 수수께끼의 (기존 용례)
#   script00: 魔の大空洞=마의 대공동, アルケシティ=알케 시티, 神螺の塔=신라의 탑,
#             ゼノン城への道=제논 성으로 가는 길, ゼノン城=제논 성, コロシアム=콜로세움
NAMES = [
    ('ホルルト村',        '홀루트 마을'),
    ('ダロスの大河',      '다로스 대하'),
    ('魔の大空洞',        '마의 대공동'),
    ('コロシアム',        '콜로세움'),
    ('コロシアム集会場',   '콜로세움 집회장'),
    ('コロシアム地下祭壇', '콜로세움 지하제단'),
    ('アルケシティ',      '알케 시티'),
    ('神螺の塔',          '신라의 탑'),
    ('ゼノン城への道',    '제논 성으로 가는 길'),
    ('ゼノン城城門',      '제논성 성문'),
    ('ゼノン城',          '제논 성'),
    ('謎の城',            '수수께끼의 성'),
]


REF = 'jp/anm7151.dat'          # ★ 원본 멤버 (재현성의 기준)


def load_member():
    """수정 대상은 build_jp/ANMPACK.DAT(앞선 편집 보존), **측정 기준은 원본**.

    이미 한글로 바꾼 아틀라스를 다시 기준으로 삼으면 색 인덱스·세로 위치가
    실행마다 미끄러진다. 그래서 팔레트 램프와 원본 잉크 위치는 항상 REF 에서 읽는다.
    """
    data = open('build_jp/ANMPACK.DAT', 'rb').read()
    ents = scriptpack.unpack(data)
    ref = open(REF, 'rb').read()
    for e in ents:
        if e['name'] == MEMBER:
            if len(e['data']) != len(ref):
                raise SystemExit(f'{MEMBER} 크기가 원본과 다르다')
            return ents, e, ref
    raise SystemExit(f'{MEMBER} 없음')


def row_ink_y(idx, x0, row):
    """원본 글자의 세로 잉크 범위 — 새 글자도 여기에 맞춘다"""
    y0 = ROW_Y0 + row * ROW_H
    ys = [y for y in range(y0, y0 + ROW_H)
          if any(idx[y * W + x] for x in range(x0, x0 + COL_W))]
    return (min(ys), max(ys)) if ys else (y0 + 2, y0 + 13)


def render_text(text, font):
    """글자를 그레이스케일 마스크로 (여분 여백 없이)"""
    pad = 6
    im = Image.new('L', (COL_W + pad * 2, ROW_H + pad * 2), 0)
    d = ImageDraw.Draw(im)
    x = pad
    for ch in text:
        if ch == ' ':
            x += SPACE_PX
            continue
        d.text((x, pad), ch, 255, font=font)
        x += font.getlength(ch)
    box = im.getbbox()
    if not box:
        return None, None
    return im, box


def unpack_clut4(raw):
    out = bytearray(len(raw) * 2)
    for i, value in enumerate(raw):
        out[i * 2] = value & 0x0F
        out[i * 2 + 1] = value >> 4
    return out


def pack_clut4(indices):
    out = bytearray(len(indices) // 2)
    for i in range(0, len(indices), 2):
        out[i // 2] = (indices[i] & 0x0F) | ((indices[i + 1] & 0x0F) << 4)
    return out


def main(make_iso=False):
    ents, ent, ref = load_member()
    d = bytearray(ent['data'])
    # 원본(REF)에서 측정하고, 원본 픽셀을 출발점으로 다시 그린다 -> 몇 번 돌려도 같은 결과.
    tex_size = ROWBYTES * H
    orig_raw = unswizzle(bytes(ref[TEX_OFF:TEX_OFF + tex_size]), ROWBYTES, H)
    orig = bytes(unpack_clut4(orig_raw))
    idx = bytearray(orig)
    pal = d[PAL_OFF:PAL_OFF + 1024]
    alpha = [pal[i * 4 + 3] for i in range(16)]
    alpha_to_index = [min(range(16), key=lambda i: abs(alpha[i] - a)) for a in range(256)]

    font = ImageFont.truetype(FONT_PATH, FONT_SIZE, index=FONT_INDEX)
    for x0 in (0,):
        for row, (jp, ko) in enumerate(NAMES):
            row_top = ROW_Y0 + row * ROW_H
            row_bottom = row_top + ROW_H
            for y in range(row_top, row_bottom):
                for x in range(x0, x0 + COL_W):
                    idx[y * W + x] = 0

            im, box = render_text(ko, font)
            if im is None:
                continue
            gw, gh = box[2] - box[0], box[3] - box[1]
            if gw > COL_W:
                raise SystemExit(f'행 {row} `{ko}` 폭 {gw}px > {COL_W}px')

            iy0, iy1 = row_ink_y(orig, x0, row)
            base_x = x0 + (COL_W - gw) // 2
            base_y = iy0 + ((iy1 - iy0 + 1) - gh) // 2
            for yy in range(gh):
                for xx in range(gw):
                    v = im.getpixel((box[0] + xx, box[1] + yy))
                    if v < 8:
                        continue
                    ty, tx = base_y + yy, base_x + xx
                    if row_top <= ty < row_bottom and x0 <= tx < x0 + COL_W:
                        idx[ty * W + tx] = alpha_to_index[v]

    # 손대지 않아야 하는 영역 확인
    for y in list(range(0, ROW_Y0)) + list(range(ROW_Y0 + ROWS * ROW_H, H)):
        if idx[y * W:(y + 1) * W] != orig[y * W:(y + 1) * W]:
            raise SystemExit(f'보존 영역 y={y} 가 변경됐다')

    encoded = swizzle(bytes(pack_clut4(idx)), ROWBYTES, H)
    tail_before = bytes(d[TEX_OFF + tex_size:])
    d[TEX_OFF:TEX_OFF + tex_size] = encoded
    assert bytes(d[TEX_OFF + tex_size:]) == tail_before, '텍스처 뒤 데이터 변경'
    assert len(d) == len(ent['data']), '멤버 크기 변경'
    ent['data'] = bytes(d)
    packed = scriptpack.pack(ents)
    old = open('build_jp/ANMPACK.DAT', 'rb').read()
    if len(packed) != len(old):
        raise SystemExit(f'ANMPACK 크기 변경 {len(old)} -> {len(packed)}')
    open('build_jp/ANMPACK.DAT', 'wb').write(packed)
    print(f'ANMPACK.DAT 갱신 ({len(packed):,}B, 크기 불변)')

    # 미리보기
    P = [tuple(pal[i * 4:i * 4 + 4]) for i in range(256)]
    im = Image.new('RGBA', (W, ROW_Y0 + ROWS * ROW_H))
    im.putdata([P[v] for v in idx[:W * (ROW_Y0 + ROWS * ROW_H)]])
    os.makedirs('work', exist_ok=True)
    im.resize((W * 4, im.height * 4), Image.Resampling.NEAREST).save('work/sign_kr_x4.png')
    print('미리보기: work/sign_kr_x4.png')

    if make_iso:
        iso = os.environ.get('D2_ISO_DST', 'build_jp/D2_JP_KR.iso')
        r = isopatch.replace(iso, 25, b'ANMPACK.DAT', packed)
        print(f'ISO 갱신: ANMPACK.DAT {r}')
    return 0


if __name__ == '__main__':
    sys.exit(main('--iso' in sys.argv))
