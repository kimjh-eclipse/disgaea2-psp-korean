# -*- coding: utf-8 -*-
"""캐릭터 도감(tower.dat)의 모든 표시 문자열 번역/주입 상태를 감사한다."""
import glob
import importlib.util
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
sys.path.insert(0, HERE)

from nislzs import decompress

JP = re.compile(r'[\u3040-\u30ff\u3400-\u9fff]')


def translations():
    out = {}
    for path in sorted(glob.glob('work/tr_names_*.py')):
        spec = importlib.util.spec_from_file_location('zukan_translation', path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        out.update(mod.T)
    return out


def chunks(data):
    """NUL 경계마다 앞쪽 VM 제어바이트 0~7개를 건너뛴 후보를 만든다."""
    pos = 0
    while pos < len(data):
        end = data.find(b'\0', pos)
        if end < 0:
            end = len(data)
        raw = data[pos:end]
        candidates = []
        for skip in range(min(8, len(raw))):
            try:
                text = raw[skip:].decode('cp932')
            except UnicodeDecodeError:
                continue
            if JP.search(text):
                candidates.append((skip, text))
        if candidates:
            yield pos, raw, candidates
        pos = end + 1


def main():
    table = translations()
    source = open('jp/vm/tower.dat', 'rb').read()
    built = decompress(open('build_jp/START_VM_JP.LZS', 'rb').read())
    found = []
    missing = []
    for off, raw, candidates in chunks(source):
        hit = next(((skip, text) for skip, text in candidates if text in table), None)
        if hit is None:
            # 제어바이트가 가장 적고 사람이 읽을 일본어가 긴 후보를 보고한다.
            best = max(candidates, key=lambda q: (len(JP.findall(q[1])), -q[0]))
            missing.append((off + best[0], best[1]))
            continue
        skip, jp = hit
        found.append(jp)

    residual = [jp for jp in dict.fromkeys(found) if jp.encode('cp932') in built]
    print(f'도감 문자열 {len(found) + len(missing)}개 / 번역표 {len(found)}개 / 누락 {len(missing)}개')
    print(f'빌드 원문 잔존 {len(residual)}개')
    for off, text in missing:
        print(f'  !! 번역표 누락 0x{off:X}: {text}')
    for text in residual:
        print(f'  !! 빌드 원문 잔존: {text}')
    return 1 if missing or residual else 0


if __name__ == '__main__':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    raise SystemExit(main())
