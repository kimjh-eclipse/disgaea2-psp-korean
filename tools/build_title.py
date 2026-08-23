# -*- coding: utf-8 -*-
"""한국어 타이틀 PNG -> TXPPACK/wbg11.txp -> ISO 주입.

입력: work/title_kr_imagegen.png (GPT imagegen 편집 결과)
형식: 480x272, 8bpp/256색 RGBA 팔레트, linear indices, 원본 TXP 헤더 유지.

기존 build_jp/TXPPACK.DAT가 있으면 이름표 등 앞선 수정을 보존하기 위해 그것을 기반으로 한다.
사용:
  python tools/build_title.py
  D2_ISO_DST=build_jp/D2_JP_KR_title.iso python tools/build_title.py --iso
"""
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
sys.path.insert(0, HERE)

from PIL import Image
import isopatch
import scriptpack

W, H = 480, 272
MEMBER = 'wbg11.txp'
SOURCE_PNG = 'work/title_kr_imagegen.png'
TXPPACK_LBA, TXPPACK_NEXT = 253712, 260448


def fit(im):
    """중앙 크롭 후 정확히 480x272로 축소."""
    im = im.convert('RGB')
    target = W / H
    ratio = im.width / im.height
    if ratio > target:
        nw = round(im.height * target)
        left = (im.width - nw) // 2
        im = im.crop((left, 0, left + nw, im.height))
    elif ratio < target:
        nh = round(im.width / target)
        top = (im.height - nh) // 2
        im = im.crop((0, top, im.width, top + nh))
    return im.resize((W, H), Image.Resampling.LANCZOS)


def encode_txp(original, rgb):
    # MEDIANCUT + Floyd-Steinberg: 작은 PSP 화면에서 그라데이션 밴딩을 줄인다.
    q = rgb.quantize(colors=256, method=Image.Quantize.MEDIANCUT,
                     dither=Image.Dither.FLOYDSTEINBERG)
    pal = q.getpalette()[:256 * 3]
    pal += [0] * (256 * 3 - len(pal))
    rgba = bytearray()
    for i in range(256):
        rgba += bytes((pal[i * 3], pal[i * 3 + 1], pal[i * 3 + 2], 255))
    indices = bytes(q.getdata())
    assert len(indices) == W * H
    out = original[:0x10] + bytes(rgba) + indices
    assert len(out) == len(original) == 131600
    return out, q.convert('RGB')


def main(make_iso=False):
    pack_src = 'build_jp/TXPPACK.DAT' if os.path.exists('build_jp/TXPPACK.DAT') else 'jp/TXPPACK.DAT'
    pack = open(pack_src, 'rb').read()
    ents = scriptpack.unpack(pack)
    ent = next(e for e in ents if e['name'] == MEMBER)

    src = Image.open(SOURCE_PNG)
    fitted = fit(src)
    new, preview = encode_txp(ent['data'], fitted)
    ent['data'] = new

    packed = scriptpack.pack(ents)
    assert len(packed) == len(pack), f'TXPPACK 크기 변경 {len(pack)}->{len(packed)}'
    os.makedirs('build_jp', exist_ok=True)
    open('build_jp/TXPPACK.DAT', 'wb').write(packed)
    preview.save('build_jp/title_kr_preview.png')
    print(f'{MEMBER}: 한국어 타이틀 480x272 / 8bpp 256색 / 크기 {len(new):,}B')
    print(f'TXPPACK: {len(packed):,}B (기반 {pack_src}, 크기 불변)')
    print('미리보기: build_jp/title_kr_preview.png')

    if make_iso:
        dst = os.environ.get('D2_ISO_DST', 'build_jp/D2_JP_KR.iso')
        r = isopatch.replace(dst, 25, b'TXPPACK.DAT', packed,
                             slot_lba=TXPPACK_LBA,
                             slot_sectors=TXPPACK_NEXT - TXPPACK_LBA)
        assert r['where'] == '제자리'
        print(f"ISO 갱신: {dst} TXPPACK -> {r['where']}, {r['size']:,}B")


if __name__ == '__main__':
    main('--iso' in sys.argv)
