# -*- coding: utf-8 -*-
"""PPSSPP .ppst의 Zstandard 본문을 풀어 문자열/메모리 상태를 점검한다."""
import ctypes
import pathlib
import sys

STATE = pathlib.Path(sys.argv[1])
OUT = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else None
DLL = pathlib.Path(
    r'C:\Users\OXP2\.cache\codex-runtimes\codex-primary-runtime\dependencies'
    r'\native\git\mingw64\bin\libzstd.dll')

raw = STATE.read_bytes()
magic = bytes.fromhex('28 b5 2f fd')
offset = raw.find(magic)
if offset < 0:
    raise SystemExit('Zstandard 프레임을 찾지 못했습니다.')

zstd = ctypes.CDLL(str(DLL))
zstd.ZSTD_getFrameContentSize.argtypes = (ctypes.c_void_p, ctypes.c_size_t)
zstd.ZSTD_getFrameContentSize.restype = ctypes.c_ulonglong
zstd.ZSTD_decompress.argtypes = (
    ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t)
zstd.ZSTD_decompress.restype = ctypes.c_size_t
zstd.ZSTD_isError.argtypes = (ctypes.c_size_t,)
zstd.ZSTD_isError.restype = ctypes.c_uint
zstd.ZSTD_getErrorName.argtypes = (ctypes.c_size_t,)
zstd.ZSTD_getErrorName.restype = ctypes.c_char_p

frame = raw[offset:]
src = ctypes.create_string_buffer(frame)
size = zstd.ZSTD_getFrameContentSize(src, len(frame))
if size in (0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFE):
    raise SystemExit(f'프레임 원본 크기를 읽지 못했습니다: {size:#x}')
dst = ctypes.create_string_buffer(size)
got = zstd.ZSTD_decompress(dst, size, src, len(frame))
if zstd.ZSTD_isError(got):
    raise SystemExit(zstd.ZSTD_getErrorName(got).decode('ascii', 'replace'))
data = dst.raw[:got]
print(f'{STATE.name}: frame={offset:#x}, compressed={len(frame):,}, '
      f'decompressed={len(data):,}')

terms = (
    '夢はばたく議員', 'はばたく', 'オーク太郎議員', 'オーク',
    '꿈나래 의원', '오크 타로 의원', '상당히 부정적',
)
for term in terms:
    encodings = []
    try:
        encodings.append(('cp932', term.encode('cp932')))
    except UnicodeEncodeError:
        pass
    try:
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
        import krtext
        encodings.append(('krtext', krtext.encode(term)))
    except Exception:
        pass
    found = []
    for label, needle in encodings:
        positions = []
        start = 0
        while len(positions) < 8:
            pos = data.find(needle, start)
            if pos < 0:
                break
            positions.append(pos)
            start = pos + 1
        if positions:
            found.append(f'{label}={len(positions)}@' + ','.join(hex(p) for p in positions))
    print(f'{term}: ' + ('; '.join(found) if found else '0'))

if OUT:
    OUT.write_bytes(data)
    print(f'저장: {OUT}')
