# -*- coding: utf-8 -*-
"""START_VM 문자열 패치 — 이름 풀/의회/도감/죄상

★ 루트 `NAME.DAT` 를 번역해도 화면은 안 바뀐다(그쪽은 미사용/다른 용도).
  게임이 쓰는 풀은 START_VM_JP.LZS 를 해제한 이미지 안에 있다.
  전투 준비 화면에 `ムサシ` `ハミルトン` `ジスカ` 가 그대로 나온 것이 이것.

★★ 이 파일에는 NUL 종단 이름과, VM 명령 사이에 박힌 **고정폭 문자열**이 섞여 있다.
예전 빌더는 `원문 + NUL`만 찾아 도감 설명의 중간 조각과 죄상명이 일본어로 남았다.
둘 다 원래 바이트 길이를 유지해야 한다. NUL 종단 문자열의 여백은 NUL, 고정폭
문자열의 여백은 ASCII 공백으로 채워 뒤의 VM 명령 바이트를 보존한다.
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

    original = open('jp/START_VM_JP.bin', 'rb').read()
    raw = bytearray(original)
    hits = 0
    nul_hits = 0
    fixed_hits = 0
    over = []
    # 긴 키부터 처리한다. 짧은 직업명/종족명이 도감 장문 안에도 들어 있으므로
    # 사전 순서대로 처리하면 긴 문자열을 먼저 훼손할 수 있다.
    encoded = []
    for jp, ko in T.items():
        jb = jp.encode('cp932')
        kb = krtext.encode(ko)
        if len(kb) > len(jb):
            over.append((jp, ko, len(jb), len(kb)))
            continue
        encoded.append((len(jb), jp, jb, kb))
    for _size, jp, jb, kb in sorted(encoded, reverse=True):
        i = 0
        while True:
            j = raw.find(jb, i)
            if j < 0:
                break
            # 이미 더 긴 키의 번역으로 덮인 영역에는 원문 jb가 남지 않으므로,
            # 여기 도달한 위치는 독립 문자열/조각이다.
            is_nul = j + len(jb) < len(original) and original[j + len(jb)] == 0
            pad = len(jb) - len(kb)
            filler = bytes(pad) if is_nul else b' ' * pad
            raw[j:j + len(jb)] = kb + filler
            hits += 1
            if is_nul:
                nul_hits += 1
            else:
                fixed_hits += 1
            i = j + len(jb)
    if over:
        print(f'!! 원문 바이트 초과 {len(over)}건 — 축약 필요')
        for jp, ko, a, b in over:
            print(f'   {jp} -> {ko}  {a}B -> {b}B')
        raise SystemExit(1)
    print(f'START_VM 문자열 {hits}개 제자리 치환 '
          f'(NUL {nul_hits}, 고정폭 {fixed_hits}, 크기 불변 {len(raw):,}B)')

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
