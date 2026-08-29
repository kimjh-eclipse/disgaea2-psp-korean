# -*- coding: utf-8 -*-
"""빌드된 ULJS00183 DLC의 구조·그룹·번역 적용을 검증하고 manifest를 쓴다."""
import csv
import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import recdat
import scriptpack
import talkfile
from inspect_dlc import start_members
from nislzs import decompress

GROUPS = {0: range(0, 5), 5: range(5, 9), 9: range(9, 13), 13: range(13, 17), 17: range(17, 18)}
UNTOUCHED_START = {'effect0.psp3d', 'waku.txp', 'anm0000.dat', 'FontB0001.txp',
                   'WISH2.dat', 'comb.dat', 'face.dat'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_start(path):
    entries = scriptpack.unpack(path.read_bytes())
    packed = next(e['data'] for e in entries if e['name'] == 'start_jp.lzs')
    return entries, start_members(decompress(packed))


def main():
    src = ROOT / 'dlc_jp'
    out = ROOT / 'build_dlc' / 'ULJS00183_KR'
    rows = list(csv.DictReader((ROOT / 'work' / 'dlc_untranslated.tsv').open(
        encoding='utf-8-sig'), delimiter='\t'))
    dlc_jp = {row['jp'] for row in rows}
    manifest = {'title_id': 'ULJS00183', 'format': 'loose PSP/GAME files', 'groups': {}, 'files': {}}

    assert (src / 'PARAM.PBP').read_bytes() == (out / 'PARAM.PBP').read_bytes()
    for representative, aliases in GROUPS.items():
        original_outer, original = load_start(src / f'DL_JP_{representative:02d}.EDAT')
        built_outer, built = load_start(out / f'DL_JP_{representative:02d}.EDAT')
        assert [(e['name'], e['tag']) for e in original_outer] == [
            (e['name'], e['tag']) for e in built_outer]
        for name in ('sound_02_jp.dat', 'cutinPack.dat'):
            a = next(e['data'] for e in original_outer if e['name'] == name)
            b = next(e['data'] for e in built_outer if e['name'] == name)
            assert a == b, f'{representative:02d} {name} 변경'
        assert set(original) == set(built)
        for name in UNTOUCHED_START:
            assert original[name] == built[name], f'{representative:02d} {name} 변경'
        for name in ('sys2.txp',) + tuple(recdat.SPEC):
            assert len(original[name]) == len(built[name]), f'{representative:02d} {name} 크기 변경'

        # DLC 신규 원문이 가변 대사 또는 고정 필드에 그대로 남았는지 검사한다.
        leftovers = []
        for _off, raw in talkfile.strings(built['InProgramTxtDB.dat']):
            try:
                text = raw.decode('cp932')
            except UnicodeDecodeError:
                continue
            if text in dlc_jp:
                leftovers.append(('InProgramTxtDB.dat', text))
        for name in recdat.SPEC:
            for _i, _off, _width, raw in recdat.items(name, built[name]):
                try:
                    text = raw.decode('cp932')
                except UnicodeDecodeError:
                    continue
                if text in dlc_jp:
                    leftovers.append((name, text))
        assert not leftovers, f'{representative:02d} DLC 원문 잔존: {leftovers[:5]}'

        rep_data = (out / f'DL_JP_{representative:02d}.EDAT').read_bytes()
        for alias in aliases:
            alias_data = (out / f'DL_JP_{alias:02d}.EDAT').read_bytes()
            assert alias_data == rep_data, f'그룹 별칭 불일치 {representative:02d}/{alias:02d}'
        manifest['groups'][f'{representative:02d}'] = [f'{n:02d}' for n in aliases]
        print(f'GROUP {representative:02d}: 구조/비텍스트/원문잔존/별칭 OK')

    for path in [out / 'PARAM.PBP'] + sorted(out.glob('DL_JP_*.EDAT')):
        original = src / path.name
        manifest['files'][path.name] = {
            'source_sha256': sha(original.read_bytes()),
            'korean_sha256': sha(path.read_bytes()),
            'size': path.stat().st_size,
        }
    target = ROOT / 'build_dlc' / 'manifest.json'
    target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'검증 완료: 18 EDAT + PARAM.PBP, DLC 신규 원문 잔존 0')
    print(f'매니페스트: {target}')


if __name__ == '__main__':
    main()
