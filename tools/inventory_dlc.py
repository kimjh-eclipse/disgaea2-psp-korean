# -*- coding: utf-8 -*-
"""ULJS00183 DLC 5개 고유 세대에서 본편 번역에 없는 문자열을 수집한다."""
import csv
import glob
import importlib.util
import pathlib
import struct
import sys
from collections import defaultdict

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import recdat
import scriptpack
import talkfile
from inspect_dlc import start_members
from nislzs import decompress

GROUPS = (0, 5, 9, 13, 17)


def load_map(pattern):
    result = {}
    for path in sorted(glob.glob(str(ROOT / pattern))):
        spec = importlib.util.spec_from_file_location('translation_part', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result.update(module.T)
    return result


def has_japanese(text):
    return any(
        '\u3040' <= char <= '\u30ff' or '\u3400' <= char <= '\u9fff'
        for char in text
    )


def decode_cp932(raw):
    try:
        return raw.decode('cp932')
    except UnicodeDecodeError:
        return None


def load_group(number):
    data = (ROOT / 'dlc_jp' / f'DL_JP_{number:02d}.EDAT').read_bytes()
    entries = scriptpack.unpack(data)
    packed = next(entry['data'] for entry in entries if entry['name'] == 'start_jp.lzs')
    return start_members(decompress(packed))


def add(found, source, group, where, jp, capacity=''):
    if not jp or not has_japanese(jp):
        return
    key = (source, jp)
    item = found.setdefault(key, {
        'source': source, 'jp': jp, 'groups': set(), 'where': [], 'capacity': [],
        'order': len(found),
    })
    item['groups'].add(group)
    if len(item['where']) < 8:
        item['where'].append(where)
    if capacity != '':
        item['capacity'].append(capacity)


def main():
    ip_map = load_map('work/tr_iptxt*.py')
    char_map = load_map('work/tr_char*.py')
    rec_map = load_map('work/tr_rec*.py')
    maps = {'InProgramTxtDB.dat': ip_map, 'sys2.txp': char_map}
    found = {}
    totals = defaultdict(int)
    covered = defaultdict(int)

    for group in GROUPS:
        files = load_group(group)

        name = 'InProgramTxtDB.dat'
        for off, raw in talkfile.strings(files[name]):
            jp = decode_cp932(raw)
            if not jp or not has_japanese(jp):
                continue
            totals[name] += 1
            if jp in maps[name]:
                covered[name] += 1
            else:
                add(found, name, group, f'{off:#x}', jp)

        name = 'sys2.txp'
        data = files[name]
        stride, width = 0xF6, 0x17
        count = struct.unpack_from('<I', data, 0)[0]
        assert 8 + count * stride == len(data)
        for index in range(count):
            for field in (0, width):
                base = 8 + index * stride + field
                raw = data[base:base + width].split(b'\0')[0]
                jp = decode_cp932(raw)
                if not jp or not has_japanese(jp):
                    continue
                totals[name] += 1
                if jp in maps[name]:
                    covered[name] += 1
                else:
                    add(found, name, group, f'rec={index},off={field:#x}', jp, width - 1)

        for name in recdat.SPEC:
            data = files[name]
            for index, field, _width, raw in recdat.items(name, data):
                jp = decode_cp932(raw)
                if not jp or not has_japanese(jp):
                    continue
                totals[name] += 1
                if jp in rec_map:
                    covered[name] += 1
                else:
                    cap = recdat.capacity(name, data, index, field)
                    add(found, name, group, f'rec={index},off={field:#x}', jp, cap)

    output = ROOT / 'work' / 'dlc_untranslated.tsv'
    with output.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=('uid', 'source', 'groups', 'where', 'capacity', 'jp', 'ko'), delimiter='\t')
        writer.writeheader()
        for uid, item in enumerate(sorted(found.values(), key=lambda x: x['order'])):
            capacities = item['capacity']
            writer.writerow({
                'uid': f'DLC{uid:04d}',
                'source': item['source'],
                'groups': ','.join(f'{n:02d}' for n in sorted(item['groups'])),
                'where': ';'.join(item['where']),
                'capacity': min(capacities) if capacities else '',
                'jp': item['jp'],
                'ko': '',
            })

    print(f'출력: {output}')
    for name in sorted(totals):
        missing = sum(1 for item in found.values() if item['source'] == name)
        print(f'{name:20s} 출현 {totals[name]:5d}, 기존 번역 {covered[name]:5d}, 신규 고유 {missing:5d}')
    print(f'신규 고유 합계: {len(found):,}')


if __name__ == '__main__':
    main()
