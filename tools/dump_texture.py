# -*- coding: utf-8 -*-
"""실행 중인 PPSSPP RAM 에서 GE 디버거가 알려준 텍스처를 떠 온다.

GE 디버거 화면에서 읽은 값을 그대로 넣는다.
    CLUT: 0x098a6200 (3)          -> 3 = 32bit ABGR8888
    Texture L0: 0x098a6600 (256x512)

지명 간판이 **텍스트가 아니라 이미지**임을 GE 로 확인했는데(제보), 규격만으로는
ISO 안에서 원본 파일을 찾지 못했다. 그래서 실물 픽셀을 떠서 그것으로 역추적한다.
`tools/match_texture.py` 가 이 덤프를 아카이브 전체와 대조한다.

전제: ppsspp.ini 의 `RemoteDebuggerOnStartup = True` (이미 켜져 있음), 포트 4543.

사용:
    python tools/dump_texture.py 0x098a6600 256 512 8 --clut 0x098a6200
"""
import argparse
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
sys.path.insert(0, HERE)
from ppsspp_dbg import Dbg


def read_big(dbg, addr, size, chunk=0x8000):
    """memory.read 는 큰 블록에서 실패하므로 쪼개 읽는다"""
    out = bytearray()
    while len(out) < size:
        n = min(chunk, size - len(out))
        out += dbg.read(addr + len(out), n)
        sys.stdout.write('\r  %d / %d B' % (len(out), size))
        sys.stdout.flush()
    print()
    return bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('addr')
    ap.add_argument('width', type=int)
    ap.add_argument('height', type=int)
    ap.add_argument('bpp', type=int, choices=(4, 8))
    ap.add_argument('--clut', default=None)
    ap.add_argument('--out', default='work/sign_atlas')
    ap.add_argument('--no-unswizzle', action='store_true')
    a = ap.parse_args()

    addr = int(a.addr, 16)
    size = a.width * a.height * a.bpp // 8
    dbg = Dbg()
    print('텍스처 %#x  %dx%d %dbpp = %d B' % (addr, a.width, a.height, a.bpp, size))
    px = read_big(dbg, addr, size)
    os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
    open(a.out + '.raw', 'wb').write(px)
    print('저장: %s.raw' % a.out)

    pal = None
    if a.clut:
        ncol = 16 if a.bpp == 4 else 256
        pal = read_big(dbg, int(a.clut, 16), ncol * 4)
        open(a.out + '.pal', 'wb').write(pal)
        print('저장: %s.pal (%d색)' % (a.out, ncol))

    # 미리보기 PNG — 스위즐/논스위즐 둘 다 낸다(파일마다 다르다)
    try:
        from PIL import Image
        import txp
        rowbytes = a.width if a.bpp == 8 else a.width // 2
        variants = [('linear', px)]
        if not a.no_unswizzle:
            variants.append(('unswz', txp.unswizzle(px, rowbytes, a.height)))
        for tag, raw in variants:
            if a.bpp == 8:
                idx = list(raw[:a.width * a.height])
            else:
                idx = []
                for v in raw[:rowbytes * a.height]:
                    idx.append(v & 0xF)
                    idx.append(v >> 4)
            if pal:
                P = [tuple(pal[i * 4:i * 4 + 4]) for i in range(len(pal) // 4)]
                data = [P[v] if v < len(P) else (255, 0, 255, 255) for v in idx]
                im = Image.new('RGBA', (a.width, a.height))
            else:
                data = [(v, v, v, 255) for v in idx]
                im = Image.new('RGBA', (a.width, a.height))
            im.putdata(data[:a.width * a.height])
            im.save(f'{a.out}_{tag}.png')
            print('저장: %s_%s.png' % (a.out, tag))
    except Exception as e:
        print('미리보기 생성 실패:', e)


if __name__ == '__main__':
    main()
