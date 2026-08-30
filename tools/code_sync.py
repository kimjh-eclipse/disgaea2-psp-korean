# -*- coding: utf-8 -*-
"""폰트 코드표와 START/SCRIPTPACK 재인코딩의 동기화 표식."""
import hashlib
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = ROOT / 'build_jp'


def fingerprint():
    digest = hashlib.sha256()
    for name in ('hangul_codes.tsv', 'moved_codes.tsv', 'talk00.dat'):
        data = (BUILD / name).read_bytes()
        digest.update(name.encode('ascii') + b'\0')
        digest.update(len(data).to_bytes(8, 'little'))
        digest.update(data)
    return digest.hexdigest()


def write_stamp(component):
    value = fingerprint()
    (BUILD / f'{component}.code.sha256').write_text(value + '\n', encoding='ascii')
    return value


def require_synced(*components):
    current = fingerprint()
    stale = []
    for component in components:
        path = BUILD / f'{component}.code.sha256'
        value = path.read_text(encoding='ascii').strip() if path.exists() else None
        if value != current:
            stale.append(component)
    if stale:
        raise RuntimeError(
            '폰트 코드표와 재인코딩 산출물이 불일치: ' + ', '.join(stale) + '\n'
            '코드 의존 산출물 전체(START, SCRIPTPACK, NAME, START_VM, CHAR)를 다시 빌드하십시오.')
    return current
