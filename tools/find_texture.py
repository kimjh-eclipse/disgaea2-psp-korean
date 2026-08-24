# -*- coding: utf-8 -*-
"""ISO 전체를 재귀로 풀어 지정 규격의 TXP 텍스처를 찾는다.

GE 디버거로 확인한 화면 요소의 실물 파일을 역추적하기 위한 도구.
지명 간판은 텍스트가 아니라 **256x512 8bpp 아틀라스**였다
(CLUT 0x098a6200 -> Texture 0x098a6600, 간격 0x400 = 256색 x 4B).

TXP 헤더 (tools/txp.py 참고)
    +0x00 u16 width
    +0x02 u16 height
    +0x0A u16 pb        팔레트 블록 수 (색 수 = 16 * pb)
    +0x10 팔레트 (색수 x 4B)  그 뒤 픽셀

사용:
    python tools/find_texture.py <ISO> 256 512
    python tools/find_texture.py <ISO> 256 512 --dump <출력디렉터리>
"""
import io
import os
import struct
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from find_string import iso_files, try_lzs, try_nispack, try_start

S = 2048


def txp_head(b):
    """TXP 로 보이면 (w, h, pb, 예상크기) 반환"""
    if len(b) < 0x10:
        return None
    w, h = struct.unpack_from('<HH', b, 0)
    pb = struct.unpack_from('<H', b, 0x0A)[0]
    if not (8 <= w <= 4096 and 8 <= h <= 4096):
        return None
    if pb not in (1, 16):          # 16색(4bpp) / 256색(8bpp)
        return None
    ncol = 16 * pb
    bpp = 4 if pb == 1 else 8
    size = 0x10 + ncol * 4 + w * h * bpp // 8
    return w, h, pb, size


def walk(blob, where, depth, want, out):
    hd = txp_head(blob)
    if hd:
        w, h, pb, size = hd
        if (w, h) == want and abs(len(blob) - size) <= S:
            out.append((where, w, h, pb, len(blob), size, blob))
    if depth >= 3:
        return
    d = try_lzs(blob)
    base = blob
    if d is not None:
        walk(d, where + ' [LZS]', depth + 1, want, out)
        base = d
    for tag, fn in (('NISPACK', try_nispack), ('START', try_start)):
        mem = fn(base)
        if mem:
            for nm, sub in mem:
                walk(sub, f'{where} [{tag}::{nm}]', depth + 1, want, out)
            break


def main():
    iso = sys.argv[1]
    want = (int(sys.argv[2]), int(sys.argv[3]))
    dump = None
    if '--dump' in sys.argv:
        dump = sys.argv[sys.argv.index('--dump') + 1]
        os.makedirs(dump, exist_ok=True)
    files = iso_files(iso)
    f = open(iso, 'rb')
    out = []
    for path, lba, size in files:
        if size == 0 or size > 200 * 1024 * 1024:
            continue
        f.seek(lba * S)
        walk(f.read(size), path, 0, want, out)
    f.close()
    print('%dx%d 텍스처 %d개\n' % (want[0], want[1], len(out)))
    for i, (where, w, h, pb, got, exp, blob) in enumerate(out):
        print('  %-64s %dx%d %dbpp  %d B (예상 %d)'
              % (where[:64], w, h, 4 if pb == 1 else 8, got, exp))
        if dump:
            nm = where.replace('/', '_').replace(' ', '').replace('[', '').replace(']', '')
            p = os.path.join(dump, f'{i:02d}_{nm[-70:]}.txp')
            open(p, 'wb').write(blob)
    if dump:
        print('\n덤프: %s' % dump)


if __name__ == '__main__':
    main()
