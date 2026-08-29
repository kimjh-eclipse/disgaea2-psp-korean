# -*- coding: utf-8 -*-
"""talk 번역 적용 -> SCRIPTPACK.DAT 재패킹 -> ISO 주입

번역 원본: work/tr_talk*.py  (dict T = {'원문일본어': '한글'})
원문 문자열 기준으로 모든 talk 파일의 전 occurrence 에 일괄 적용.
"""
import sys, os, io, glob, struct, shutil, importlib.util, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
sys.path.insert(0, HERE)
import talkfile, scriptpack, krtext, isopatch

# SCRIPTPACK.DAT 슬롯 — 최종 레이아웃 (EBOOT talk 버퍼 패치 전제)
# ★ 진짜 제약은 talk 공용 버퍼였다(원본 0x318F8=203,000B). EBOOT 9워드 패치로
#   0x36000=221,184B 로 확장했으므로 각 talk 멤버는 그 이하이면 된다.
#   전량 전각화 최대 멤버 = talk01 211,619B < 221,184B OK.
# ★ SCRIPTPACK 총 크기·ISO 슬롯 자체에는 상한이 없음이 실증됐다(0 패딩 3.48MB 부팅 OK).
#   다만 START_JP 와 맞닿아 있으므로 경계(249886)는 build_jp.JP_ISO_LBA 와 같아야 한다.
# ★ 이 레이아웃은 반드시 패치된 EBOOT(build_jp/EBOOT_KR.BIN)와 함께 써야 한다.
#   무패치 EBOOT 에서는 멤버가 203,000B 를 넘는 순간 죽는다.
ISO_LBA, ISO_NEXT = 248176, 249886
SLOT = (ISO_NEXT - ISO_LBA) * 2048


