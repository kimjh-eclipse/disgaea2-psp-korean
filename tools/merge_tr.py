# -*- coding: utf-8 -*-
"""번역 배치 파일(work/tr_batch*.py)들을 모아 work/ko_script00.tsv 생성 + 검증"""
import sys, os, csv, glob, importlib.util, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
sys.path.insert(0, HERE)
import krtext
from textio import dump

def load_batch(path):
    spec = importlib.util.spec_from_file_location('b', path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.T

def main():
    src = {r['id']: r for r in dump(open('jp/start/script00.dat','rb').read())
           if False}  # placeholder
    rows = dump(open('jp/start/script00.dat','rb').read())
    jp = {r['id']: r['text'] for r in rows}
    merged = {}
    dupes = []
    for p in sorted(glob.glob('work/tr_batch*.py')):
        T = load_batch(p)
        for k, v in T.items():
            if k in merged and merged[k] != v:
                dupes.append((k, p))
            merged[k] = v
        print(f'  {os.path.basename(p)}: {len(T)}건')
    if dupes:
        print('!! 배치 간 충돌:', dupes)
    # 검증
    bad_enc = []
    bad_fmt = []
    for k, v in merged.items():
        b = krtext.validate(v)
        if b: bad_enc.append((k, b, v))
        # 서식 지정자 보존 검사
        o = jp.get(k, '')
        for spec in ('%s', '%d', '%2d'):
            if o.count(spec) != v.count(spec) and spec != '%d':
                pass
        if o.count('%') != v.count('%'):
            bad_fmt.append((k, o, v))
    print(f'번역 총 {len(merged)}건 / 미번역 {sum(1 for k,t in jp.items() if t and any(ord(c)>0x7f for c in t)) - len(merged)}건 남음')
    if bad_enc:
        print(f'!! 인코딩 불가 {len(bad_enc)}건')
        for k, b, v in bad_enc[:12]: print(f'   {k:#05x} {b} : {v}')
    if bad_fmt:
        print(f'!! 서식지정자(%) 개수 불일치 {len(bad_fmt)}건')
        for k, o, v in bad_fmt[:12]: print(f'   {k:#05x} JP:{o!r} KO:{v!r}')
    with open('work/ko_script00.tsv','w',encoding='utf-8',newline='') as f:
        w = csv.writer(f, delimiter='\t'); w.writerow(['id','ko'])
        for k in sorted(merged): w.writerow([f'{k:#05x}', merged[k]])
    print('-> work/ko_script00.tsv')
    return len(bad_enc) + len(bad_fmt)

if __name__ == '__main__':
    sys.exit(1 if main() else 0)
