# -*- coding: utf-8 -*-
"""talk*_jp.dat 전체에서 문자열 추출 + 원문바이트 기준 중복 제거 -> work/talk_inventory.tsv"""
import sys, os, io, csv, glob, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
sys.path.insert(0, HERE)
import talkfile


def build():
    uniq = collections.OrderedDict()      # raw -> dict(text, occ=[(file, off)])
    files = sorted(glob.glob('jp/scriptpack/talk*_jp.dat'))
    for p in files:
        d = open(p, 'rb').read()
        nm = os.path.basename(p)
        for off, raw in talkfile.strings(d):
            e = uniq.get(raw)
            if e is None:
                try:
                    txt = raw.decode('cp932')
                except Exception:
                    continue
                e = uniq[raw] = dict(text=txt, occ=[])
            e['occ'].append((nm, off))
    return uniq, files


def main():
    uniq, files = build()
    occ = sum(len(e['occ']) for e in uniq.values())
    jpc = sum(sum(1 for c in e['text'] if ord(c) > 0x7f) for e in uniq.values())
    print(f'파일 {len(files)}개 / 등장 {occ}회 / 고유 {len(uniq)}건 / 일본어 {jpc}자')
    lens = sorted(len(r) for r in uniq)
    print(f'바이트 길이: 중간값 {lens[len(lens)//2]}, 평균 {sum(lens)//len(lens)}, 최대 {lens[-1]}')
    os.makedirs('work', exist_ok=True)
    with open('work/talk_inventory.tsv', 'w', encoding='utf-8', newline='') as f:
        w = csv.writer(f, delimiter='\t')
        w.writerow(['n', 'bytes', 'occ', 'jp', 'ko'])
        for i, (raw, e) in enumerate(uniq.items()):
            w.writerow([i, len(raw), len(e['occ']), e['text'], ''])
    print('-> work/talk_inventory.tsv')


if __name__ == '__main__':
    main()
