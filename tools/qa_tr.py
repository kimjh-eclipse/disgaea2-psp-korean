# -*- coding: utf-8 -*-
"""서브에이전트 번역 결과 품질 검사

검사 항목
 1. 키 정합성 — 청크 원문과 정확히 일치하는가 (누락/오타/추가)
 2. 인코딩 — 게임 글리프로 표현 가능한가 (한자·가나·전각영숫자 검출)
 3. 서식 지정자 — %s %d 등 개수 일치
 4. 자리표시자 — ＄ ＃ § 개수 일치
 5. 빈 값 / 원문 그대로 방치
 6. 용어 일관성 — 같은 원문에 다른 번역, 금지 용어 사용
"""
import sys, os, io, glob, re, importlib.util, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
sys.path.insert(0, HERE)
import krtext

FMT = re.compile(r'%[0-9]*[sdxXc%]')
PLACE = ('＄', '＃', '§')

# 금지 용어 -> 올바른 용어 (일관성)
BANNED = {
    '아이템 월드': '아이템계',
    '마 체인지': '마체인지',
    '다크 썬': '다크 태양',
    '암흑 태양': '다크 태양',
    '이노센트 마을': '이노센트 타운',
    '베이스패널': '베이스 패널',
    '로젠 퀸': '로젠퀸',
}


def load(p):
    spec = importlib.util.spec_from_file_location('b', p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.T


def check(tr_glob, chunk_glob=None):
    problems = collections.Counter()
    details = collections.defaultdict(list)
    merged = {}
    conflicts = []

    files = sorted(glob.glob(tr_glob))
    for p in files:
        try:
            T = load(p)
        except Exception as e:
            print(f'  !! {os.path.basename(p)} 로드 실패: {e}')
            problems['load'] += 1
            continue
        for k, v in T.items():
            if k in merged and merged[k] != v:
                conflicts.append((k, merged[k], v, os.path.basename(p)))
            merged[k] = v
        print(f'  {os.path.basename(p):26s} {len(T)}건')

    # 청크 원문과 키 대조
    if chunk_glob:
        src = set()
        for c in sorted(glob.glob(chunk_glob)):
            for line in open(c, encoding='utf-8').read().split('\n'):
                if line != '':
                    src.add(line)
        missing = src - set(merged)
        extra = set(merged) - src
        if missing:
            problems['키누락'] = len(missing)
            details['키누락'] = list(missing)[:10]
        if extra:
            problems['키불일치(원문에 없음)'] = len(extra)
            details['키불일치(원문에 없음)'] = list(extra)[:10]

    for k, v in merged.items():
        # 원문이 공백·기호만인 항목은 같은 값으로 두는 것이 규칙이다(GLOSSARY 4절).
        # 번역할 것이 없으므로 빈값/원문방치 검사에서 제외한다.
        passthru = not any(ch.isalnum() for ch in k)
        if not v.strip() and not passthru:
            problems['빈값'] += 1; details['빈값'].append(k)
        if v == k and not passthru:
            problems['원문방치'] += 1; details['원문방치'].append(k)
        bad = krtext.validate(v)
        if bad:
            problems['인코딩불가'] += 1
            details['인코딩불가'].append(f'{k} -> {v}  [{"".join(sorted(set(bad)))}]')
        # 전각 ％ 는 양쪽 모두 정규화 (한쪽만 하면 정상 번역이 오탐된다)
        if len(FMT.findall(k.replace('％', '%'))) != len(FMT.findall(v.replace('％', '%'))):
            problems['서식지정자'] += 1
            details['서식지정자'].append(f'{k} -> {v}')
        for ph in PLACE:
            if k.count(ph) != v.count(ph):
                problems['자리표시자'] += 1
                details['자리표시자'].append(f'{k} -> {v}')
                break
        for b, good in BANNED.items():
            if b in v:
                problems['용어위반'] += 1
                details['용어위반'].append(f'{v}  ({b} -> {good})')
                break

    if conflicts:
        problems['배치간충돌'] = len(conflicts)
        details['배치간충돌'] = [f'{k}: {a!r} vs {b!r} ({f})' for k, a, b, f in conflicts[:10]]

    print(f'\n총 {len(merged)}건')
    if not problems:
        print('=== 문제 없음 ===')
        return 0
    print('=== 문제 ===')
    for k, n in problems.items():
        print(f'  {k}: {n}건')
        for d in details[k][:6]:
            print(f'      {d}')
    return 1


if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'iptxt'
    if which == 'iptxt':
        rc = check('work/tr_iptxt*.py', 'work/chunks/iptxt_*.txt')
    elif which == 'talk':
        rc = check('work/tr_talk*.py', 'work/chunks/talk_*.txt')
    else:
        rc = check(f'work/tr_{which}*.py')
    sys.exit(rc)
