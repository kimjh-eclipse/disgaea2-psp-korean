# -*- coding: utf-8 -*-
"""지명 간판 아틀라스 한글화 — ANMPACK/anm7151.dat 안의 256x512 8bpp 이미지.

★ 이것이 거점 진입 시 나오는 지명 간판(`ホルルト村`)의 진짜 출처다.

경위: 처음에 "이미지라서 못 찾았다"고 알려진 미번역으로 남겼고, 그 뒤 루트
`DUNGEON.DAT` 에서 같은 문자열을 찾아 "텍스트였다"고 정정했는데 **그것도 틀렸다**
(DUNGEON.DAT 은 스테이지 선택용 이름이고 간판이 아니다). GE 디버거 제보로
`Texture L0: 0x098a6600 (256x512)` / `CLUT: 0x098a6200` 을 얻어 RAM 을 떠서
(`tools/dump_texture.py`) 픽셀 지문으로 원본을 특정했다(`tools/match_texture.py`).

결정적 근거: 아틀라스에 있는 `ダロスの大河` `謎の城` 는 **ISO 어디에도 텍스트로
존재하지 않는다**. 개발 시점에 구워 넣은 이미지다.

레이아웃 (anm7151.dat)
    +0x10C0  256색 RGBA 팔레트 (1024B)
    +0x14C0  256x512 8bpp PSP 스위즐 인덱스 (131072B)
      y   0.. 25  상단 바 장식      ← 건드리지 않는다
      y  32..223  지명 12줄 x 2열   ← 여기만 다시 그린다 (줄당 16px, 열당 128px)
      y 256..511  캐릭터 스프라이트  ← 건드리지 않는다 (anm8265.dat 과 공유)

팔레트는 스프라이트와 공용인 256색이라 원본 글자는 색 프린징이 있다. 색을 흉내내는
대신 **그 열에서 가장 많이 쓰인 인덱스**를 본체·외곽으로 뽑아 재현한다.

사용:
    python tools/build_signatlas.py            # build_jp/ANMPACK.DAT 갱신 + 미리보기
    python tools/build_signatlas.py --iso      # ISO 주입까지
"""
import io
import os
import struct
import sys
from collections import Counter

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
ROW_Y0, ROWS, ROW_H = 32, 12, 16
COL_W = 128
FONT_PATH, FONT_INDEX, FONT_SIZE = r'C:\Windows\Fonts\gulim.ttc', 2, 12   # 본문과 같은 돋움
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


def column_ramp(idx, x0):
    """그 열에서 많이 쓰인 인덱스 -> (본체, 외곽)"""
    c = Counter()
    for y in range(ROW_Y0, ROW_Y0 + ROWS * ROW_H):
        for x in range(x0, x0 + COL_W):
            v = idx[y * W + x]
            if v:
                c[v] += 1
    top = [v for v, _ in c.most_common(4)]
    core = top[0]
    edge = top[1] if len(top) > 1 else top[0]
    return core, edge


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
    return (im, box) if box else (None, None)


def main(make_iso=False):
    ents, ent, ref = load_member()
    d = bytearray(ent['data'])
    # 원본(REF)에서 측정하고, 원본 픽셀을 출발점으로 다시 그린다 -> 몇 번 돌려도 같은 결과
    orig = bytes(unswizzle(bytes(ref[TEX_OFF:TEX_OFF + W * H]), W, H))
    idx = bytearray(orig)

    font = ImageFont.truetype(FONT_PATH, FONT_SIZE, index=FONT_INDEX)
    for ci, x0 in enumerate((0, COL_W)):
        core, edge = column_ramp(orig, x0)
        print(f'  {"좌" if ci == 0 else "우"}열: 본체 idx {core}, 외곽 idx {edge}')
        for row, (jp, ko) in enumerate(NAMES):
            iy0, iy1 = row_ink_y(orig, x0, row)
            # 원본 글자 지우기 (그 행·그 열만)
            for y in range(ROW_Y0 + row * ROW_H, ROW_Y0 + (row + 1) * ROW_H):
                for x in range(x0, x0 + COL_W):
                    idx[y * W + x] = 0
            im, box = render_text(ko, font)
            if im is None:
                continue
            gw, gh = box[2] - box[0], box[3] - box[1]
            if gw > COL_W:
                raise SystemExit(f'행 {row} `{ko}` 폭 {gw}px > {COL_W}px')
            dx = x0 + (COL_W - gw) // 2
            dy = iy0 + ((iy1 - iy0 + 1) - gh) // 2
            for yy in range(gh):
                for xx in range(gw):
                    v = im.getpixel((box[0] + xx, box[1] + yy))
                    if v < 40:
                        continue
                    ty, tx = dy + yy, dx + xx
                    if not (ROW_Y0 <= ty < ROW_Y0 + ROWS * ROW_H and x0 <= tx < x0 + COL_W):
                        continue
                    idx[ty * W + tx] = core if v >= 140 else edge

    # 손대지 않아야 하는 영역 확인
    for y in list(range(0, ROW_Y0)) + list(range(ROW_Y0 + ROWS * ROW_H, H)):
        if idx[y * W:(y + 1) * W] != orig[y * W:(y + 1) * W]:
            raise SystemExit(f'보존 영역 y={y} 가 변경됐다')

    d[TEX_OFF:TEX_OFF + W * H] = swizzle(bytes(idx), W, H)
    assert len(d) == len(ent['data']), '멤버 크기 변경'
    ent['data'] = bytes(d)
    packed = scriptpack.pack(ents)
    old = open('build_jp/ANMPACK.DAT', 'rb').read()
    if len(packed) != len(old):
        raise SystemExit(f'ANMPACK 크기 변경 {len(old)} -> {len(packed)}')
    open('build_jp/ANMPACK.DAT', 'wb').write(packed)
    print(f'ANMPACK.DAT 갱신 ({len(packed):,}B, 크기 불변)')

    # 미리보기
    pal = d[PAL_OFF:PAL_OFF + 1024]
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
