# -*- coding: utf-8 -*-
"""복호화된 ULJS00183 DATA.BIN의 암흑의회 의원명 64개를 한국어로 바꾼다.

의원명은 세이브 안의 32바이트 레코드 배열에 생성 시점 문자열로 저장된다.
따라서 ISO의 START_VM을 번역해도 이미 만들어진 세이브에는 반영되지 않는다.
이 도구는 평문 DATA.BIN만 대상으로 하며 입력 길이를 절대 바꾸지 않는다.
"""
import argparse
import collections
import importlib.util
import pathlib
import shutil
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
import krtext

spec = importlib.util.spec_from_file_location(
    'tr_names_vm_extra', ROOT / 'work' / 'tr_names_vm_extra.py')
translations = importlib.util.module_from_spec(spec)
spec.loader.exec_module(translations)

COUNT = 64
STRIDE = 0x20
NAME_OFFSET = 0x0E
NAME_SIZE = 16
FIRST_NAME = 'うとうと議員'


def looks_encrypted(data):
    if not data:
        return False
    counts = collections.Counter(data)
    return counts[0] / len(data) < 0.03 and len(counts) > 250


def patch(data):
    out = bytearray(data)
    first = out.find(FIRST_NAME.encode('cp932'))
    if first < 0:
        # 이미 변환된 파일도 확인 모드에서 정상으로 처리한다.
        first_ko = krtext.encode(translations.T[FIRST_NAME])
        if out.find(first_ko) >= 0:
            return bytes(out), [], 'already'
        return bytes(out), [], 'missing'

    array_at = first - NAME_OFFSET
    converted = []
    for index in range(COUNT):
        field_at = array_at + index * STRIDE + NAME_OFFSET
        field = bytes(out[field_at:field_at + NAME_SIZE])
        old_raw = field.split(b'\0', 1)[0]
        try:
            old = old_raw.decode('cp932')
        except UnicodeDecodeError as exc:
            raise ValueError(f'의원 {index + 1} 원문 디코드 실패: {exc}')
        if old not in translations.T:
            raise ValueError(f'의원 {index + 1} 번역 누락: {old!r}')
        new = translations.T[old]
        new_raw = krtext.encode(new)
        if len(new_raw) > NAME_SIZE:
            raise ValueError(
                f'의원 {index + 1} 필드 초과: {old} -> {new} ({len(new_raw)}B)')
        out[field_at:field_at + NAME_SIZE] = new_raw + bytes(NAME_SIZE - len(new_raw))
        converted.append((old, new, field_at))

    # 배열 안에 원문 이름이 하나라도 남았으면 구조를 잘못 짚은 것이다.
    region = bytes(out[array_at:array_at + COUNT * STRIDE])
    leftovers = [old for old, _new, _at in converted if old.encode('cp932') in region]
    if leftovers:
        raise ValueError(f'의원명 원문 잔존: {leftovers[:3]}')
    return bytes(out), converted, 'patched'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('source', type=pathlib.Path, help='복호화된 DATA.BIN')
    ap.add_argument('target', nargs='?', type=pathlib.Path,
                    help='출력 파일(생략 시 <source>.assemblyfix)')
    ap.add_argument('--in-place', action='store_true', help='.d2assemblybak 백업 후 제자리 수정')
    args = ap.parse_args()

    source = args.source
    target = args.target or pathlib.Path(str(source) + '.assemblyfix')
    data = source.read_bytes()
    print(f'대상: {source} ({len(data):,}B)')
    if looks_encrypted(data):
        raise SystemExit('암호화된 DATA.BIN입니다. 먼저 mode 5로 복호화해야 합니다.')

    fixed, converted, status = patch(data)
    if status == 'already':
        print('의원명은 이미 한국어로 변환되어 있습니다.')
        return 0
    if status == 'missing':
        raise SystemExit('의원 배열을 찾지 못했습니다. 다른 게임/슬롯이거나 구조가 다릅니다.')
    if len(fixed) != len(data):
        raise SystemExit('파일 길이가 바뀌었습니다. 저장하지 않습니다.')

    if args.in_place:
        backup = pathlib.Path(str(source) + '.d2assemblybak')
        if backup.exists():
            raise SystemExit(f'백업이 이미 있습니다. 중복 적용을 중단합니다: {backup}')
        shutil.copyfile(source, backup)
        target = source
        print(f'백업: {backup}')
    target.write_bytes(fixed)
    print(f'의원명: {len(converted)}/{COUNT} 변환')
    print(f'첫 항목: {converted[0][0]} -> {converted[0][1]} @ {converted[0][2]:#x}')
    print(f'마지막: {converted[-1][0]} -> {converted[-1][1]} @ {converted[-1][2]:#x}')
    print(f'완성: {target}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
