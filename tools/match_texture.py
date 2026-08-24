# -*- coding: utf-8 -*-
"""RAM 에서 뜬 텍스처 픽셀(`work/sign_atlas.raw`)의 원본 파일을 ISO 에서 찾는다.

규격(가로x세로)만으로 찾으려다 실패했으므로 **바이트 내용으로** 역추적한다.
아카이브를 재귀로 풀어(LZS / NISPACK / START / ANM) 각 후보 안에서 덤프의
선두 조각을 찾는다. 스위즐 여부와 무관하게 맞도록 원본 순서 그대로 비교한다.

사용:
    python tools/match_texture.py work/sign_atlas.raw
    python tools/match_texture.py work/sign_atlas.raw --probe 4096
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
import nislzs
import scriptpack

S = 2048


def probe_of(px, n):
    """0 이 아닌 실제 픽셀이 섞인 구간을 찾아 지문으로 쓴다.
    텍스트 아틀라스는 앞부분이 전부 0(투명)이라 선두를 그냥 쓰면 오탐한다."""
    best, bi = -1, 0
    for i in range(0, max(1, len(px) - n), n):
        seg = px[i:i + n]
        nz = sum(1 for b in seg if b)
        if nz > best:
            best, bi = nz, i
    return px[bi:bi + n], bi, best


def containers(blob, depth=0):
    """(라벨, 데이터) 를 재귀로 낸다"""
    yield '', blob
    if depth >= 3:
        return
    try:
        u = nislzs.decompress(blob)
        if len(u) > len(blob):
            for lbl, sub in containers(u, depth + 1):
                yield '[LZS]' + lbl, sub
            blob = u
    except Exception:
        pass
    try:
        if blob[:8] == b'NISPACK\0':
            for e in scriptpack.unpack(blob):
                for lbl, sub in containers(e['data'], depth + 1):
                    yield '::' + e['name'] + lbl, sub
    except Exception:
        pass


def iso_files(path):
    f = open(path, 'rb')

    def rd(lba, n=1):
        f.seek(lba * S)
        return f.read(n * S)
    pvd = rd(16)
    root = pvd[156:156 + 34]
    rl = struct.unpack('<I', root[2:6])[0]
    rs = struct.unpack('<I', root[10:14])[0]
    out = []

    def walk(lba, size, pre):
        d = rd(lba, (size + S - 1) // S)
        i = 0
        while i < size:
            L = d[i]
            if L == 0:
                i = (i // S + 1) * S
                continue
            r = d[i:i + L]
            fl = r[25]
            nl = r[32]
            nm = r[33:33 + nl]
            el = struct.unpack('<I', r[2:6])[0]
            es = struct.unpack('<I', r[10:14])[0]
            if not (nl == 1 and nm in (b'\x00', b'\x01')):
                n = nm.decode('latin1').split(';')[0]
                p = pre + '/' + n
                if fl & 2:
                    walk(el, es, p)
                else:
                    out.append((p, el, es))
            i += L
    walk(rl, rs, '')
    f.close()
    return out


def main():
    raw = open(sys.argv[1], 'rb').read()
    n = 4096
    if '--probe' in sys.argv:
        n = int(sys.argv[sys.argv.index('--probe') + 1])
    probe, at, nz = probe_of(raw, n)
    print('덤프 %d B / 지문 %d B (오프셋 %#x, 0아닌 바이트 %d개)' % (len(raw), n, at, nz))
    if nz == 0:
        print('★ 지문이 전부 0 이다 — 더 큰 --probe 로 다시 시도하라')
        return 1

    iso = os.environ.get('D2_ISO_SRC',
                         '../Makai Senki Disgaea 2 Portable (Japan) (PSP) (PSN).iso')
    files = iso_files(iso)
    f = open(iso, 'rb')
    found = []
    for path, lba, size in files:
        if size == 0 or size > 200 * 1024 * 1024:
            continue
        f.seek(lba * S)
        blob = f.read(size)
        for lbl, sub in containers(blob):
            p = sub.find(probe)
            if p >= 0:
                found.append((path + lbl, p, len(sub)))
                print('★ %s  +%#x  (컨테이너 %d B)' % (path + lbl, p, len(sub)))
    f.close()
    if not found:
        print('\n일치 없음 — 원본이 다른 방식으로 저장돼 있거나(런타임 생성) '
              '압축 계층이 더 깊다.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