def load_batches():
    T = {}
    conflict = []
    for p in sorted(glob.glob('work/tr_talk*.py')):
        spec = importlib.util.spec_from_file_location('b', p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        for k, v in m.T.items():
            if k in T and T[k] != v:
                conflict.append(k)
            T[k] = v
        print(f'  {os.path.basename(p)}: {len(m.T)}건')
    if conflict:
        print(f'!! 배치 간 충돌 {len(conflict)}건: {conflict[:5]}')
    return T


def main(make_iso=False):
    T = load_batches()
    if not T:
        print('번역 배치 없음 (work/tr_talk*.py)')
        return
    # 검증
    bad = [(k, krtext.validate(v)) for k, v in T.items() if krtext.validate(v)]
    if bad:
        print(f'!! 인코딩 불가 {len(bad)}건')
        for k, b in bad[:8]:
            print(f'   {b} : {T[k]}')
        raise SystemExit(1)
    # 전각 ％ 는 양쪽 모두 정규화해야 한다. 한쪽만 하면 원문의 전각 ％ 를 그대로 살린
    # 정상 번역이 불일치로 잡힌다(실제로 겪음).
    _pc = lambda s: s.replace('％', '%').count('%')
    fmt = [(k, v) for k, v in T.items() if _pc(k) != _pc(v)]
    if fmt:
        print(f'!! 서식지정자 개수 불일치 {len(fmt)}건')
        for k, v in fmt[:8]:
            print(f'   JP:{k!r} KO:{v!r}')
        raise SystemExit(1)

    # 원문 -> 바이트
    enc = {}
    for jp, ko in T.items():
        try:
            enc[jp.encode('cp932')] = krtext.encode(ko)
        except Exception as e:
            print(f'!! 원문 인코딩 실패 {jp!r}: {e}')
            raise SystemExit(1)

    ents = scriptpack.unpack(open('jp/SCRIPTPACK.DAT', 'rb').read())
    # 부분 패딩 대상 (검증용). 파일이 없으면 빈 집합 = 패딩 없음.
    PAD = set()
    if os.path.exists('work/pad_keys.txt'):
        for ln in open('work/pad_keys.txt', encoding='utf-8').read().splitlines():
            if ln:
                try: PAD.add(ln.encode('cp932'))
                except Exception: pass
        print(f'부분 패딩 대상 {len(PAD)}건')
    # ★ 전각화 검증 대상 (work/fw_keys.txt).
    #   게임이 문자 경계를 무시하고 고정 바이트 오프셋으로 줄을 자른다. 일본어는 전부
    #   2바이트라 항상 경계에 맞지만, 1바이트 ASCII 가 섞이면 이후 오프셋이 홀수가 되어
    #   자르는 지점이 문자 중간에 떨어진다(작업 버퍼에서 1바이트 밀린 사본을 확인).
    #   -> 대사는 모든 문자가 2바이트여야 한다.
    FW_MAP = {' ': '　', '.': '．', ',': '，', '!': '！',
              '?': '？', '~': '～', ':': '：', ';': '；',
              '(': '（', ')': '）', '-': '－', '/': '／'}
    # 숫자·영문도 1바이트라 정렬을 깨뜨린다. 전각 영숫자 글리프는 bake_font 가
    # 원본에서 복원한다(빈 gid 1757~1818).
    for _n in range(10): FW_MAP[chr(0x30+_n)] = chr(0xFF10+_n)
    for _n in range(26):
        FW_MAP[chr(0x41+_n)] = chr(0xFF21+_n)
        FW_MAP[chr(0x61+_n)] = chr(0xFF41+_n)
    # 기본 = 전 대사 전각화. work/fw_keys.txt 가 있으면 그 목록만(무패치 EBOOT 용 축소 빌드).
    if os.path.exists('work/fw_keys.txt'):
        FW = set()
        for ln in open('work/fw_keys.txt', encoding='utf-8').read().splitlines():
            if ln:
                try: FW.add(ln.encode('cp932'))
                except Exception: pass
        print(f'전각화 대상 {len(FW)}건 (fw_keys.txt)')
    else:
        FW = set(enc)
        print(f'전각화 대상 전체 {len(FW)}건')

    def fullwidth(t):
        return ''.join(FW_MAP.get(c, c) for c in t)

    # ★ 짝수 길이 패딩 검증 대상 (work/even_keys.txt).
    #   손상은 앞선 문자열에서 밀린 오프셋이 누적되어 생긴다. 그렇다면 "모든 문자가
    #   2바이트"까지 필요 없고 "각 문자열의 바이트 길이가 짝수"면 될 수 있다.
    #   전자는 +119KB(슬롯 초과), 후자는 +32KB 로 훨씬 싸다.
    EVEN = set()
    if os.path.exists('work/even_keys.txt'):
        for ln in open('work/even_keys.txt', encoding='utf-8').read().splitlines():
            if ln:
                try: EVEN.add(ln.encode('cp932'))
                except Exception: pass
        print(f'짝수 패딩 대상 {len(EVEN)}건')

    applied = 0
    grown = collections.Counter()
    for e in ents:
        if not e['name'].startswith('talk'):
            continue
        d = e['data']
        edits = {}
        for off, raw in talkfile.strings(d):
            if raw in enc:
                b = enc[raw]
                if raw in FW:
                    b = krtext.encode(fullwidth(T[raw.decode('cp932')]))
                if raw in EVEN and len(b) % 2:
                    b += b' '          # 1바이트 추가로 짝수 맞춤
                # ★ 가설 검증용 부분 패딩.
                #   게임이 NUL 에서 멈추지 않고 줄이 찰 때까지 스트림을 계속 읽어 그리는
                #   것으로 보인다 — 번역이 원문보다 짧으면 그만큼 뒤쪽 바이트코드가
                #   글자로 노출된다(인게임에서 `ww を ％` 와 빈칸으로 확인).
                #   전체에 적용하면 +64,847B 로 슬롯을 넘으므로, work/pad_keys.txt 에
                #   적은 원문만 원문 길이까지 공백으로 채워 먼저 검증한다.
                if raw in PAD and len(b) < len(raw):
                    b += b' ' * (len(raw) - len(b))
                edits[off] = b
        if not edits:
            continue
        new = talkfile.rebuild(d, edits)
        # talk 공용 버퍼(패치 후 0x36000) 초과 방지 — 넘으면 인게임에서 죽는다
        MEMBER_CAP = 0x36000
        if len(new) > MEMBER_CAP:
            raise SystemExit(f"!! {e['name']} {len(new):,}B > 멤버 버퍼 {MEMBER_CAP:,}B")
        grown[e['name']] = len(new) - len(d)
        e['data'] = new
        applied += len(edits)

    # --- script09/16 나레이션 (talk 와 다른 포맷: `32 <len> <SJIS> 00` 인라인) ---
    # 오프셋 테이블 재계산을 피하기 위해 **정확히 같은 바이트 길이**로 제자리 치환한다.
    # 부족분은 전각 공백(8140) 패딩 — 나레이션 문장 끝이라 화면에 안 보인다.
    # 번역: work/tr_script_narr.py (모든 문자 2바이트 검증 완료)
    nspec = importlib.util.spec_from_file_location('narr', 'work/tr_script_narr.py')
    if os.path.exists('work/tr_script_narr.py'):
        nm_ = importlib.util.module_from_spec(nspec); nspec.loader.exec_module(nm_)
        nenc = {}
        for jp, ko in nm_.T.items():
            jb = jp.encode('cp932'); kb = krtext.encode(ko)
            assert len(kb) <= len(jb) and len(kb) % 2 == 0, f'나레이션 길이 위반: {ko}'
            nenc[jb] = kb + bytes([0x81, 0x40]) * ((len(jb) - len(kb)) // 2)
        napp = 0
        for e in ents:
            if not e['name'].startswith('script'):
                continue
            d = bytearray(e['data'])
            for jb, kb in nenc.items():
                i = 0
                while True:
                    j = d.find(jb, i)
                    if j < 0:
                        break
                    # `32 <len>` 프리앰블 + NUL 종단 확인 후 제자리 치환
                    if j >= 2 and d[j-2] == 0x32 and d[j-1] == len(jb)+1 and d[j+len(jb)] == 0:
                        d[j:j+len(jb)] = kb
                        napp += 1
                    i = j + 1
            e['data'] = bytes(d)
        print(f'나레이션(script09/16): {napp}회 적용 (고유 {len(nenc)}건)')

    print(f'적용 {applied}회 (고유 {len(T)}건)')
    tot_growth = sum(grown.values())
    print(f'talk 파일 크기 변화 합계 {tot_growth:+d}B')

    packed = scriptpack.pack(ents)
    print(f'SCRIPTPACK {len(packed)}B (원본 슬롯 {SLOT}B, {100*len(packed)/SLOT:.2f}%)')
    open('build_jp/SCRIPTPACK.DAT', 'wb').write(packed)

    if make_iso:
        dst = os.environ.get('D2_ISO_DST', 'build_jp/D2_JP_KR.iso')
        if not os.path.exists(dst):
            src = glob.glob('../Makai*Disgaea*.iso')[0]
            shutil.copyfile(src, dst)
        # ★ SCRIPTPACK 은 원래 슬롯을 넘기면 안 된다. 넘겨서 ISO 끝으로 재배치했더니
        #   게임이 "Now Loading" 에서 멈췄다 — 이 아카이브를 원래 크기 기준 고정 버퍼로
        #   읽는 것으로 보인다. ISO 헤더(PVD·디렉터리 레코드)는 정상이었는데도 안 됐다.
        #   따라서 재배치로 조용히 넘어가지 말고 여기서 막는다.
        limit = (ISO_NEXT - ISO_LBA) * 2048
        if len(packed) > limit and not os.environ.get('ALLOW_RELOCATE'):
            raise SystemExit(
                f'!! SCRIPTPACK {len(packed)}B > 슬롯 {limit}B — 재배치하면 부팅이 막힌다.\n'
                f'   번역문 바이트를 줄여야 한다(전각 공백/기호를 ASCII 로).')
        r = isopatch.replace(dst, 25, b'SCRIPTPACK.DAT', packed,
                             slot_lba=ISO_LBA, slot_sectors=ISO_NEXT - ISO_LBA)
        if not os.environ.get('ALLOW_RELOCATE'):
            assert r['where'] == '제자리', f"슬롯 안에 들어가야 한다: {r['where']}"
        print(f"ISO 갱신: SCRIPTPACK -> {r['where']}, {r['size']}B")

    from code_sync import write_stamp
    print(f'SCRIPTPACK 코드표 동기화: {write_stamp("SCRIPTPACK")[:16]}')


if __name__ == '__main__':
    main('--iso' in sys.argv)
