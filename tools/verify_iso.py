# -*- coding: utf-8 -*-
"""빌드된 ISO를 되읽어 정적 검증 — 폰트/맵/문자열/무손상 전부 확인"""
import sys, os, io, struct, glob
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
sys.path.insert(0, HERE)
from nislzs import decompress
from textio import parse
import scriptpack, talkfile, recdat

ISO = os.environ.get('D2_ISO_DST', 'build_jp/D2_JP_KR.iso')


def build_decoder():
    """게임 바이트 -> 사람이 읽을 문자열"""
    m = {}
    # 한글
    for line in open('build_jp/hangul_codes.tsv', encoding='utf-8').read().splitlines()[1:]:
        ch, c1, c2, i, g = line.split('\t')
        m[bytes([int(c1, 16), int(c2, 16)])] = ch
    # 이전 보존분 (가나 + 기호)
    for line in open('build_jp/moved_codes.tsv', encoding='utf-8').read().splitlines()[1:]:
        c1, c2, o, nw = line.split('\t')
        b = bytes([int(c1, 16), int(c2, 16)])
        for e in ('cp932', 'shift_jis'):
            try:
                m.setdefault(b.decode(e), None) or m.setdefault(b, b.decode(e))
                break
            except Exception:
                pass
    # 제자리 보존 (lead 0x81)
    for c2 in range(0x40, 0x100):
        if c2 == 0x7f:
            continue
        b = bytes([0x81, c2])
        for e in ('cp932', 'shift_jis'):
            try:
                m.setdefault(b, b.decode(e))
                break
            except Exception:
                pass

    def dec(raw):
        out = ''
        i = 0
        while i < len(raw):
            if raw[i] < 0x80:
                out += chr(raw[i]); i += 1
            else:
                q = raw[i:i + 2]
                v = m.get(q)
                if v is None:
                    try:
                        v = q.decode('cp932')
                    except Exception:
                        v = '·'
                out += v; i += 2
        return out
    return dec


def read_iso_file(f, dir_lba, name):
    f.seek(dir_lba * 2048)
    d = f.read(2048)
    p = d.find(name)
    rec = p - 33
    lba = struct.unpack_from('<I', d, rec + 2)[0]
    size = struct.unpack_from('<I', d, rec + 10)[0]
    f.seek(lba * 2048)
    return f.read(size), lba, size


