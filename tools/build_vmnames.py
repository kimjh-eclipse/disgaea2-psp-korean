# -*- coding: utf-8 -*-
"""범용 유닛 이름 풀 — 실제 출처는 `START_VM_JP.LZS` 안이다

★ 루트 `NAME.DAT` 를 번역해도 화면은 안 바뀐다(그쪽은 미사용/다른 용도).
  게임이 쓰는 풀은 START_VM_JP.LZS 를 해제한 이미지 안의 **NUL 종단 가변길이 문자열 블롭**.
  전투 준비 화면에 `ムサシ` `ハミルトン` `ジスカ` 가 그대로 나온 것이 이것.

블롭에 오프셋 테이블이 딸려 있으므로 **각 이름의 바이트 길이를 유지**해야 한다.
번역이 짧으면 남는 자리는 NUL 로 채운다(게임은 NUL 종단으로 읽으므로 무해).
길이를 넘는 12건은 미리 축약해 두었다(work/tr_names_*.py 주석 참고).

사용: python tools/build_vmnames.py [--iso]
"""
import sys, os, io, glob, importlib.util
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
sys.path.insert(0, HERE)
import krtext, isopatch
from nislzs import compress, decompress

LBA, NEXT = 253024, 253712          # START_VM_JP.LZS 슬롯
SLOT = (NEXT - LBA) * 2048


def main(make_iso=False):
    T = {}
    for p in sorted(glob.glob('work/tr_names_*.py')):
        spec = importlib.util.spec_from_file_location('n', p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        T.update(m.T)
        print(f'  {os.path.basename(p)}: {len(m.T)}건')

    raw = bytearray(open('jp/START_VM_JP.bin', 'rb').read())
    hits = 0
    over = []
    for jp, ko in T.items():
        jb = jp.encode('cp932')
        kb = krtext.encode(ko)
        if len(kb) > len(jb):
            over.append((jp, ko, len(jb), len(kb)))
            continue
        pat = jb + b'\0'
        rep = kb + bytes(len(jb) - len(kb) + 1)      # 길이 동일, 남는 자리 NUL
        assert len(pat) == len(rep)
        i = 0
        while True:
            j = raw.find(pat, i)
            if j < 0:
                break
            raw[j:j + len(pat)] = rep
            hits += 1
            i = j + len(pat)
    if over:
        print(f'!! 원문 바이트 초과 {len(over)}건 — 축약 필요')
        for jp, ko, a, b in over[:10]:
            print(f'   {jp} -> {ko}  {a}B -> {b}B')
        raise SystemExit(1)
    print(f'이름 {hits}개 제자리 치환 (크기 불변 {len(raw):,}B)')

    c = compress(bytes(raw), 0xd5)
    assert decompress(c) == bytes(raw), 'LZS 검증 실패'
    # 비중첩 제약 (게임 디코더 요구)
    flag = c[12]; s = 16; bad = 0
    while s < len(c) - 2:
        if c[s] == flag and c[s + 1] != flag:
            x, cn = c[s + 1], c[s + 2]
            disp = x - 1 if x > flag else x
            if cn > disp:
                bad += 1
            s += 3
        elif c[s] == flag:
            s += 2
        else:
            s += 1
    assert bad == 0, f'비중첩 제약 위반 {bad}건'
    print(f'START_VM_JP.LZS {len(c):,}B / 슬롯 {SLOT:,}B ({100*len(c)/SLOT:.1f}%)')
    assert len(c) <= SLOT, '슬롯 초과'
    open('build_jp/START_VM_JP.LZS', 'wb').write(c)

    if make_iso:
        dst = os.environ.get('D2_ISO_DST', 'build_jp/D2_JP_KR.iso')
        r = isopatch.replace(dst, 25, b'START_VM_JP.LZS', c,
                             slot_lba=LBA, slot_sectors=NEXT - LBA)
        assert r['where'] == '제자리'
        print(f"ISO 갱신: START_VM_JP.LZS -> {r['where']}, {r['size']:,}B")
    from code_sync import write_stamp
    print(f'START_VM 코드표 동기화: {write_stamp("START_VM")[:16]}')


if __name__ == '__main__':
    main('--iso' in sys.argv)
