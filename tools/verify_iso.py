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
import krtext
import audit_zukan

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
    from code_sync import require_synced
    require_synced('font', 'START', 'SCRIPTPACK', 'NAME', 'START_VM', 'CHAR')
    dec = build_decoder()
    f = open(ISO, 'rb')
    ok = True

    # 캐릭터 생성 소질명은 script00과 EBOOT에 각각 한 벌씩 있다.
    # 실제 선택 화면은 EBOOT의 24바이트 고정 필드를 참조하므로 양쪽을 모두 검사한다.
    eboot_enc, eboot_lba, eboot_size = read_iso_file(f, 24, b'EBOOT.BIN')
    from psp_prx_type1 import decrypt_prx
    eboot_dec = decrypt_prx(eboot_enc)
    from patch_class_description_effect import patch as verify_class_effect
    verify_class_effect(eboot_dec, verify_only=True)
    from patch_class_title_width import patch as verify_title_width
    verify_title_width(eboot_dec, verify_only=True)
    from patch_ascii_space import patch as verify_spaces
    verify_spaces(eboot_dec, verify_only=True)
    print('공통 ASCII 공백: 15px -> 7px / 비공백 글리프 변경 없음 OK')
    print('직업 상세 제목: 원래 글자 크기 1.0 / 시작 X 47,133 복원 OK')
    print('직업 설명문: 본문 유지 / 밝은 외곽선 복원 / 좌우 폭 1px OK')
    aptitude_jp = ('どうしようもないクズ', 'おちこぼれ', '平凡', '優秀', '極めて優秀', '天才')
    aptitude_ko = ('답 없는 쓰레기', '낙오자', '평범', '우수', '극히 우수', '천재')
    eboot_left = [s for s in aptitude_jp if s.encode('cp932') in eboot_dec]
    eboot_missing = [s for s in aptitude_ko if krtext.encode(s) not in eboot_dec]
    print(f'EBOOT.BIN      lba {eboot_lba} size {eboot_size} / '
          f'소질명 일본어 {len(eboot_left)} / 한글 누락 {len(eboot_missing)}')
    if eboot_left or eboot_missing:
        ok = False
        for s in eboot_left:
            print(f'  !! EBOOT 일본어 소질명: {s}')
        for s in eboot_missing:
            print(f'  !! EBOOT 한글 소질명 누락: {s}')

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

    # --- 코드표 의존 루트 이름 풀 ---
    # DLC 폰트 갱신 때 START/SCRIPTPACK만 다시 만들고 이 둘을 빠뜨려, 새 게임의
    # 범용 유닛 이름부터 깨진 회귀가 있었다. ISO 안의 실물을 빌드본과 직접 비교한다.
    name_dat, name_lba, name_size = read_iso_file(f, 25, b'NAME.DAT')
    name_expected = open('build_jp/NAME.DAT', 'rb').read()
    name_same = name_dat == name_expected
    print(f'NAME.DAT       lba {name_lba} size {name_size} / 빌드 일치 {name_same}')
    if not name_same:
        ok = False

    vm_lzs, vm_lba, vm_size = read_iso_file(f, 25, b'START_VM_JP.LZS')
    vm_expected = open('build_jp/START_VM_JP.LZS', 'rb').read()
    vm_raw = decompress(vm_lzs)
    vm_same = vm_lzs == vm_expected and vm_raw == decompress(vm_expected)
    print(f'START_VM_JP    lba {vm_lba} size {vm_size} / 이름 풀 빌드 일치 {vm_same}')
    if not vm_same:
        ok = False

    # START_VM에는 NUL 종단 이름과 VM 명령 사이의 고정폭 문장이 함께 있다.
    # 예전 빌더가 고정폭 필드를 건너뛰어 도감·의회·죄상에 일본어가 남았으므로,
    # 실제 ISO를 풀어 해당 회귀 문구가 없는지 별도로 확인한다.
    vm_forbidden = (
        '専門職として認められている', '人見知りもいるようだ',
        'あるが、この呼称', '夢はばたく議員', 'オーク太郎議員',
        'ＨＰ多すぎの罪', 'ダメージ与えすぎの罪',
        '病院部屋', 'プチオーク部屋', 'オーク界賊団',
        'ゴースト変化', '虹レンジャー変化',
    )
    vm_left = [s for s in vm_forbidden if s.encode('cp932') in vm_raw]
    vm_expected_ko = ('인정받고 있다', '낯가림도 있는 듯하다',
                      '꿈나래 의원', 'ＨＰ 과다죄', '과도한 데미지의 죄',
                      '병원 방', '프티오크 방', '오크 해적단 아지트',
                      '고스트 변신', '니지레인저 변신')
    vm_missing = [s for s in vm_expected_ko if krtext.encode(s) not in vm_raw]
    print(f'  START_VM 회귀검사: 일본어 잔존 {len(vm_left)} / 한글 누락 {len(vm_missing)}')
    if vm_left or vm_missing:
        for s in vm_left:
            print(f'    !! 일본어 잔존: {s}')
        for s in vm_missing:
            print(f'    !! 한글 누락: {s}')
        ok = False

    # 캐릭터 도감 tower.dat의 제목·설명 351개를 원문 단위로 전수 대조한다.
    # 대표 문자열 몇 개만 검사하면 `戦士♂`처럼 한자 글리프가 빈칸으로 보이는
    # 짧은 목록명이 다시 빠질 수 있다.
    if audit_zukan.main():
        ok = False

    sc = mem['script00.dat']
    cnt, ptrs = parse(sc)
    print(f'  script00 문자열 {cnt}건')
    script_forbidden = ('どうしようもないクズ', 'おちこぼれ')
    script_left = [s for s in script_forbidden if s.encode('cp932') in sc]
    script_expected = ('답 없는 쓰레기', '낙오자')
    script_missing = [s for s in script_expected if krtext.encode(s) not in sc]
    print(f'  소질명 회귀검사: 일본어 잔존 {len(script_left)} / 한글 누락 {len(script_missing)}')
    if script_left or script_missing:
        ok = False
        for s in script_left:
            print(f'    !! 일본어 잔존: {s}')
        for s in script_missing:
            print(f'    !! 한글 누락: {s}')
    class_labels = {0x23a: '장비적성', 0x23b: '기본능력'}
    for sid, expected in class_labels.items():
        q = ptrs[sid]
        e = sc.index(b'\0', q)
        actual = dec(sc[q:e])
        print(f'  캐릭터 상세 제목 {sid:#05x}: {actual}')
        if actual != expected:
            print(f'    !! 예상값: {expected}')
            ok = False
    # 아이템명은 직전 표시 명령이 따로 출력한다. 조사 병기는 이 렌더러에서
    # `을(`만 남으므로 0x028은 조사 없는 완결 문장이어야 한다.
    q028 = ptrs[0x028]
    e028 = sc.index(b'\0', q028)
    text028 = dec(sc[q028:e028])
    print(f'  아이템 획득 문구: {text028}')
    if text028 != '손에 넣었다！！':
        print('    !! 아이템 획득 문구 회귀')
        ok = False
    q0b8 = ptrs[0x0b8]
    e0b8 = sc.index(b'\0', q0b8)
    text0b8 = dec(sc[q0b8:e0b8])
    print(f'  아이템 획득 조사 조각: {text0b8!r}')
    if text0b8 != '':
        print('    !! 아이템 획득 조사 조각이 비어 있지 않음')
        ok = False
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
    expected_char = 'build_jp/CHAR_root.DAT'
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
        if nm == 'magic.dat':
            # 이 화면은 한 글자를 2바이트 고정 셀로 읽는다. 한 바이트 ASCII가
            # 하나라도 있으면 다음 한글과 결합되어 깨진 글리프가 된다.
            ascii_cells = []
            for *_, raw in it:
                pos = 0
                while pos < len(raw):
                    if raw[pos] < 0x80:
                        ascii_cells.append(raw)
                        break
                    pos += 2
            print(f'      고정 셀 ASCII 잔존 {len(ascii_cells)}개')
            if ascii_cells:
                ok = False
                for raw in ascii_cells[:3]:
                    print(f'    !! 고정 셀 불일치: {dec(raw)}')
            record = {off: raw for i, off, _w, raw in it if i == 41}
            expected = {
                0x00: '최전선에서　활약하는　파워　파이터．',
                0x32: '높은　체력과　공격력을　갖췄다．',
                0x64: '위기에　빠지면　크리티컬　데미지가　ＵＰ．',
            }
            for off, text in expected.items():
                actual = dec(record.get(off, b''))
                print(f'      직업 설명 41/{off:#04x}: {actual}')
                if actual != text:
                    ok = False
                    print(f'    !! 예상값: {text}')

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

    # 이 렌더러는 ASCII 대괄호 한 바이트 뒤부터 문자열 경계를 잃어 제목 끝에
    # H/w 같은 후행 바이트를 노출한다. 모든 talk를 되읽어 대표 튜토리얼 문구가
    # 정상 동작이 확인된 【】로 패킹됐는지 검사한다.
    talk_texts = []
    for ent in ents2:
        if ent['name'].startswith('talk'):
            talk_texts.extend(dec(s) for _, s in talkfile.strings(ent['data']))
    tutorial_expected = (
        '【튜토리얼　아이템계란？】',
        '【튜토리얼　【이노센트】를　찾아라！】',
        '좋은　주민은　【이노센트】라고　불려．',
    )
    tutorial_missing = [s for s in tutorial_expected if s not in talk_texts]
    tutorial_ascii = [s for s in talk_texts if '튜토리얼' in s and ('[' in s or ']' in s)]
    print(f'  튜토리얼 괄호 회귀검사: 누락 {len(tutorial_missing)} / ASCII 괄호 {len(tutorial_ascii)}')
    if tutorial_missing or tutorial_ascii:
        ok = False
        for s in tutorial_missing:
            print(f'    !! 정상 문구 누락: {s}')
        for s in tutorial_ascii[:3]:
            print(f'    !! ASCII 괄호 잔존: {s}')
    # 오프셋 정합성: 마지막 레코드가 파일 끝 근처를 가리키는지
    info = talkfile.parse(t['data'])
    last = info['table_end'] + info['offs'][-1]
    print(f'  오프셋 정합성: 마지막 레코드 {last:#x} / 파일 {len(t["data"]):#x} '
          f'(차이 {len(t["data"])-last})')

    print('\n=== ' + ('전체 검증 OK' if ok else '문제 발견') + ' ===')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
