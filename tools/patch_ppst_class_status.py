# -*- coding: utf-8 -*-
"""캐릭터 생성 상세 화면의 구 RAM DB를 현재 빌드로 교체한다.

PPSSPP 상태저장은 START_JP 안의 magic.dat와 script00 문자열을 RAM째
보존하므로 ISO를 갱신한 뒤에도 예전 상태를 불러오면 구 데이터가 되살아난다.
"""
import ctypes
import pathlib
import struct
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import krtext
import build_jp as build_jp_tool

SOURCE = pathlib.Path(sys.argv[1])
TARGET = pathlib.Path(sys.argv[2])
MAGIC = ROOT / 'build_jp' / 'magic.dat'
EBOOT = ROOT / 'build_jp' / 'EBOOT_KR.BIN'
DLL = pathlib.Path(
    r'C:\Users\OXP2\.cache\codex-runtimes\codex-primary-runtime\dependencies'
    r'\native\git\mingw64\bin\libzstd.dll')

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

# magic.dat 41번 레코드 첫 필드로 RAM 적재 위치를 역산한다. 이미 한 번
# 패치한 상태도 다시 처리할 수 있도록 구 문자열과 현재 문자열을 모두 받는다.
old_anchor = krtext.encode('최전선에서 활약하는 파워 파이터.')
new_anchor = krtext.encode(build_jp_tool.fixed_cell_text(
    '최전선에서 활약하는 파워 파이터.'))
anchor_hits = []
for anchor in (old_anchor, new_anchor):
    start = 0
    while True:
        at = memory.find(anchor, start)
        if at < 0:
            break
        anchor_hits.append(at)
        start = at + 1
anchor_hits = sorted(set(anchor_hits))
if len(anchor_hits) != 1:
    raise SystemExit(f'magic.dat 기준 문장 출현 횟수 불일치: {len(anchor_hits)}')
anchor_at = anchor_hits[0]
magic_base = anchor_at - (8 + 41 * 152)
if memory[magic_base:magic_base + 8] != bytes.fromhex('a3 00 00 00 a3 00 00 00'):
    raise SystemExit(f'magic.dat 헤더 불일치: {magic_base:#x}')
magic = MAGIC.read_bytes()
if len(magic) != 24784:
    raise SystemExit(f'magic.dat 크기 불일치: {len(magic)}')
memory[magic_base:magic_base + len(magic)] = magic

labels = [('장비 적성', '장비적성'), ('기본 능력', '기본능력')]
label_results = []
for old, new in labels:
    old_raw = krtext.encode(old)
    new_raw = krtext.encode(new)
    hits = []
    start = 0
    while True:
        at = memory.find(old_raw, start)
        if at < 0:
            break
        memory[at:at + len(old_raw)] = new_raw + bytes(len(old_raw) - len(new_raw))
        hits.append(at)
        start = at + len(old_raw)
    if len(hits) > 1:
        raise SystemExit(f'{old!r} 상태 RAM 출현 횟수 불일치: {len(hits)}')
    if hits:
        at = hits[0]
    else:
        new_hits = []
        start = 0
        while True:
            found = memory.find(new_raw, start)
            if found < 0:
                break
            new_hits.append(found)
            start = found + 1
        if len(new_hits) != 1:
            raise SystemExit(f'{new!r} 상태 RAM 출현 횟수 불일치: {len(new_hits)}')
        at = new_hits[0]
    label_results.append((old, new, at))

# 상태 저장은 실행 파일의 데이터 영역도 함께 보존한다. 예전 패처가 소질명
# 필드 뒤의 수치 2바이트까지 지운 상태를 불러오지 않도록, 현 빌드 EBOOT의
# 6개 레코드(이름 22B + 수치 4B)를 그대로 복원한다.
eboot_patched, aptitude_names, aptitude_offsets = (
    build_jp_tool.patch_eboot_aptitude_names(EBOOT.read_bytes()))
record_size = 0x1a
source_table = b''.join(
    eboot_patched[at:at + record_size] for at in aptitude_offsets)
state_names = [krtext.encode(new) for _old, new in aptitude_names]
table_candidates = []
start = 0
while True:
    at = memory.find(state_names[0], start)
    if at < 0:
        break
    ok = all(memory[at + i * record_size:at + i * record_size + len(raw)] == raw
             for i, raw in enumerate(state_names[:5]))
    sixth = memory[at + 5 * record_size:at + 5 * record_size + 22]
    sixth_ok = (sixth.startswith(state_names[5]) or
                sixth.startswith(aptitude_names[5][0].encode('cp932')))
    if ok and sixth_ok:
        table_candidates.append(at)
    start = at + 1
if len(table_candidates) != 1:
    raise SystemExit(f'EBOOT 소질명 상태 테이블 출현 횟수 불일치: {len(table_candidates)}')
aptitude_state_at = table_candidates[0]
memory[aptitude_state_at:aptitude_state_at + len(source_table)] = source_table

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

# 출력 파일을 다시 풀어 전체 magic.dat와 제목을 검증한다.
test = TARGET.read_bytes()[frame_at:]
test_src = ctypes.create_string_buffer(test)
test_size = zstd.ZSTD_getFrameContentSize(test_src, len(test))
test_buf = ctypes.create_string_buffer(test_size)
test_got = check(zstd.ZSTD_decompress(test_buf, test_size, test_src, len(test)))
roundtrip = test_buf.raw[:test_got]
if roundtrip[magic_base:magic_base + len(magic)] != magic:
    raise SystemExit('magic.dat 압축 왕복 검증 실패')
for old, new, at in label_results:
    if roundtrip[at:at + len(krtext.encode(new))] != krtext.encode(new):
        raise SystemExit(f'{new!r} 압축 왕복 검증 실패')
if roundtrip[aptitude_state_at:aptitude_state_at + len(source_table)] != source_table:
    raise SystemExit('EBOOT 소질명 테이블 압축 왕복 검증 실패')
print(f'magic.dat RAM 교체: {magic_base:#x}, {len(magic):,}B')
for old, new, at in label_results:
    print(f'제목: {old} -> {new} ({at:#x})')
print(f'EBOOT 소질명 6레코드 복원: {aptitude_state_at:#x}, {len(source_table):,}B')
print(f'PPST: {len(packed):,}B -> {TARGET.stat().st_size:,}B')
print(f'완성: {TARGET}')
