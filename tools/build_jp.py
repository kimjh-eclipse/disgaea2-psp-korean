"""JP 베이스 한글 패치 빌드 (재현 가능)
사용: python tools/build_jp.py [--iso]
"""
import sys,os,struct,csv,shutil,io
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
HERE=os.path.dirname(os.path.abspath(__file__))
ROOT=os.path.dirname(HERE)
sys.path.insert(0,HERE)
os.chdir(ROOT)
from nislzs import compress,decompress
from rebuild import rebuild_start
from textio2 import rebuild as rebuild_block
import talkfile, glob as _glob, importlib.util as _ilu
import krtext, recdat

def fixed_cell_text(text):
    """2바이트 고정 셀 렌더러용 문자열.

    magic.dat의 직업/캐릭터 설명 화면은 한 글자를 2바이트씩 읽는다.
    ASCII가 섞이면 다음 한글의 첫 바이트와 한 쌍이 되어 글리프가 깨지므로
    공백과 ASCII 인쇄 문자를 Shift-JIS 전각 문자로 바꾼다.
    """
    out=[]
    for ch in text:
        code=ord(ch)
        if ch == ' ':
            out.append('\u3000')
        elif 0x21 <= code <= 0x7e:
            out.append(chr(code + 0xfee0))
        else:
            out.append(ch)
    return ''.join(out)


def patch_eboot_aptitude_names(blob):
    """캐릭터 생성 화면이 직접 참조하는 EBOOT 내 소질명 5단계를 번역한다.

    각 항목은 이름 22바이트 + 수치 4바이트의 0x1A바이트 레코드다.
    script00에도 같은 문구가 있지만 이 선택 화면은 그 복제본을 사용하지 않는다.
    """
    names = (
        ('どうしようもないクズ', '답 없는 쓰레기'),
        ('おちこぼれ', '낙오자'),
        ('平凡', '평범'),
        ('優秀', '우수'),
        ('極めて優秀', '극히 우수'),
        ('天才', '천재'),
    )
    out = bytearray(blob)
    anchor = names[0][0].encode('cp932')
    base = bytes(out).find(anchor)
    if base < 0 or bytes(out).find(anchor, base + 1) >= 0:
        raise SystemExit('EBOOT 소질명 배열 기준 위치 불일치')
    starts = []
    for index, (old, new) in enumerate(names):
        old_raw = old.encode('cp932')
        at = base + index * 0x1a
        field = bytes(out[at:at + 22]).split(b'\0', 1)[0]
        if field != old_raw:
            raise SystemExit(f'EBOOT 소질명 레코드 불일치: {old!r} @ {at:#x}')
        new_raw = krtext.encode(new)
        if len(new_raw) > 22:
            raise SystemExit(f'EBOOT 소질명 필드 초과: {old} -> {new}')
        # 원문 뒤의 NUL 패딩까지만 교체하여 바로 뒤 4바이트 수치를 보존한다.
        out[at:at + 22] = new_raw + bytes(22 - len(new_raw))
        starts.append(at)
    return bytes(out), names, starts

# START_JP 를 249886 으로 민 최종 레이아웃 — 전량 전각화 SCRIPTPACK(3,484,323B)에 자리를 내준다.
# build_talk.ISO_NEXT 와 같아야 한다. 패치된 EBOOT(talk 버퍼 0x36000) 전제.
JP_ISO_LBA, JP_ISO_NEXT = 249886, 252272
SLOT=(JP_ISO_NEXT-JP_ISO_LBA)*2048

def load_edits(path):
    out={}
    with open(path,encoding='utf-8') as f:
        for row in csv.DictReader(f,delimiter='\t'):
            ko=row['ko'].strip()
            # 공용 조사처럼 의도적으로 문자열 자체를 제거해야 하는 항목.
            # 빈 TSV 셀은 미번역과 구별되지 않으므로 명시적 표식을 사용한다.
            if ko == '<EMPTY>':
                out[int(row['id'],16)]=''
            elif ko:
                out[int(row['id'],16)]=ko
    return out

