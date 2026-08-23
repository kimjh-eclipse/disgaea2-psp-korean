# -*- coding: utf-8 -*-
"""전각화 대상 선정 — SCRIPTPACK 멤버별 크기 예산을 지키는 최대 집합

배경 (HANDOFF 23-11)
  대사 렌더러가 고정 바이트 오프셋으로 줄을 자르므로 대사는 모든 문자가 2바이트여야 한다.
  그런데 **각 talk 멤버는 원본 크기를 넘으면 게임이 죽는다**(문자열 무변경 0 패딩으로 확정).
  총 파일 크기에는 상한이 없다.

  예산 B_m = 원본크기_m - 무변환크기_m.  문자열 s 를 전각화하면 s 를 담은 모든 멤버가
  d_s 바이트씩(그 멤버 내 등장 횟수만큼) 커진다. 모든 멤버가 예산을 지켜야 한다.

전략
  비용 오름차순 그리디로 개수를 최대화한다. 예산이 남는 멤버가 있어도 다른 멤버가 막으면
  그 문자열은 못 넣는다(문자열이 멤버 간 공유되므로).

사용
  python tools/pick_fw.py [여유바이트]     기본 여유 2048 (멤버당 안전 마진)
  -> work/fw_keys.txt 갱신
"""
import sys, os, io, glob, importlib.util, collections
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
os.chdir(ROOT)
sys.path.insert(0, HERE)
import scriptpack, talkfile, krtext

FW_MAP = {' ': '　', '.': '．', ',': '，', '!': '！', '?': '？', '~': '～',
          ':': '：', ';': '；', '(': '（', ')': '）', '-': '－', '/': '／'}


def fullwidth(t):
    return ''.join(FW_MAP.get(c, c) for c in t)


def main(margin=2048):
    T = {}
    for p in sorted(glob.glob('work/tr_talk*.py')):
        spec = importlib.util.spec_from_file_location('b', p)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        T.update(m.T)

    enc, encfw, delta = {}, {}, {}
    for jp, ko in T.items():
        k = jp.encode('cp932')
        a = krtext.encode(ko)
        b = krtext.encode(fullwidth(ko))
        enc[k] = a; encfw[k] = b; delta[k] = len(b) - len(a)

    ents = [e for e in scriptpack.unpack(open('jp/SCRIPTPACK.DAT', 'rb').read())
            if e['name'].startswith('talk') and talkfile.parse(e['data'])]

    # 멤버별: 무변환 크기, 예산, 문자열별 등장 횟수
    budget, cnt = {}, {}
    for e in ents:
        d = e['data']
        ed = {}
        c = collections.Counter()
        for off, raw in talkfile.strings(d):
            if raw in enc:
                ed[off] = enc[raw]; c[raw] += 1
        base = len(talkfile.rebuild(d, ed)) if ed else len(d)
        budget[e['name']] = len(d) - base - margin
        cnt[e['name']] = c
        print(f'  {e["name"]:18s} 원본 {len(d):8,} 무변환 {base:8,} 예산 {len(d)-base:7,}')

    # 문자열별 총 비용(참고) 과 멤버별 비용
    cand = [k for k in delta if delta[k] > 0]
    cand.sort(key=lambda k: sum(delta[k] * cnt[nm][k] for nm in cnt))

    used = collections.Counter()
    sel = []
    for k in cand:
        if all(used[nm] + delta[k] * cnt[nm][k] <= budget[nm] for nm in cnt):
            for nm in cnt:
                used[nm] += delta[k] * cnt[nm][k]
            sel.append(k)
    already = [k for k in delta if delta[k] == 0]      # 바꿀 게 없는 문자열(비용 0)

    print(f'\n전각화 필요 {len(cand)}건 중 선정 {len(sel)}건 ({100*len(sel)/len(cand):.1f}%)')
    print(f'비용 0(이미 전부 2바이트) {len(already)}건')
    print('멤버별 예산 사용:')
    for nm in sorted(cnt):
        print(f'  {nm:18s} {used[nm]:7,} / {budget[nm]:7,}')

    with open('work/fw_keys.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(k.decode('cp932') for k in sel + already) + '\n')
    print(f'\n-> work/fw_keys.txt ({len(sel)+len(already)}건)')
    return 0


if __name__ == '__main__':
    sys.exit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 2048))
