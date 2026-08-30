# -*- coding: utf-8 -*-
"""CHAR.DAT 캐릭터명·클래스명 번역 적용 -> ISO 주입

포맷: u32 count(396) x2 + record[396] x 0x102
        +0x00 char[0x17] 이름 / +0x17 char[0x17] 직업
필드가 고정 폭이라 23바이트(한글 11자) 초과 불가.
"""
import sys, os, io, glob, struct, shutil, importlib.util
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
sys.path.insert(0, HERE)
import krtext, isopatch

COUNT_OFF, STRIDE, FLD = 8, 0x102, 0x17
ISO_LBA, ISO_SECTORS = 260448, 50          # CHAR.DAT 슬롯 (102,176B -> 50섹터)


def load_batches():
    T = {}
    for p in sorted(glob.glob('work/tr_char*.py')):
        spec = importlib.util.spec_from_file_location('b', p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        T.update(m.T)
        print(f'  {os.path.basename(p)}: {len(m.T)}건')
    return T


def main(make_iso=False):
    T = load_batches()
    bad = [(k, krtext.validate(v)) for k, v in T.items() if krtext.validate(v)]
    if bad:
        print(f'!! 인코딩 불가 {len(bad)}건')
        for k, b in bad[:10]:
            print(f'   {"".join(b)} : {T[k]}')
        raise SystemExit(1)

    d = bytearray(open('jp/CHAR.DAT', 'rb').read())
    cnt = struct.unpack('<I', d[:4])[0]
    assert COUNT_OFF + cnt * STRIDE == len(d), '구조 불일치'

    applied = 0
    missing = set()
    over = []
    for i in range(cnt):
        for off in (0, FLD):
            base = COUNT_OFF + i * STRIDE + off
            raw = bytes(d[base:base + FLD]).split(b'\0')[0]
            if not raw:
                continue
            try:
                jp = raw.decode('cp932')
            except Exception:
                continue
            ko = T.get(jp)
            if ko is None:
                missing.add(jp)
                continue
            b = krtext.encode(ko)
            if len(b) > FLD:
                over.append((jp, ko, len(b)))
                continue
            d[base:base + FLD] = b + bytes(FLD - len(b))
            applied += 1
    if over:
        print(f'!! 필드 초과 {len(over)}건 (최대 {FLD}B)')
        for jp, ko, n in over[:10]:
            print(f'   {jp} -> {ko} ({n}B)')
        raise SystemExit(1)
    print(f'적용 {applied}회 / 미번역 원문 {len(missing)}종')
    if missing:
        for s in list(missing)[:10]:
            print(f'   미번역: {s}')
    assert len(d) == len(open('jp/CHAR.DAT', 'rb').read()), '크기 변경됨'
    open('build_jp/CHAR_root.DAT', 'wb').write(bytes(d))
    print(f'build_jp/CHAR_root.DAT 저장 ({len(d)}B, 크기 동일)')

    if make_iso:
        dst = os.environ.get('D2_ISO_DST', 'build_jp/D2_JP_KR.iso')
        if not os.path.exists(dst):
            shutil.copyfile(glob.glob('../Makai*Disgaea*.iso')[0], dst)
        r = isopatch.replace(dst, 25, b'CHAR.DAT', bytes(d),
                             slot_lba=ISO_LBA, slot_sectors=ISO_SECTORS)
        print(f"ISO 갱신: CHAR.DAT -> {r['where']}, {r['size']}B")
    from code_sync import write_stamp
    print(f'CHAR 코드표 동기화: {write_stamp("CHAR")[:16]}')


if __name__ == '__main__':
    main('--iso' in sys.argv)
