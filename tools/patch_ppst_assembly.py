# -*- coding: utf-8 -*-
"""기존 일본어 세이브에서 생성된 암흑의회 의원 64명의 이름을 PPST RAM에서 변환."""
import ctypes
import importlib.util
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import krtext

SOURCE = pathlib.Path(sys.argv[1])
TARGET = pathlib.Path(sys.argv[2])
DLL = pathlib.Path(
    r'C:\Users\OXP2\.cache\codex-runtimes\codex-primary-runtime\dependencies'
    r'\native\git\mingw64\bin\libzstd.dll')

spec = importlib.util.spec_from_file_location(
    'tr_names_vm_extra', ROOT / 'work' / 'tr_names_vm_extra.py')
translations = importlib.util.module_from_spec(spec)
spec.loader.exec_module(translations)

zstd = ctypes.CDLL(str(DLL))
zstd.ZSTD_getFrameContentSize.argtypes = (ctypes.c_void_p, ctypes.c_size_t)
zstd.ZSTD_getFrameContentSize.restype = ctypes.c_ulonglong
zstd.ZSTD_decompress.argtypes = (
    ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t)
zstd.ZSTD_decompress.restype = ctypes.c_size_t
zstd.ZSTD_compressBound.argtypes = (ctypes.c_size_t,)
zstd.ZSTD_compressBound.restype = ctypes.c_size_t
zstd.ZSTD_compress.argtypes = (
    ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t,
    ctypes.c_int)
zstd.ZSTD_compress.restype = ctypes.c_size_t
zstd.ZSTD_isError.argtypes = (ctypes.c_size_t,)
zstd.ZSTD_isError.restype = ctypes.c_uint
zstd.ZSTD_getErrorName.argtypes = (ctypes.c_size_t,)
zstd.ZSTD_getErrorName.restype = ctypes.c_char_p


def check(code):
    if zstd.ZSTD_isError(code):
        raise RuntimeError(zstd.ZSTD_getErrorName(code).decode('ascii', 'replace'))
    return code


packed = SOURCE.read_bytes()
frame_at = packed.find(bytes.fromhex('28 b5 2f fd'))
if frame_at != 0xB0:
    raise SystemExit(f'예상하지 못한 PPST 프레임 위치: {frame_at:#x}')
frame = packed[frame_at:]
src = ctypes.create_string_buffer(frame)
raw_size = zstd.ZSTD_getFrameContentSize(src, len(frame))
if raw_size in (0xFFFFFFFFFFFFFFFF, 0xFFFFFFFFFFFFFFFE):
    raise SystemExit('Zstandard 원본 크기를 읽지 못했습니다.')
raw_buf = ctypes.create_string_buffer(raw_size)
got = check(zstd.ZSTD_decompress(raw_buf, raw_size, src, len(frame)))
memory = bytearray(raw_buf.raw[:got])

# 32바이트 의원 구조체의 이름 필드는 +0x0E, 폭 16바이트다.
first_name = 'うとうと議員'.encode('cp932')
converted = []
first_at = memory.find(first_name)
array_at = None
if first_at >= 14:
    array_at = first_at - 14
    if array_at % 0x20:
        raise SystemExit(f'의원 배열 정렬 불일치: {array_at:#x}')
    for index in range(64):
        field_at = array_at + index * 0x20 + 14
        field = bytes(memory[field_at:field_at + 16])
        old_raw = field.split(b'\0')[0]
        try:
            old = old_raw.decode('cp932')
        except UnicodeDecodeError as exc:
            raise SystemExit(f'의원 {index} 원문 디코드 실패: {exc}')
        if old not in translations.T:
            raise SystemExit(f'의원 {index} 번역 누락: {old!r}')
        new = translations.T[old]
        new_raw = krtext.encode(new)
        if len(new_raw) > 16:
            raise SystemExit(f'의원 {index} 필드 초과: {old} -> {new} ({len(new_raw)}B)')
        memory[field_at:field_at + 16] = new_raw + bytes(16 - len(new_raw))
        converted.append((old, new))

# 캐릭터 생성의 소질 5단계도 구 script00이 상태 RAM에 남아 별도 화면에서 사용된다.
aptitude = {
    'どうしようもないクズ': '답 없는 쓰레기',
    'おちこぼれ': '낙오자',
    '平凡': '평범',
    '優秀': '우수',
    '極めて優秀': '극히 우수',
}
aptitude_hits = []
for old, new in sorted(aptitude.items(), key=lambda item: len(item[0]), reverse=True):
    old_raw = old.encode('cp932')
    new_raw = krtext.encode(new)
    if len(new_raw) > len(old_raw):
        raise SystemExit(f'소질명 필드 초과: {old} -> {new}')
    hits = []
    start = 0
    while True:
        at = memory.find(old_raw, start)
        if at < 0:
            break
        memory[at:at + len(old_raw)] = new_raw + bytes(len(old_raw) - len(new_raw))
        hits.append(at)
        start = at + len(old_raw)
    aptitude_hits.append((old, new, hits))

bound = zstd.ZSTD_compressBound(len(memory))
compressed_buf = ctypes.create_string_buffer(bound)
memory_buf = ctypes.create_string_buffer(bytes(memory))
compressed_size = check(zstd.ZSTD_compress(
    compressed_buf, bound, memory_buf, len(memory), 3))
new_frame = compressed_buf.raw[:compressed_size]

header = bytearray(packed[:frame_at])
struct.pack_into('<I', header, 8, len(new_frame))
struct.pack_into('<I', header, 12, len(memory))
TARGET.write_bytes(header + new_frame)

# 완성본을 즉시 다시 풀어 64개 필드와 전체 크기를 왕복 검증한다.
test = TARGET.read_bytes()[frame_at:]
test_src = ctypes.create_string_buffer(test)
test_size = zstd.ZSTD_getFrameContentSize(test_src, len(test))
test_buf = ctypes.create_string_buffer(test_size)
test_got = check(zstd.ZSTD_decompress(test_buf, test_size, test_src, len(test)))
roundtrip = test_buf.raw[:test_got]
if roundtrip != bytes(memory):
    raise SystemExit('PPST 압축 왕복 불일치')
if array_at is not None:
    for index, (_old, new) in enumerate(converted):
        field_at = array_at + index * 0x20 + 14
        actual = roundtrip[field_at:field_at + 16].split(b'\0')[0]
        if actual != krtext.encode(new):
            raise SystemExit(f'의원 {index} 완성본 검증 실패')
for old, new, hits in aptitude_hits:
    if old.encode('cp932') in roundtrip:
        raise SystemExit(f'소질명 원문 잔존: {old}')
    print(f'소질명: {old} -> {new} ({len(hits)}회)')

if array_at is None:
    print('의원 배열: 이미 변환되어 건너뜀')
else:
    print(f'의원 배열: {array_at:#x}, 64/64 변환')
print(f'PPST: {len(packed):,}B -> {TARGET.stat().st_size:,}B')
if converted:
    print(f'첫 항목: {converted[0][0]} -> {converted[0][1]}')
    print(f'마지막: {converted[-1][0]} -> {converted[-1][1]}')
print(f'완성: {TARGET}')
