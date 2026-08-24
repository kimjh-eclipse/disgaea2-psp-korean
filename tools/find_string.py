# -*- coding: utf-8 -*-
"""ISO 안의 모든 파일을 재귀로 풀어(LZS·NISPACK) 지정한 문자열을 찾는다.

"파일에 없다" 는 결론을 낼 때 **압축·아카이브를 다 풀었는지** 확인하기 위한 도구.
지명 간판(`ホルルト村`)을 못 찾았다고 결론냈던 것이 실은 패치 대상 파일만 본
결과였다. 없다는 결론은 전수 탐색으로만 낼 수 있다.

사용:
    python tools/find_string.py <ISO> "ホルルト"
    python tools/find_string.py <ISO> "ホルルト" --raw   (ISO 원본 섹터도 통째로)
"""
import io
import os
import struct
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nislzs

S = 2048


def iso_files(path):
    """[(경로, lba, size)] — 디렉터리 제외"""
    f = open(path, 'rb')

    def rd(lba, n=1):
        f.seek(lba * S)
        return f.read(n * S)

    pvd = rd(16)
    assert pvd[1:6] == b'CD001', 'ISO9660 아님'
    root = pvd[156:156 + 34]
    rl = struct.unpack('<I', root[2:6])[0]
    rs = struct.unpack('<I', root[10:14])[0]
    out = []

    def walk(lba, size, prefix):
        data = rd(lba, (size + S - 1) // S)
        i = 0
        while i < size:
            L = data[i]
            if L == 0:
                i = (i // S + 1) * S
                continue
            rec = data[i:i + L]
            flags = rec[25]
            nlen = rec[32]
            name = rec[33:33 + nlen]
            elba = struct.unpack('<I', rec[2:6])[0]
            esz = struct.unpack('<I', rec[10:14])[0]
            if not (nlen == 1 and name in (b'\x00', b'\x01')):
                nm = name.decode('latin1').split(';')[0]
                p = prefix + '/' + nm
                if flags & 2:
                    walk(elba, esz, p)
                else:
                    out.append((p, elba, esz))
            i += L

    walk(rl, rs, '')
    f.close()
    return out


def try_lzs(b):
    """LZS 로 풀리면 풀린 데이터, 아니면 None"""
    if len(b) < 16:
        return None
    try:
        d = nislzs.decompress(b)
        return d if len(d) > len(b) // 2 else None
    except Exception:
        return None


def try_nispack(b):
    """NISPACK 이면 [(이름, 데이터)], 아니면 None"""
    if b[:8] != b'NISPACK\0':
        return None
    try:
        n = struct.unpack_from('<I', b, 0x0C)[0]
        if not (0 < n < 5000):
            return None
        out = []
        for i in range(n):
            o = 0x10 + i * 0x20
            name = b[o:o + 0x18].split(b'\0')[0].decode('latin1', 'replace')
            off, size = struct.unpack_from('<II', b, o + 0x18)
            if off + size <= len(b):
                out.append((name, b[off:off + size]))
        return out or None
    except Exception:
        return None


def try_start(b):
    """START 형식(u32 count + 0x20 엔트리, +0x2B0 보정)이면 [(이름, 데이터)]"""
    if len(b) < 0x20:
        return None
    try:
        n = struct.unpack_from('<I', b, 0)[0]
        if not (0 < n < 4000) or 0x10 + n * 0x20 > len(b):
            return None
        ents = []
        for i in range(n):
            o = 0x10 + i * 0x20
            off = struct.unpack_from('<I', b, o)[0] + 0x2B0
            nm = b[o + 4:o + 0x20].split(b'\0')[0].decode('latin1', 'replace')
            if not nm or off > len(b):
                return None
            ents.append((off, nm))
        order = sorted(range(n), key=lambda k: ents[k][0])
        out = []
        for k, i in enumerate(order):
            off, nm = ents[i]
            end = ents[order[k + 1]][0] if k + 1 < n else len(b)
            out.append((nm, b[off:end]))
        return out
    except Exception:
        return None


def search(needles, blob, where, hits, depth=0):
    for enc, pat in needles:
        p = 0
        while True:
            p = blob.find(pat, p)
            if p < 0:
                break
            hits.append((where, enc, p, blob[max(0, p - 24):p + len(pat) + 24]))
            p += 1
    if depth >= 3:
        return
    # 재귀: LZS -> NISPACK -> START
    d = try_lzs(blob)
    if d is not None:
        search(needles, d, where + ' [LZS]', hits, depth + 1)
        blob2 = d
    else:
        blob2 = blob
    for tag, fn in (('NISPACK', try_nispack), ('START', try_start)):
        mem = fn(blob2)
        if mem:
            for nm, sub in mem:
                search(needles, sub, f'{where} [{tag}::{nm}]', hits, depth + 1)
            break


def main():
    iso = sys.argv[1]
    text = sys.argv[2]
    needles = []
    for enc in ('cp932', 'shift_jis', 'utf-16-le', 'utf-8'):
        try:
            b = text.encode(enc)
            if all(b != x for _, x in needles):
                needles.append((enc, b))
        except Exception:
            pass
    print('찾는 문자열: %r' % text)
    for enc, b in needles:
        print('   %-10s %s' % (enc, b.hex()))
    files = iso_files(iso)
    print('\nISO 파일 %d개 탐색\n' % len(files))
    f = open(iso, 'rb')
    hits = []
    for path, lba, size in files:
        if size == 0 or size > 200 * 1024 * 1024:
            continue
        f.seek(lba * S)
        blob = f.read(size)
        n0 = len(hits)
        search(needles, blob, path, hits)
        if len(hits) > n0:
            print('  %-28s %+d건' % (path, len(hits) - n0))
    f.close()
    print('\n=== 총 %d건 ===' % len(hits))
    for where, enc, off, ctx in hits[:40]:
        try:
            t = ctx.decode('cp932', 'replace')
        except Exception:
            t = repr(ctx)
        print('  %-46s %-8s +%#x  %r' % (where, enc, off, t))


if __name__ == '__main__':
    main()
