# -*- coding: utf-8 -*-
"""대사창 이름표(TXPPACK/name.txp) 한글 재렌더 -> TXPPACK 재팩 -> ISO 주입

19절의 미해결이던 이름표 출처. 텍스트가 아니라 **이미지 아틀라스**다:
  256x256, 4bpp, 16색 그레이스케일+알파, **리니어(스위즐 없음)** ← 폰트 페이지와 다름!
  2열 x 16행, 슬롯 128x16, 이름 중앙 정렬. 화자 ID 가 슬롯 인덱스.

원본 팔레트를 그대로 쓰고(색인만 다시 그림) 크기·헤더 불변이므로 TXPPACK 총크기도 불변.
사용: python tools/build_nameplate.py [--iso]
"""
import sys, os, io, struct
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
sys.path.insert(0, HERE)
import scriptpack, isopatch
from PIL import Image, ImageFont, ImageDraw

# (열, 행) -> 한국어 이름. None 이면 원본 유지(？？？？).
NAMES = {
    (0, 0): None,            # ？？？？ — 기호라 원본 유지
    (0, 1): '아델',
    (0, 2): '로자리',
    (0, 3): '로자린드',
    (0, 4): '하나코',
    (0, 5): '타로',
    (0, 6): '엄마',
    (0, 7): '아빠',
    (0, 8): '아쿠타레',
    (0, 9): '디렉터',
    (0, 10): '에트나',
    (0, 11): '라하르',
    (0, 12): '플로네',
    (0, 13): '프리니 부대',
    (0, 14): '팅크',
    (0, 15): '후부키',
    (1, 0): '유키마루',
    (1, 1): '가면의 남자',
    (1, 2): '가면의 여자',
    (1, 3): '마왕 제논',
    (1, 4): '마왕 제뇬',    # 魔王ゼノソ — ン→ソ 짝퉁 말장난을 논→뇬 으로 재현
    (1, 5): '상어',
}

W = H = 256
SLOT_W, SLOT_H = 128, 16
FONT = (r'C:\Windows\Fonts\gulim.ttc', 2, 12)      # Dotum 12 (본문과 동일 서체)
TXPPACK_LBA, TXPPACK_NEXT = 253712, 260448


def decode(d):
    pal = [tuple(d[0x10 + i * 4:0x10 + i * 4 + 4]) for i in range(16)]
    raw = d[0x50:0x50 + W * H // 2]
    idx = bytearray(W * H)
    for i, b in enumerate(raw):
        idx[i * 2] = b & 0xF; idx[i * 2 + 1] = b >> 4
    return pal, idx


def encode(hdr_pal, idx):
    px = bytearray(W * H // 2)
    for i in range(0, W * H, 2):
        px[i // 2] = (idx[i] & 0xF) | ((idx[i + 1] & 0xF) << 4)
    return hdr_pal + bytes(px)


def render_name(text, pal):
    """흰 글자 + 1px 어두운 외곽선 -> 128x16 색인 배열

    PIL 의 stroke_width 는 12px 폰트에서 획을 잠식해 뭉개진다(실제로 겪음).
    본문 마스크를 한 장 그려 8방향 팽창으로 외곽선을 만들고,
    본문=백색(15) / 외곽선=흑색(3) 로 직접 색인을 찍는다. AA 회색은 밝기 버킷.
    """
    font = ImageFont.truetype(FONT[0], FONT[2], index=FONT[1])
    core = Image.new('L', (SLOT_W, SLOT_H), 0)
    dr = ImageDraw.Draw(core)
    bb = dr.textbbox((0, 0), text, font=font)
    x = (SLOT_W - (bb[2] - bb[0])) // 2 - bb[0]
    y = (SLOT_H - (bb[3] - bb[1])) // 2 - bb[1]
    dr.text((x, y), text, fill=255, font=font)
    cm = core.load()

    # 8방향 팽창 = 외곽선 마스크
    edge = Image.new('L', (SLOT_W, SLOT_H), 0)
    em = edge.load()
    for yy in range(SLOT_H):
        for xx in range(SLOT_W):
            if cm[xx, yy] > 96:
                continue
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    px_, py_ = xx + dx, yy + dy
                    if 0 <= px_ < SLOT_W and 0 <= py_ < SLOT_H and cm[px_, py_] > 96:
                        em[xx, yy] = 255; break
                else:
                    continue
                break

    # 밝기 -> 백색 계열 색인 (원본 팔레트: 15=237, 14=205, 13=175, 12=148, 11=118)
    def bright(g):
        if g >= 220: return 15
        if g >= 190: return 14
        if g >= 160: return 13
        if g >= 130: return 12
        return 11

    out = bytearray(SLOT_W * SLOT_H)
    for j in range(SLOT_W * SLOT_H):
        xx, yy = j % SLOT_W, j // SLOT_W
        g = cm[xx, yy]
        if g > 96:
            out[j] = bright(g)         # 본문
        elif em[xx, yy]:
            out[j] = 3                 # 외곽선 (3,3,3,253)
        elif g > 32:
            out[j] = 6                 # 흐린 AA (12,11,14,155)
        else:
            out[j] = 0
    return out


def main(make_iso=False):
    pack = open('jp/TXPPACK.DAT', 'rb').read()
    ents = scriptpack.unpack(pack)
    ent = [e for e in ents if e['name'] == 'name.txp'][0]
    d = ent['data']
    pal, idx = decode(d)

    n = 0
    for (col, row), ko in NAMES.items():
        if ko is None:
            continue
        cell = render_name(ko, pal)
        for y in range(SLOT_H):
            base = (row * SLOT_H + y) * W + col * SLOT_W
            for x in range(SLOT_W):
                idx[base + x] = cell[y * SLOT_W + x]
        n += 1
    new = encode(d[:0x50], idx)
    assert len(new) == len(d), '크기 변경'
    ent['data'] = new
    print(f'name.txp: {n}개 이름 재렌더 (크기 불변 {len(new):,}B)')

    packed = scriptpack.pack(ents)
    assert len(packed) == len(pack), f'TXPPACK 크기 변경 {len(pack)}->{len(packed)}'
    open('build_jp/TXPPACK.DAT', 'wb').write(packed)
    print(f'TXPPACK {len(packed):,}B (불변)')

    if make_iso:
        r = isopatch.replace('build_jp/D2_JP_KR.iso', 25, b'TXPPACK.DAT', packed,
                             slot_lba=TXPPACK_LBA,
                             slot_sectors=TXPPACK_NEXT - TXPPACK_LBA)
        assert r['where'] == '제자리'
        print(f"ISO 갱신: TXPPACK -> {r['where']}, {r['size']:,}B")

    # 미리보기 PNG
    im = Image.new('RGBA', (W, H))
    px = im.load()
    for j in range(W * H):
        r, g, b, a = pal[idx[j]]
        px[j % W, j // W] = (r, g, b, min(255, a * 2))
    im.save('build_jp/nameplate_preview.png')
    print('미리보기: build_jp/nameplate_preview.png')


if __name__ == '__main__':
    main('--iso' in sys.argv)
