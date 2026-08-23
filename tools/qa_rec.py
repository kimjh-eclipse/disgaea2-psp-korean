# -*- coding: utf-8 -*-
"""고정 레코드 DB 번역 품질 검사 — qa_tr.py 와 같지만 **바이트 예산**을 추가로 본다.

청크 형식은 `<예산>\t<원문>` 이므로 키 대조 시 탭 앞을 떼어내야 한다.
"""
import sys, os, io, glob, re, importlib.util, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
sys.path.insert(0, HERE)
import krtext

FMT = re.compile(r'%[0-9]*[sdxXc%]')


def main():
    budget = {}
    for line in open('work/rec_inventory.tsv', encoding='utf-8').read().splitlines()[1:]:
        b, _occ, jp = line.split('\t', 2)
        budget[jp] = int(b)

    merged = {}
    conflicts = []
    for p in sorted(glob.glob('work/tr_rec*.py')):
        spec = importlib.util.spec_from_file_location('b', p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        for k, v in m.T.items():
            if k in merged and merged[k] != v:
                conflicts.append((k, merged[k], v))
            merged[k] = v
        print(f'  {os.path.basename(p):22s} {len(m.T)}건')

    prob = collections.Counter()
    det = collections.defaultdict(list)

    for k in set(budget) - set(merged):
        prob['미번역'] += 1; det['미번역'].append(k)
    for k in set(merged) - set(budget):
        prob['원문에 없는 키'] += 1; det['원문에 없는 키'].append(k)

    for k, v in merged.items():
        if k not in budget:
            continue
        bad = krtext.validate(v)
        if bad:
            prob['인코딩불가'] += 1
            det['인코딩불가'].append(f'{k} -> {v}  [{"".join(sorted(set(bad)))}]')
            continue                      # 인코딩 불가면 길이 측정 불가
        n = len(krtext.encode(v))
        if n > budget[k]:
            prob['예산초과'] += 1
            det['예산초과'].append(f'{k} -> {v}  ({n}B > {budget[k]}B)')
        if not v.strip() and k.strip():
            prob['빈값'] += 1; det['빈값'].append(k)
        if len(FMT.findall(k.replace('％', '%'))) != len(FMT.findall(v)):
            prob['서식지정자'] += 1; det['서식지정자'].append(f'{k} -> {v}')
    if conflicts:
        prob['배치간충돌'] = len(conflicts)
        det['배치간충돌'] = [f'{k}: {a!r} vs {b!r}' for k, a, b in conflicts[:10]]

    print(f'\n원문 {len(budget)}건 / 번역 {len(merged)}건')
    if not prob:
        print('=== 문제 없음 ===')
        return 0
    print('=== 문제 ===')
    for k, n in prob.items():
        print(f'  {k}: {n}건')
        for d in det[k][:8]:
            print(f'      {d}')
    return 1


if __name__ == '__main__':
    sys.exit(main())
