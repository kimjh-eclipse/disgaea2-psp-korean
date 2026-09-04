# -*- coding: utf-8 -*-
"""릴리스 패처용 암흑의회 세이브 이름 치환표를 생성한다."""
import importlib.util
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import krtext

spec = importlib.util.spec_from_file_location(
    'tr_names_vm_extra', ROOT / 'work' / 'tr_names_vm_extra.py')
tr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tr)

FIRST = 'うとうと議員'
LAST = '天願先生'
keys = list(tr.T)
names = keys[keys.index(FIRST):keys.index(LAST) + 1]
if len(names) != 64:
    raise SystemExit(f'의원명 수가 64가 아닙니다: {len(names)}')

out = bytearray(b'D2ASMMAP1')
out += struct.pack('<I', 1)
out += struct.pack('<I', len(names))
for old in names:
    new = tr.T[old]
    old_raw = old.encode('cp932')
    new_raw = krtext.encode(new)
    if len(old_raw) > 16 or len(new_raw) > 16:
        raise SystemExit(f'16바이트 초과: {old} -> {new}')
    out += old_raw.ljust(16, b'\0')
    out += new_raw.ljust(16, b'\0')

target = ROOT / 'iso_quickpatch' / 'D2_SAVE_assemblymap.bin'
target.write_bytes(out)
print(f'{target}: {len(names)}개, {len(out):,}B')
