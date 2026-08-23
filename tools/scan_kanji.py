# -*- coding: utf-8 -*-
"""빌드된 ISO 전체에서 '글리프를 지운 한자'가 남은 문자열을 전수 검출

폰트에서 한자 셀을 전부 지웠으므로, 게임이 한자 코드를 그리려 하면 빈칸/깨진 글자가 된다.
번역 커버리지가 100% 여도 (a) 인벤토리에 안 잡힌 문자열, (b) 다른 포맷의 문자열이
남아 있을 수 있어 바이트 수준에서 직접 훑는다.

선행바이트 배치:
  0x81            보존 기호
  0x84 / 0x87     이전한 가나·기호 (krfont.MOVE_LEADS)
  0x88 ~ 0xEF     지운 한자 영역  <- 여기가 남으면 결함
  0xF0 ~ 0xFC     한글
"""
import sys, os, io, struct
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
sys.path.insert(0, HERE)
from nislzs import decompress
import scriptpack, talkfile, recdat, textio

ISO = 'build_jp/D2_JP_KR.iso'
KANJI_LO, KANJI_HI = 0x88, 0xEF


def has_kanji(raw):
    i = 0
    while i < len(raw):
        b = raw[i]
        if KANJI_LO <= b <= KANJI_HI:
            return True
        i += 2 if (0x81 <= b <= 0x9f or 0xe0 <= b <= 0xfc) else 1
    return False


def dec(raw):
    """한자는 cp932 로, 나머지는 대충 읽어서 사람이 알아볼 수 있게"""
    out = []
    i = 0
    while i < len(raw):
        b = raw[i]
        if 0x20 <= b < 0x7f:
            out.append(chr(b)); i += 1
        elif (0x81 <= b <= 0x9f or 0xe0 <= b <= 0xfc) and i + 1 < len(raw):
            two = raw[i:i + 2]
            if KANJI_LO <= b <= KANJI_HI:
                try: out.append('【' + two.decode('cp932') + '】')   # 문제 문자 강조
                except Exception: out.append(f'[{two.hex()}]')
            else:
                out.append('·')
            i += 2
        else:
            out.append('.'); i += 1
    return ''.join(out)


def read_iso_file(f, dir_lba, name):
    f.seek(dir_lba * 2048)
    d = f.read(2048)
    p = d.find(name)
    rec = p - 33
    lba = struct.unpack_from('<I', d, rec + 2)[0]
    size = struct.unpack_from('<I', d, rec + 10)[0]
    f.seek(lba * 2048)
    return f.read(size)


def main():
    f = open(ISO, 'rb')
    total = 0

    # --- START 아카이브 ---
    raw = decompress(read_iso_file(f, 25, b'START_JP.LZS'))
    n = struct.unpack('<I', raw[:4])[0]
    ents = [(struct.unpack_from('<I', raw, 0x10 + i * 0x20)[0] + 0x2b0,
             raw[0x10 + i * 0x20 + 4:0x10 + i * 0x20 + 0x20].split(b'\0')[0].decode('latin1'))
            for i in range(n)]
    order = sorted(range(n), key=lambda k: ents[k][0])
    mem = {}
    for k, i in enumerate(order):
        off, nm = ents[i]
        end = ents[order[k + 1]][0] if k + 1 < n else len(raw)
        mem[nm] = raw[off:end]

    for nm in recdat.SPEC:
        bad = [r for *_, r in recdat.items(nm, mem[nm]) if has_kanji(r)]
        if bad:
            total += len(bad)
            print(f'{nm}: {len(bad)}건')
            for r in bad[:5]: print(f'    {dec(r)}')

    sc = mem['script00.dat']
    cnt, ptrs = textio.parse(sc)
    bad = []
    for q in ptrs:
        e = sc.index(b'\0', q)
        if has_kanji(sc[q:e]): bad.append(sc[q:e])
    if bad:
        total += len(bad)
        print(f'script00.dat: {len(bad)}건')
        for r in bad[:5]: print(f'    {dec(r)}')

    for nm in ('InProgramTxtDB.dat',):
        bad = [r for _, r in talkfile.strings(mem[nm]) if has_kanji(r)]
        if bad:
            total += len(bad)
            print(f'{nm}: {len(bad)}건')
            for r in bad[:5]: print(f'    {dec(r)}')

    sd = mem['sys2.txp']
    S, FLD = 0xF6, 0x17
    scnt = struct.unpack('<I', sd[:4])[0]
    bad = []
    for i in range(scnt):
        for off in (0, FLD):
            b = 8 + i * S + off
            r = sd[b:b + FLD].split(bytes(1))[0]
            if r and has_kanji(r): bad.append(r)
    if bad:
        total += len(bad)
        print(f'sys2.txp: {len(bad)}건')
        for r in bad[:5]: print(f'    {dec(r)}')

    # --- SCRIPTPACK (talk) ---
    for e in scriptpack.unpack(read_iso_file(f, 25, b'SCRIPTPACK.DAT')):
        if not talkfile.parse(e['data']):
            continue
        bad = [r for _, r in talkfile.strings(e['data']) if has_kanji(r)]
        if bad:
            total += len(bad)
            print(f"{e['name']}: {len(bad)}건")
            for r in bad[:5]: print(f'    {dec(r)}')

    # --- CHAR.DAT ---
    cd = read_iso_file(f, 25, b'CHAR.DAT')
    f.close()

    print(f'\n한자 잔존 총 {total}건')
    return 1 if total else 0


if __name__ == '__main__':
    sys.exit(main())
