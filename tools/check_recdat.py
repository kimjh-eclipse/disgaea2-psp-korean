# -*- coding: utf-8 -*-
"""고정 레코드 DB 무손상 검사 — 문자열 뒤 바이너리가 살아 있는지 확인한다.

이 검사가 없어서 아이템 DB(HABIT.dat)의 무기 종류·사거리·공격력을 전부 0 으로
지운 채 배포했다. 증상은 "무기를 껴도 공격이 안 된다" 였고, **번역률·한글 표시·
부팅 확인으로는 절대 드러나지 않는다.** 화면에 보이는 것은 문자열뿐이기 때문이다.

두 가지를 본다.
  1) 선언 폭 검사 — SPEC 의 폭 안에 바이너리가 들어 있지 않은가
     (원본에서 문자열 NUL 뒤에 0 아닌 바이트가 있으면 그 폭은 과대 선언이다)
  2) 빌드 무손상 검사 — 원본 대비 **문자열 영역 밖의 바이트가 한 개도 변하지
     않았는가**. 이것이 본 검사의 핵심이다.

사용:
    python tools/check_recdat.py                 # jp/start vs build_jp
    python tools/check_recdat.py <원본dir> <빌드dir>
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
import recdat


def true_width(data, hdr, rs, off, w, n):
    """원본에서 관측한 안전 폭 = (문자열 최대길이+1) .. (꼬리 데이터 최소위치) 중 최대"""
    max_str, min_data = 0, w
    for i in range(n):
        f = data[hdr + i * rs + off:hdr + i * rs + off + w]
        e = f.find(0)
        if e < 0:
            max_str = max(max_str, w)
            continue
        max_str = max(max_str, e + 1)
        for j in range(e + 1, w):
            if f[j]:
                min_data = min(min_data, j)
                break
    return max_str, min_data


def main(src_dir='jp/start', dst_dir='build_jp'):
    ok = True
    for name, (hdr, rs, fields) in recdat.SPEC.items():
        sp = os.path.join(src_dir, name)
        dp = os.path.join(dst_dir, name)
        if not (os.path.exists(sp) and os.path.exists(dp)):
            print(f'  {name:14s} 건너뜀 (파일 없음)')
            continue
        o = open(sp, 'rb').read()
        b = open(dp, 'rb').read()
        n = recdat.count(o)
        if len(o) != len(b):
            print(f'  !! {name}: 크기 변경 {len(o)} -> {len(b)}')
            ok = False
            continue

        # (1) 선언 폭이 바이너리를 먹고 있지 않은가
        for off, w in fields:
            max_str, min_data = true_width(o, hdr, rs, off, w, n)
            if w > min_data:
                print(f'  !! {name} +{off:#04x}: 선언폭 {w} > 꼬리데이터 위치 {min_data}'
                      f' — 바이너리를 침범한다 (안전폭 {min_data})')
                ok = False
            elif max_str > w:
                print(f'  !! {name} +{off:#04x}: 선언폭 {w} < 최대문자열 {max_str}')
                ok = False

        # (2) 문자열 영역 밖 무손상 — 핵심 검사
        #     레코드마다 "이 필드가 실제로 쓸 수 있는 범위" 밖은 원본과 같아야 한다.
        touched = bytearray(len(o))
        for i in range(n):
            for off, w in fields:
                cap = recdat.capacity(name, o, i, off)
                base = hdr + i * rs + off
                for k in range(base, base + cap + 1):   # +1 = 종단 NUL
                    touched[k] = 1
        bad = [k for k in range(len(o)) if o[k] != b[k] and not touched[k]]
        if bad:
            ok = False
            print(f'  !! {name}: 문자열 영역 밖 {len(bad)}바이트 손상')
            for k in bad[:6]:
                i = (k - hdr) // rs
                print(f'       off {k:#x} (rec{i} +{(k - hdr) % rs:#x})'
                      f'  {o[k]:#04x} -> {b[k]:#04x}')
        else:
            print(f'  {name:14s} 레코드 {n:5d}  문자열 영역 밖 무손상 OK')
    print('\n=== ' + ('고정 레코드 DB 검사 OK' if ok else '★ 문제 발견') + ' ===')
    return 0 if ok else 1


if __name__ == '__main__':
    a = sys.argv[1:]
    sys.exit(main(*a) if a else main())
