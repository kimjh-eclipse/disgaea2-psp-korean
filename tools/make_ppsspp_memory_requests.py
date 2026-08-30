# -*- coding: utf-8 -*-
"""PPSSPP WebSocket 디버거용 읽기 전용 메모리 검색 요청을 만든다."""
import base64
import glob
import importlib.util
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
os.chdir(ROOT)

import hangul_rank
from krfont import HANGUL_LIMIT, n_to_code
from krtext import encode as stable_encode


def used():
    out = set()
    for n, path in enumerate(sorted(glob.glob('work/tr_*.py'))):
        spec = importlib.util.spec_from_file_location('ramdiag_' + str(n), path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for value in mod.T.values():
            out |= {c for c in value if 0xAC00 <= ord(c) <= 0xD7A3}
    return out


def encoder(chars, text):
    table = {ch: bytes(n_to_code(i)) for i, ch in enumerate(chars)}
    out = bytearray()
    for ch in text:
        if ch in table:
            out += table[ch]
        elif 0x20 <= ord(ch) < 0x7F:
            out.append(ord(ch))
        else:
            out += ch.encode('cp932')
    return bytes(out)


def main():
    texts = sys.argv[1:] or ['연무', '동굴', '게이트', '열기', '군자금', '필요해']
    unstable_chars = hangul_rank.pick(HANGUL_LIMIT, must=used())
    requests = [{'event': 'version', 'ticket': 'version'}]
    rendered = []
    for text in texts:
        variants = {
            f'stable:{text}': stable_encode(text),
            f'unstable-v20260830:{text}': encoder(unstable_chars, text),
        }
        for label, raw in variants.items():
            requests.append({
                'event': 'memory.search',
                'ticket': label,
                'address': 0x08000000,
                'size': 0x02000000,
                'type': 'bytes',
                'base64': base64.b64encode(raw).decode('ascii'),
                'maxResults': 100,
            })
            rendered.append((label, raw))
    output = ROOT / 'work' / 'ppsspp_memory_requests.json'
    output.write_text(json.dumps(requests, ensure_ascii=False, indent=2), encoding='utf-8')
    print(output)
    for label, raw in rendered:
        print(label, raw.hex())


if __name__ == '__main__':
    main()
