# -*- coding: utf-8 -*-
"""ULJS00183 추가 패키지 한글판 빌드/설치.

18개 EDAT은 5개의 누적 스냅샷(00/05/09/13/17)이다. 각 대표 파일을
번역한 뒤 같은 세대의 파일명으로 복제한다. PARAM.PBP는 원본 그대로 둔다.

사용:
  python tools/build_dlc.py
  python tools/build_dlc.py --install
"""
import glob
import importlib.util
import io
import os
import pathlib
import shutil
import struct
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
os.chdir(ROOT)

import krtext
import recdat
import scriptpack
import talkfile
from inspect_dlc import start_members
from nislzs import compress, decompress
from rebuild import rebuild_start

GROUPS = {
    0: range(0, 5),
    5: range(5, 9),
    9: range(9, 13),
    13: range(13, 17),
    17: range(17, 18),
}

FONT_FILES = ('fontB.ftd', 'FontB0000.txp', 'talk00.dat', 'fontB.fnt')
FW_MAP = {
    ' ': '　', '.': '．', ',': '，', '!': '！', '?': '？', '~': '～',
    ':': '：', ';': '；', '(': '（', ')': '）', '-': '－', '/': '／',
    '&': '＆', '<': '＜', '>': '＞',
}
for n in range(10):
    FW_MAP[chr(0x30 + n)] = chr(0xFF10 + n)
for n in range(26):
    FW_MAP[chr(0x41 + n)] = chr(0xFF21 + n)
    FW_MAP[chr(0x61 + n)] = chr(0xFF41 + n)


def fullwidth(text):
    return ''.join(FW_MAP.get(char, char) for char in text)


