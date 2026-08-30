# -*- coding: utf-8 -*-
"""범용 유닛 기본 이름 풀(루트 NAME.DAT) 번역 적용 -> ISO 주입

포맷 (규명 2026-08-23)
  +0x00  u16 x4  그룹 카운트 (206,206,206,206)
  +0x08  u16     그룹 카운트 (86)          -> 합 910
  +0x0A  u16 x910  블롭 상대 오프셋 (블롭 = +0x726)
  +0x726 NUL 종단 SJIS 이름 x910

인게임 증상: 개그 이름의 한자 글리프가 지워져 `の１２` 처럼 깨져 보였고,
카타카나 이름(ゼリク 등)은 일본어 그대로 노출됐다.

번역: work/tr_names_*.py.  이름은 한글/전각만(2바이트 정렬 안전) + 16B 이하.
오프셋 테이블을 새로 계산하므로 블롭이 커져도 된다(슬롯 32,768B).

사용: python tools/build_names.py [--iso]
"""
import sys, os, io, glob, struct, importlib.util
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
sys.path.insert(0, HERE)
import krtext, isopatch

BLOB = 0x726
COUNT = 910
LBA, NEXT = 248080, 248096          # NAME.DAT 슬롯 (다음 파일 NISGFX.DAT)


def main(make_iso=False):
    T = {}
    for p in sorted(glob.glob('work/tr_names_*.py')):
        spec = importlib.util.spec_from_file_location('n', p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        T.update(m.T)
        print(f'  {os.path.basename(p)}: {len(m.T)}건')

    d = open('jp/NAME.DAT', 'rb').read()
    offs = [struct.unpack_from('<H', d, 0x0A + 2 * i)[0] for i in range(COUNT)]
    names = []
    for o in offs:
        s = BLOB + o
        names.append(d[s:d.index(b'\0', s)].decode('cp932'))

    miss = sorted({n for n in names if n not in T})
    if miss:
        print(f'!! 미번역 {len(miss)}건: {miss[:8]}')
        raise SystemExit(1)

    # 새 블롭 + 오프셋 (중복 이름은 오프셋 공유)
    blob = bytearray()
    where = {}
    new_offs = []
    for n in names:
        ko = T[n]
        b = krtext.encode(ko)
        assert len(b) <= 16, f'16B 초과: {ko}'
        # ★ 바이트로 ASCII 를 판정하면 안 된다 — 전각 ！(0x8149) 처럼 트레일 바이트가
        #   ASCII 범위(0x49)인 2바이트 문자가 오탐된다. 문자 단위로 본다.
        assert not any(0x20 <= ord(c) < 0x7f for c in ko), f'ASCII 혼입: {ko}'
        if b not in where:
            where[b] = len(blob)
            blob += b + b'\0'
        new_offs.append(where[b])
    assert max(new_offs) <= 0xFFFF

    out = bytearray(d[:0x0A])
    for o in new_offs:
        out += struct.pack('<H', o)
    assert len(out) == BLOB, f'테이블 크기 {len(out):#x} != {BLOB:#x}'
    out += blob
    slot = (NEXT - LBA) * 2048
    print(f'NAME.DAT {len(d):,}B -> {len(out):,}B (슬롯 {slot:,}B)')
    assert len(out) <= slot, '슬롯 초과'
    open('build_jp/NAME.DAT', 'wb').write(bytes(out))

    if make_iso:
        dst = os.environ.get('D2_ISO_DST', 'build_jp/D2_JP_KR.iso')
        r = isopatch.replace(dst, 25, b'NAME.DAT', bytes(out),
                             slot_lba=LBA, slot_sectors=NEXT - LBA)
        assert r['where'] == '제자리'
        print(f"ISO 갱신: NAME.DAT -> {r['where']}, {r['size']:,}B")
    from code_sync import write_stamp
    print(f'NAME 코드표 동기화: {write_stamp("NAME")[:16]}')


if __name__ == '__main__':
    main('--iso' in sys.argv)