def main(make_iso=False):
    # 1) 문자열 패치
    edits=load_edits('work/ko_script00.tsv')
    sc0=open('jp/start/script00.dat','rb').read()
    sc,cnt=rebuild_block(sc0,edits,krtext.encode)
    sc+=bytes(8)                    # 원본 말미 정렬 패딩 유지 (NUL x8)
    applied=[(sid,len(krtext.encode(ko)),ko) for sid,ko in edits.items()]
    print(f'  블록 크기 {len(sc0)} -> {len(sc)} ({len(sc)-len(sc0):+d}B)')
    open('build_jp/script00.dat','wb').write(sc)
    print(f'script00: {len(applied)}건 패치')
    if len(applied)<=12:
        for sid,b,ko in applied: print(f'   id {sid:#05x} {b:3d}B  {ko}')
    # 1-B) InProgramTxtDB (talk 포맷) 패치
    ipt=open('jp/start/InProgramTxtDB.dat','rb').read()
    T={}
    for bp in sorted(_glob.glob('work/tr_iptxt*.py')):
        sp=_ilu.spec_from_file_location('b',bp); mm=_ilu.module_from_spec(sp)
        sp.loader.exec_module(mm); T.update(mm.T)
    if T:
        # talk 와 같은 렌더러(고정 바이트 오프셋 줄자르기)이므로 대사 전각화 필수
        FW_MAP={' ':'　','.':'．',',':'，','!':'！','?':'？','~':'～',
                ':':'：',';':'；','(':'（',')':'）','-':'－','/':'／'}
        for _n in range(10): FW_MAP[chr(0x30+_n)]=chr(0xFF10+_n)
        for _n in range(26):
            FW_MAP[chr(0x41+_n)]=chr(0xFF21+_n)
            FW_MAP[chr(0x61+_n)]=chr(0xFF41+_n)
        fw=lambda t:''.join(FW_MAP.get(c,c) for c in t)
        # ASCII 물음표 등은 의도적으로 빈 글리프라서 원문 번역표 상태로
        # validate 하면 정상 번역까지 실패한다. 실제 기록값(전각화 후)을 검사한다.
        bad=[(k,krtext.validate(fw(v))) for k,v in T.items() if krtext.validate(fw(v))]
        if bad:
            print(f'!! InProgramTxtDB 인코딩 불가 {len(bad)}건')
            for k,b in bad[:8]: print(f'   {"".join(b)} : {T[k]}')
            raise SystemExit(1)
        enc={jp.encode('cp932'):krtext.encode(fw(ko)) for jp,ko in T.items()}
        edits={off:enc[raw] for off,raw in talkfile.strings(ipt) if raw in enc}
        ipt_new=talkfile.rebuild(ipt,edits)
        print(f'InProgramTxtDB: {len(edits)}회 적용 (고유 {len(T)}건), 크기 {len(ipt)}->{len(ipt_new)}')
    else:
        ipt_new=ipt
        print('InProgramTxtDB: 번역 없음 (원본 유지)')
    open('build_jp/InProgramTxtDB.dat','wb').write(ipt_new)

    # 1-C) sys2.txp = 실제로는 캐릭터 DB (500 x 0xF6, 이름/직업 각 0x17)
    #      대사창 이름표의 실제 출처. CHAR.DAT 를 고쳐도 여기가 안 바뀌면 원문이 남는다.
    CT={}
    for bp in sorted(_glob.glob('work/tr_char*.py')):
        sp=_ilu.spec_from_file_location('c',bp); mm=_ilu.module_from_spec(sp)
        sp.loader.exec_module(mm); CT.update(mm.T)
    sd=bytearray(open('jp/start/sys2.txp','rb').read())
    S,FLD=0xF6,0x17
    scnt=struct.unpack('<I',sd[:4])[0]
    assert 8+scnt*S==len(sd), 'sys2.txp 구조 불일치'
    hit=0; miss=set(); over=[]
    for i in range(scnt):
        for off in (0,FLD):
            base=8+i*S+off
            raw=bytes(sd[base:base+FLD]).split(bytes(1))[0]
            if not raw: continue
            try: jp=raw.decode('cp932')
            except Exception: continue
            ko=CT.get(jp)
            if ko is None: miss.add(jp); continue
            b=krtext.encode(ko)
            if len(b)>FLD: over.append((jp,ko,len(b))); continue
            sd[base:base+FLD]=b+bytes(FLD-len(b)); hit+=1
    if over:
        print(f'!! sys2 필드 초과 {len(over)}건'); [print(f'   {a}->{b} ({c}B)') for a,b,c in over[:8]]
        raise SystemExit(1)
    print(f'sys2.txp(캐릭터DB): {hit}회 적용, 미번역 {len(miss)}종')
    if miss: [print(f'   미번역: {x}') for x in list(miss)[:8]]
    open('build_jp/sys2.txp','wb').write(bytes(sd))

    # 1-D) 고정 레코드 DB 6종 (기술·무기명 / 이노센트 / 마법설명 / 의제 / 음악)
    #      필드 폭이 고정이므로 파일 크기는 변하지 않는다. 초과분은 recdat.put 이 막는다.
    RT={}
    for bp in sorted(_glob.glob('work/tr_rec*.py')):
        sp=_ilu.spec_from_file_location('r',bp); mm=_ilu.module_from_spec(sp)
        sp.loader.exec_module(mm); RT.update(mm.T)
    rec_names=[]
    for nm in recdat.SPEC:
        data=open('jp/start/'+nm,'rb').read()
        edits={}; miss=set(); over=[]
        for i,off,w,rawb in recdat.items(nm,data):
            try: jp=rawb.decode('cp932')
            except UnicodeDecodeError: continue
            if not any(ord(c)>0x7f for c in jp): continue
            ko=RT.get(jp)
            if ko is None: miss.add(jp); continue
            # magic.dat 설명은 2바이트 고정 셀 렌더러를 사용한다.
            # 일반 ASCII를 그대로 넣으면 바이트 경계가 어긋나 이후 글리프가 깨진다.
            stored_ko=fixed_cell_text(ko) if nm.lower()=='magic.dat' else ko
            b=krtext.encode(stored_ko)
            # ★ 예산은 선언 폭이 아니라 **레코드별 실제 용량**이다.
            #   문자열 뒤가 바이너리인 필드가 있어서(HABIT/dungeon/mitem) 폭을
            #   그대로 쓰면 무기 종류·사거리를 덮어쓴다. recdat.capacity 주석 참고.
            cap=recdat.capacity(nm,data,i,off)
            if len(b)>cap: over.append((jp,ko,len(b),cap)); continue
            edits[(i,off)]=b
        if over:
            print(f'!! {nm} 예산 초과 {len(over)}건')
            for a,b,c,d in over[:40]: print(f'   {a} -> {b} ({c}B > {d}B)')
            raise SystemExit(1)
        new=recdat.put(nm,data,edits)
        assert len(new)==len(data), f'{nm} 크기 변경'
        open('build_jp/'+nm,'wb').write(new)
        rec_names.append(nm)
        print(f'{nm:14s} {len(edits):5d}회 적용, 미번역 {len(miss)}종')

    # 1-E) ISO 루트 DUNGEON.DAT (스테이지·지명 165개) — 스테이지 선택 화면 이름 목록.
    #      ★ 거점 진입 시 나오는 지명 간판(이미지)의 출처가 아니다 — 그건 별개로
    #      ANMPACK/anm7151.dat 아틀라스다(tools/build_signatlas.py, GE 디버거로 확인).
    #      이 파일과는 무관하니 그대로 번역해 넣는다.
    import build_dungeon as _bd
    _bd.main(False)

    # 2) START 재빌드
    ov={nm:open('build_jp/'+nm,'rb').read() for nm in
        ('fontB.ftd','FontB0000.txp','talk00.dat','fontB.fnt','script00.dat',
         'InProgramTxtDB.dat','sys2.txp')+tuple(rec_names)}
    raw=rebuild_start('jp/START_JP.bin',ov)
    c=compress(raw,0xd5)
    assert decompress(c)==raw, 'LZS 검증 실패'
    # 비중첩 제약
    flag=c[12]; s=16; bad=0
    while s<len(c)-2:
        if c[s]==flag and c[s+1]!=flag:
            x,cn=c[s+1],c[s+2]; disp=x-1 if x>flag else x
            if cn>disp: bad+=1
            s+=3
        elif c[s]==flag: s+=2
        else: s+=1
    assert bad==0, f'비중첩 제약 위반 {bad}건'
    open('build_jp/START_JP.LZS','wb').write(c)
    print(f'START_JP.LZS {len(c)}B / 슬롯 {SLOT}B  ({100*len(c)/SLOT:.1f}%)')
    assert len(c)<=SLOT, '슬롯 초과'
    # 3) ISO
    if make_iso:
        import glob
        src=glob.glob('../Makai*Disgaea*.iso')[0]
        dst=os.environ.get('D2_ISO_DST', 'build_jp/D2_JP_KR.iso')
        if not os.path.exists(dst): shutil.copyfile(src,dst)
        # LBA 도 갱신해야 한다 — START_JP 를 자기 영역 뒤쪽으로 옮기기 때문.
        # 예전 코드는 크기만 고쳐서, LBA 를 바꾸면 게임이 엉뚱한 섹터를 읽게 된다.
        import isopatch
        r=isopatch.replace(dst, 25, b'START_JP.LZS', c,
                           slot_lba=JP_ISO_LBA, slot_sectors=JP_ISO_NEXT-JP_ISO_LBA)
        assert r['where']=='제자리', f"슬롯 안에 들어가야 한다: {r['where']}"
        print(f"ISO 갱신: START_JP -> LBA {r['lba']}, {r['size']}B")
        # ★ 'build_jp/DUNGEON.DAT' 로 쓰면 Windows 파일시스템이 대소문자를 구분하지
        #   않아 START 멤버 'build_jp/dungeon.dat'(8,016B, 완전히 다른 파일)와
        #   충돌한다. build_dungeon.py 가 이 충돌을 피해 DUNGEON_root.DAT 로 쓴다.
        rd = isopatch.replace(dst, 25, b'DUNGEON.DAT',
                              open('build_jp/DUNGEON_root.DAT', 'rb').read())
        print(f"ISO 갱신: DUNGEON.DAT(스테이지·지명 165) {rd['size']:,}B")

        # ★ 패치 EBOOT 주입 — 이 레이아웃의 필수 전제.
        #   build_jp/EBOOT_KR.BIN = PPSSPP DumpDecryptedEboots 산출물에
        #   talk 버퍼 9워드(0x18F8->0x6000) 등을 패치한 평문 ELF.
        #
        #   ★★ 예전에는 이 평문 ELF 를 그대로 넣어서 **PPSSPP 전용**이었다.
        #   시놀부님이 주신 type-1(~PSP, tag C0CB167C) 재암호화 스크립트
        #   (tools/psp_prx_type1.py)로 원본 헤더를 재사용해 다시 암호화하면
        #   서명 검사를 통과하는 EBOOT 이 나온다.
        #
        #   PPSSPP 덤프는 진짜 원본 ELF 뒤에 348B 가 더 붙어 있다(덤프 아티팩트).
        #   원본 복호 길이로 잘라 넣는다 — 검증: 원본복호 == PPSSPP덤프[:원본길이].
        ebp='build_jp/EBOOT_KR.BIN'
        if not os.path.exists(ebp):
            print('!! EBOOT_KR.BIN 없음 — 이 레이아웃은 패치 EBOOT 필수. 빌드 중단')
            raise SystemExit(1)
        eb=open(ebp,'rb').read()
        assert eb[:4]==b'ELF', 'EBOOT_KR.BIN 이 ELF 가 아니다'
        eb, aptitude_names, aptitude_offsets = patch_eboot_aptitude_names(eb)
        print('EBOOT 소질명: ' + ', '.join(new for _old,new in aptitude_names))
        print('EBOOT 소질명 위치: ' + ', '.join(f'{x:#x}' for x in aptitude_offsets))
        from psp_prx_type1 import encrypt_prx, decrypt_prx
        orig_enc=open('jp/EBOOT_orig_enc.BIN','rb').read()
        limit=len(decrypt_prx(orig_enc))
        assert len(eb)>=limit, 'ELF 가 원본 한도보다 짧다'
        cut=len(eb)-limit
        enc=encrypt_prx(eb[:limit], orig_enc)
        assert enc[:4]==b'~PSP', '재암호화 결과가 ~PSP 가 아니다'
        assert decrypt_prx(enc)==eb[:limit], 'EBOOT 재암호화 왕복 검증 실패'
        open('build_jp/EBOOT_KR_enc.BIN','wb').write(enc)
        r2=isopatch.replace(dst, 24, b'EBOOT.BIN', enc, slot_lba=32, slot_sectors=832-32)
        assert r2['where']=='제자리'
        print(f"ISO 갱신: EBOOT.BIN(재암호화 ~PSP, 덤프꼬리 {cut}B 절단) {r2['size']:,}B")
    from code_sync import write_stamp
    print(f'START 코드표 동기화: {write_stamp("START")[:16]}')
    return raw

if __name__=='__main__':
    main('--iso' in sys.argv)