def load_map(patterns):
    result = {}
    for pattern in patterns:
        for index, path in enumerate(sorted(glob.glob(str(ROOT / pattern)))):
            spec = importlib.util.spec_from_file_location(
                f'dlc_map_{abs(hash((pattern, path, index)))}', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            result.update(module.T)
    return result


def encoded(text, *, widen=False):
    value = fullwidth(text) if widen else text
    invalid = krtext.validate(value)
    if invalid:
        raise ValueError(f'인코딩/글리프 불가 {"".join(invalid)!r}: {value}')
    return krtext.encode(value)


def patch_talk(data, mapping):
    table = {jp.encode('cp932'): encoded(ko, widen=True) for jp, ko in mapping.items()}
    edits = {off: table[raw] for off, raw in talkfile.strings(data) if raw in table}
    return talkfile.rebuild(data, edits), len(edits)


def patch_sys2(data, mapping):
    out = bytearray(data)
    stride, width = 0xF6, 0x17
    count = struct.unpack_from('<I', out, 0)[0]
    assert 8 + count * stride == len(out), 'sys2.txp 구조 불일치'
    hit = 0
    for index in range(count):
        for field in (0, width):
            base = 8 + index * stride + field
            raw = bytes(out[base:base + width]).split(b'\0')[0]
            try:
                jp = raw.decode('cp932')
            except UnicodeDecodeError:
                continue
            if jp not in mapping:
                continue
            # 고정 필드는 본편 빌더와 동일하게 번역표의 바이트를 그대로 쓴다.
            # 전각화하면 ASCII가 1B->2B가 되어 기존의 빠듯한 레코드가 넘친다.
            new = encoded(mapping[jp])
            if len(new) > width - 1:
                raise ValueError(f'sys2 초과 {len(new)}>{width - 1}: {jp} -> {mapping[jp]}')
            out[base:base + width] = new + bytes(width - len(new))
            hit += 1
    return bytes(out), hit


def patch_record(name, data, mapping):
    edits = {}
    for index, field, _width, raw in recdat.items(name, data):
        try:
            jp = raw.decode('cp932')
        except UnicodeDecodeError:
            continue
        if jp not in mapping:
            continue
        new = encoded(mapping[jp])
        cap = recdat.capacity(name, data, index, field)
        if len(new) > cap:
            raise ValueError(f'{name} 초과 {len(new)}>{cap}: {jp} -> {mapping[jp]}')
        edits[(index, field)] = new
    return recdat.put(name, data, edits), len(edits)


def build_group(number, ip_map, char_map, rec_map, output):
    source = ROOT / 'dlc_jp' / f'DL_JP_{number:02d}.EDAT'
    outer = scriptpack.unpack(source.read_bytes())
    start_entry = next(item for item in outer if item['name'] == 'start_jp.lzs')
    original_lzs = start_entry['data']
    raw = decompress(original_lzs)
    members = start_members(raw)

    overrides = {}
    overrides['InProgramTxtDB.dat'], ip_hits = patch_talk(
        members['InProgramTxtDB.dat'], ip_map)
    overrides['sys2.txp'], sys_hits = patch_sys2(members['sys2.txp'], char_map)

    rec_hits = 0
    for name in recdat.SPEC:
        overrides[name], hits = patch_record(name, members[name], rec_map)
        rec_hits += hits

    # 본편과 DLC가 같은 코드표를 써야 하므로 폰트 4종은 항상 최신 빌드본으로 통일한다.
    for name in FONT_FILES:
        overrides[name] = (ROOT / 'build_jp' / name).read_bytes()
    overrides['script00.dat'] = (ROOT / 'build_jp' / 'script00.dat').read_bytes()

    group_dir = output / f'group_{number:02d}'
    group_dir.mkdir(parents=True, exist_ok=True)
    original_raw = group_dir / 'START_original.bin'
    original_raw.write_bytes(raw)
    rebuilt = rebuild_start(str(original_raw), overrides)
    flag = original_lzs[12]
    rebuilt_lzs = compress(rebuilt, flag)
    assert decompress(rebuilt_lzs) == rebuilt, 'START LZS 왕복 검증 실패'
    (group_dir / 'START_KR.bin').write_bytes(rebuilt)
    (group_dir / 'start_jp_KR.lzs').write_bytes(rebuilt_lzs)

    start_entry['data'] = rebuilt_lzs
    packed = scriptpack.pack(outer)
    # 바깥 NISPACK도 다시 읽어 START가 정확히 들어갔는지 검사한다.
    check = scriptpack.unpack(packed)
    check_lzs = next(item['data'] for item in check if item['name'] == 'start_jp.lzs')
    assert decompress(check_lzs) == rebuilt, 'EDAT 재패킹 검증 실패'

    for alias in GROUPS[number]:
        (output / f'DL_JP_{alias:02d}.EDAT').write_bytes(packed)
    print(f'GROUP {number:02d}: IP {ip_hits:,} / sys2 {sys_hits:,} / rec {rec_hits:,}; '
          f'START {len(original_lzs):,}->{len(rebuilt_lzs):,}B; EDAT {len(packed):,}B')
    return packed


def install(output):
    target = pathlib.Path.home() / 'Documents' / 'PPSSPP' / 'PSP' / 'GAME' / 'ULJS00183'
    target.mkdir(parents=True, exist_ok=True)
    for path in sorted(output.glob('DL_JP_*.EDAT')):
        shutil.copy2(path, target / path.name)
    shutil.copy2(output / 'PARAM.PBP', target / 'PARAM.PBP')
    print(f'PPSSPP 설치 완료: {target}')


def main(do_install=False):
    from code_sync import require_synced
    require_synced('font', 'START', 'SCRIPTPACK', 'NAME', 'START_VM', 'CHAR')
    output = ROOT / 'build_dlc' / 'ULJS00183_KR'
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / 'dlc_jp' / 'PARAM.PBP', output / 'PARAM.PBP')

    ip_map = load_map(('work/tr_iptxt*.py', 'work/tr_dlc_dialogue_*.py'))
    fixed = load_map(('work/tr_dlc_fixed.py',))
    char_map = load_map(('work/tr_char*.py',))
    char_map.update(fixed)
    rec_map = load_map(('work/tr_rec*.py',))
    rec_map.update(fixed)
    print(f'번역표: InProgram {len(ip_map):,}, char {len(char_map):,}, rec {len(rec_map):,}')

    for number in GROUPS:
        build_group(number, ip_map, char_map, rec_map, output)
    files = sorted(output.glob('DL_JP_*.EDAT'))
    assert len(files) == 18, f'EDAT 개수 불일치: {len(files)}'
    print(f'완료: {output} ({len(files)} EDAT + PARAM.PBP)')
    if do_install:
        install(output)


if __name__ == '__main__':
    if '--install-only' in sys.argv:
        install(ROOT / 'build_dlc' / 'ULJS00183_KR')
    else:
        main('--install' in sys.argv)