def main():
    dec = build_decoder()
    f = open(ISO, 'rb')
    ok = True

    # --- START (폰트 + UI 문자열) ---
    lzs, lba, size = read_iso_file(f, 25, b'START_JP.LZS')
    raw = decompress(lzs)
    n = struct.unpack('<I', raw[:4])[0]
    ents = []
    for i in range(n):
        o = 0x10 + i * 0x20
        ents.append((struct.unpack('<I', raw[o:o + 4])[0] + 0x2b0,
                     raw[o + 4:o + 0x20].split(b'\0')[0].decode('latin1')))
    order = sorted(range(n), key=lambda k: ents[k][0])
    mem = {}
    for k, i in enumerate(order):
        off, nm = ents[i]
        end = ents[order[k + 1]][0] if k + 1 < n else len(raw)
        mem[nm] = raw[off:end]
    print(f'START_JP.LZS  lba {lba} size {size}  -> 멤버 {len(mem)}개')

    # 수정 대상만 바뀌고 나머지 무손상인지
    orig = open('jp/START_JP.bin', 'rb').read()
    on = struct.unpack('<I', orig[:4])[0]
    oe = []
    for i in range(on):
        o = 0x10 + i * 0x20
        oe.append((struct.unpack('<I', orig[o:o + 4])[0] + 0x2b0,
                   orig[o + 4:o + 0x20].split(b'\0')[0].decode('latin1')))
    oo = sorted(range(on), key=lambda k: oe[k][0])
    omem = {}
    for k, i in enumerate(oo):
        off, nm = oe[i]
        end = oe[oo[k + 1]][0] if k + 1 < on else len(orig)
        omem[nm] = orig[off:end]
    mods = {'fontB.ftd', 'FontB0000.txp', 'talk00.dat', 'fontB.fnt',
            'script00.dat', 'InProgramTxtDB.dat', 'sys2.txp'} | set(recdat.SPEC)
    for nm in omem:
        same = omem[nm] == mem.get(nm)
        if nm in mods and same and nm != 'InProgramTxtDB.dat':
            print(f'  !! {nm}: 변경 안됨'); ok = False
        if nm not in mods and not same:
            print(f'  !! {nm}: 손상'); ok = False
    print('  START 무손상 검증: ' + ('OK' if ok else 'FAIL'))

    sc = mem['script00.dat']
    cnt, ptrs = parse(sc)
    print(f'  script00 문자열 {cnt}건')
    for sid in (0x000, 0x077, 0x394, 0x2a9, 0x3e4):
        q = ptrs[sid]; e = sc.index(b'\0', q)
        print(f'    {sid:#05x}  {dec(sc[q:e])}')

    # --- 캐릭터 DB (sys2.txp) ---
    sd = mem['sys2.txp']
    scnt = struct.unpack('<I', sd[:4])[0]
    S, FLD = 0xF6, 0x17
    print(f'  sys2.txp(캐릭터DB) {scnt}레코드')
    for i in (0, 1, 3, 7, 400):
        nm = sd[8+i*S:8+i*S+FLD].split(bytes(1))[0]
        cl = sd[8+i*S+FLD:8+i*S+2*FLD].split(bytes(1))[0]
        print(f'    [{i:3d}] {dec(nm):16s} | {dec(cl)}')

    # --- ISO 루트 CHAR.DAT (대화창 화자 이름표의 실제 출처) ---
    cd, clba, csize = read_iso_file(f, 25, b'CHAR.DAT')
    ccnt = struct.unpack_from('<I', cd, 0)[0]
    assert 8 + ccnt * 0x102 == len(cd), 'CHAR.DAT 구조 불일치'
    expected_char = 'build_jp/CHAR.DAT'
    same_char = os.path.exists(expected_char) and cd == open(expected_char, 'rb').read()
    jp_mama = cd.count('ママ'.encode('cp932'))
    print(f'  CHAR.DAT(이름표) lba {clba} / {ccnt}레코드 / '
          f'빌드 일치 {same_char} / ママ 잔존 {jp_mama}')
    if not same_char or jp_mama:
        print('  !! CHAR.DAT 주입 누락 또는 일본어 이름 잔존')
        ok = False

    # --- 고정 레코드 DB 6종: 내용이 실제로 한글인지 되읽어 확인 ---
    #     무손상 검사만으로는 "바뀌었다"까지만 알 수 있고 무엇으로 바뀌었는지는 모른다.
    #     한글 '비율'로는 판정할 수 없다. mitem.dat 은 곡 제목이 순 ASCII(`BGM01`,
    #     `Wonder Castle`)라 한글이 0%인 필드가 106개나 정상적으로 존재한다.
    #     진짜 결함은 **글리프를 지운 한자가 남아 있는 것**이므로 그것을 센다.
    #     선행바이트: 0x81=보존기호, 0x84/0x87=이전한 가나, 0xF0~0xFC=한글.
    #     그 사이(0x88~0xEF)는 전부 지운 한자 영역이다.
    def kanji_left(raw):
        i = 0
        while i < len(raw):
            b = raw[i]
            if 0x88 <= b <= 0xEF:
                return True
            i += 2 if (0x81 <= b <= 0x9f or 0xe0 <= b <= 0xfc) else 1
        return False

    # ★ 문자열 영역 **밖**의 무손상 검사 — 한글 표시가 정상이어도 여기가 깨질 수 있다.
    #   실제로 선언 폭을 넉넉히 잡아 아이템 DB 의 무기 종류·사거리를 전부 0 으로
    #   지운 채 배포했고, 증상은 "무기를 껴도 공격이 안 된다" 였다.
    for nm in recdat.SPEC:
        hdr, rs, flds = recdat.SPEC[nm]
        o = open('jp/start/' + nm, 'rb').read()
        b = mem[nm]
        cnt = recdat.count(o)
        touched = bytearray(len(o))
        for i in range(cnt):
            for off, w in flds:
                cap = recdat.capacity(nm, o, i, off)
                base = hdr + i * rs + off
                for k in range(base, base + cap + 1):
                    touched[k] = 1
        hurt = sum(1 for k in range(min(len(o), len(b)))
                   if o[k] != b[k] and not touched[k])
        if hurt or len(o) != len(b):
            print(f'  !! {nm}: 문자열 영역 밖 {hurt}바이트 손상 (바이너리 필드 파괴)')
            ok = False

    for nm in recdat.SPEC:
        it = recdat.items(nm, mem[nm])
        kor = [raw for *_, raw in it
               if any(0xF0 <= raw[i] <= 0xFC for i in range(0, max(0, len(raw) - 1)))]
        bad = [raw for *_, raw in it if kanji_left(raw)]
        print(f'  {nm:14s} 필드 {len(it):5d}개 / 한글 {len(kor):5d}개 / 한자잔존 {len(bad)}개')
        if bad:
            ok = False
            for raw in bad[:3]:
                print(f'    !! {dec(raw)}')
        for raw in kor[:2]:
            print(f'      {dec(raw)}')

    # --- SCRIPTPACK (대사) ---
    sp, lba2, size2 = read_iso_file(f, 25, b'SCRIPTPACK.DAT')
    ents2 = scriptpack.unpack(sp)
    print(f'\nSCRIPTPACK.DAT  lba {lba2} size {size2}  -> 멤버 {len(ents2)}개')
    t = [e for e in ents2 if e['name'] == 'talk01_jp.dat'][0]
    ss = talkfile.strings(t['data'])
    ko = [s for _, s in ss if any(0xF0 <= s[i] <= 0xFC for i in range(0, len(s) - 1))]
    print(f'  talk01_jp.dat 문자열 {len(ss)}개 / 한글 포함 {len(ko)}개')
    for s in ko[:5]:
        print(f'    {dec(s)}')
    # 오프셋 정합성: 마지막 레코드가 파일 끝 근처를 가리키는지
    info = talkfile.parse(t['data'])
    last = info['table_end'] + info['offs'][-1]
    print(f'  오프셋 정합성: 마지막 레코드 {last:#x} / 파일 {len(t["data"]):#x} '
          f'(차이 {len(t["data"])-last})')

    print('\n=== ' + ('전체 검증 OK' if ok else '문제 발견') + ' ===')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
