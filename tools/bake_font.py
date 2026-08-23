# -*- coding: utf-8 -*-
"""한글 폰트 베이크 (재현 가능)

배치
  gid   1.. 131 : ASCII + lead 0x81 전각기호/버튼아이콘   (원위치 보존)
  gid 132..2417 : 한글 2286자 (상용 2350 중 실사용 없는 52자 제외)
  gid 2418..2591: 보존 이전분 = 가나 162 + 기호 12 (─ ② Ⅰ 등)

가나를 남기는 이유: 미번역 일본어가 읽히는 상태로 유지 -> 진행 중에도 게임이 정상적으로
보이고, 어디가 미번역인지 한눈에 보인다. 전각영숫자·그리스·키릴은 버린다(ASCII 로 대체).

한글 목록은 현재 번역이 실제 쓰는 음절을 must 로 강제 포함하므로, 번역이 늘면
재실행만으로 자동 반영된다(self-healing).
"""
import sys, os, io, shutil, glob, importlib.util
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
sys.path.insert(0, HERE)
from krfont import (load_page, save_page, wipe, bake, build_tables, bake_ascii,
                    collect_moves, collect_kana, collect_fullwidth_alnum,
                    move_glyphs, move_glyphs_to, rebake_symbols, rebake_cell,
                    n_to_code, code_to_idx, cell_rect,
                    GID_BASE, MOVE_BASE, FULLWIDTH_ALNUM_BASE, HANGUL_LIMIT,
                    CELL, COLS, DIV,
                    FONT_PATH, FONT_INDEX, FONT_SIZE)
import hangul_rank
from PIL import ImageFont


def used_syllables():
    """현재 번역이 실제로 쓰는 한글 음절"""
    # 패턴을 열거하지 말 것. tr_char / tr_iptxt / tr_rec 계열이 추가될 때마다
    # 목록에서 빠져 새 음절이 폰트에 안 들어가는 사고가 두 번 났다. work/tr_*.py 전부 읽는다.
    out = set()
    for p in sorted(glob.glob('work/tr_*.py')):
        spec = importlib.util.spec_from_file_location('b', p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        for v in m.T.values():
            out |= {c for c in v if 0xAC00 <= ord(c) <= 0xD7A3}
    return out


def main():
    os.makedirs('build_jp', exist_ok=True)
    src = [load_page('jp/start/fontB.ftd'), load_page('jp/start/FontB0000.txp')]
    dst = [load_page('jp/start/fontB.ftd'), load_page('jp/start/FontB0000.txp')]
    map_src = open('jp/start/talk00.dat', 'rb').read()
    fnt_src = open('jp/start/fontB.fnt', 'rb').read()

    kana = collect_kana(map_src)
    syms = collect_moves(map_src)
    preserve = kana + syms
    alnum = collect_fullwidth_alnum(map_src)
    print(f'보존 이전분: 가나 {len(kana)} + 기호 {len(syms)} = {len(preserve)}자')
    print(f'전각 영숫자 복원: {len(alnum)}자')
    assert MOVE_BASE + len(preserve) - 1 <= 2591, '보존분이 페이지 용량 초과'

    must = used_syllables()
    chars = hangul_rank.pick(HANGUL_LIMIT, must=must)
    dropped = hangul_rank.dropped(HANGUL_LIMIT, must=must)
    print(f'한글 {len(chars)}자 선정 (번역 사용 {len(must)}자 강제 포함, 제외 {len(dropped)}자)')
    print(f'  제외: {"".join(dropped)}')
    assert len(chars) == HANGUL_LIMIT

    n = wipe(dst, GID_BASE, 2591)
    print(f'기존 셀 제거 {n}개')

    font = ImageFont.truetype(FONT_PATH, FONT_SIZE, index=FONT_INDEX)
    bake(dst, chars, font)
    print(f'한글 베이크 -> gid {GID_BASE}..{GID_BASE+len(chars)-1}')

    alnum_moves = move_glyphs_to(dst, src, alnum, FULLWIDTH_ALNUM_BASE)
    # ★ 복사한 원본 전각 영숫자는 일본어 폰트용이라 한글보다 크다(잉크 높이 12~13px vs 11px).
    #   인게임에서 숫자가 커 보인다는 지적을 받았다 -> 같은 서체(돋움 12)로 다시 굽는다.
    #   map/fnt 항목은 move_glyphs_to 결과를 그대로 쓰고 셀 픽셀만 교체한다.
    nre = sum(1 for c1, c2, _o, ng in alnum_moves
              if rebake_cell(dst, bytes([c1, c2]).decode('cp932'), ng, font))
    print(f'전각 영숫자 -> gid {FULLWIDTH_ALNUM_BASE}..{FULLWIDTH_ALNUM_BASE+len(alnum_moves)-1}'
          f' ({nre}자 우리 서체로 재렌더)')

    # 전각 기호(？！：；，．（）－／～)도 같은 이유로 원위치에서 재렌더
    rs = rebake_symbols(dst, map_src, font)
    print(f'전각 기호 재렌더 {len(rs)}자: {"".join(c for c, _ in rs)}')

    moves = move_glyphs(dst, src, preserve)
    print(f'보존 이전 -> gid {MOVE_BASE}..{MOVE_BASE+len(moves)-1}')

    # ★ ASCII 보충 글리프는 굽지 않는다. 원본이 `? ~ : ' | z v` 등의 글리프를 비워둔 것은
    #   누락이 아니라, **바이트코드에 섞인 ASCII 값이 화면에 안 보이게 하는 장치**다.
    #   글리프를 채워 넣으니 대사창에 `|` `'` 같은 쓰레기가 드러났다(인게임에서 실제로 겪음).
    #   필요한 문자는 전각(？～：＆＜＞’)으로 대체한다 — 그쪽은 원본 글리프가 살아 있다.
    all_moves = alnum_moves + moves
    mp, ft, codes = build_tables(map_src, fnt_src, chars, all_moves)

    save_page(dst[0], 'build_jp/fontB.ftd')
    save_page(dst[1], 'build_jp/FontB0000.txp')
    open('build_jp/talk00.dat', 'wb').write(mp)
    open('build_jp/fontB.fnt', 'wb').write(ft)
    shutil.copyfile('jp/start/FontB0001.txp', 'build_jp/FontB0001.txp')
    for f in ('fontB.ftd', 'FontB0000.txp', 'talk00.dat', 'fontB.fnt'):
        a = os.path.getsize('jp/start/' + f); b = os.path.getsize('build_jp/' + f)
        assert a == b, f'{f} 크기 변경 {a}->{b}'
    print('폰트 4종 저장 (크기 동일)')

    with open('build_jp/hangul_codes.tsv', 'w', encoding='utf-8') as fp:
        fp.write('char\tc1\tc2\tidx\tgid\n')
        for ch, c1, c2, i, g in codes:
            fp.write(f'{ch}\t{c1:02X}\t{c2:02X}\t{i}\t{g}\n')
    with open('build_jp/moved_codes.tsv', 'w', encoding='utf-8') as fp:
        fp.write('c1\tc2\told_gid\tnew_gid\n')
        for c1, c2, o, nw in all_moves:
            fp.write(f'{c1:02X}\t{c2:02X}\t{o}\t{nw}\n')
    print('코드표 저장')


if __name__ == '__main__':
    main()
