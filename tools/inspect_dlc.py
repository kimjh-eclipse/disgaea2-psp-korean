# -*- coding: utf-8 -*-
"""ULJS00183 DLC 묶음의 PBP/NISPACK/START 구조를 읽기 전용으로 요약한다."""
import hashlib
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import scriptpack
from nislzs import decompress


def sha16(data):
    return hashlib.sha256(data).hexdigest()[:16]


def start_members(raw):
    count = struct.unpack_from('<I', raw, 0)[0]
    entries = []
    for i in range(count):
        pos = 0x10 + i * 0x20
        off = struct.unpack_from('<I', raw, pos)[0]
        name = raw[pos + 4:pos + 0x20].split(b'\0')[0].decode('latin1')
        entries.append((off, name))
    order = sorted(range(count), key=lambda i: entries[i][0])
    files = {}
    for k, i in enumerate(order):
        off, name = entries[i]
        start = off + 0x2B0
        end = entries[order[k + 1]][0] + 0x2B0 if k + 1 < count else len(raw)
        files[name] = raw[start:end]
    return files


def print_pbp(path):
    pbp = path.read_bytes()
    offsets = struct.unpack_from('<8I', pbp, 8)
    sfo = pbp[offsets[0]:offsets[1]]
    magic, version, key_off, data_off, count = struct.unpack_from('<4s4I', sfo, 0)
    assert magic == b'\0PSF'
    print(f'PARAM.PBP: version={version:#x}, sections={offsets}')
    for i in range(count):
        key_rel, fmt, length, maximum, value_rel = struct.unpack_from('<HHIII', sfo, 20 + i * 16)
        key = sfo[key_off + key_rel:].split(b'\0')[0].decode('ascii')
        raw = sfo[data_off + value_rel:data_off + value_rel + length]
        value = struct.unpack('<I', raw)[0] if fmt == 0x404 else raw.rstrip(b'\0').decode('utf-8')
        print(f'  {key}={value!r} (fmt={fmt:#x}, max={maximum})')


def main():
    dlc = ROOT / 'dlc_jp'
    print_pbp(dlc / 'PARAM.PBP')
    print()
    previous = None
    for number in (0, 5, 9, 13, 17):
        path = dlc / f'DL_JP_{number:02d}.EDAT'
        packed = path.read_bytes()
        entries = scriptpack.unpack(packed)
        print(f'GROUP {number:02d}: outer={len(packed):,}, sha256={sha16(packed)}')
        for entry in entries:
            print(f"  {entry['name']:20s} {len(entry['data']):9,d}  {sha16(entry['data'])}  tag={entry['tag']:08x}")
        start_lzs = next(e['data'] for e in entries if e['name'] == 'start_jp.lzs')
        raw = decompress(start_lzs)
        files = start_members(raw)
        if previous is None:
            changed = list(files)
        else:
            changed = [name for name, data in files.items() if sha16(data) != sha16(previous[name])]
        print(f"  START raw={len(raw):,}, lzs={len(start_lzs):,}; changed={', '.join(changed)}")
        previous = files
        print()


if __name__ == '__main__':
    main()
