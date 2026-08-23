# -*- coding: utf-8 -*-
"""한글 음절 선정 — 폰트 칸이 상용 2,350자보다 적을 때 무엇을 넣을지 정한다

칸 수는 후행바이트 제약 때문에 1,625자다 (krfont.TRAIL_BASE 주석 참고).
상용 2,350자에서 725자를 빼야 하므로 "희귀한 것만 빼는" 방식(구 RARE_POOL)으로는
부족하다. 대신 다음 순서로 채운다.

  1) `must` — 현재 번역이 실제로 쓰는 음절. **무조건 포함** (self-healing)
  2) 남은 칸 — 우리 번역 말뭉치에서 산출한 자모 빈도 점수 순
  3) RARE_POOL — 실제 한국어에 안 나타나는 조합. 항상 맨 뒤

2) 의 점수는 외부 corpus 가 아니라 **이 프로젝트의 번역문 자체**에서 뽑는다.
과거에 자모 빈도 휴리스틱이 `꺾 끊 넓 몫 삶` 같은 실사용 음절을 잘라낸 사고가 있었지만,
그 음절들은 이제 1) 에서 강제 포함되므로 순위와 무관하다. 순위는 "아직 안 쓰였지만
나중에 쓸 만한" 438자를 고르는 데만 쓴다.
"""
import os, glob, importlib.util, collections

# 실제 한국어 표기에 나타나지 않는 음절 (겹받침 오조합 등). 항상 최하위.
RARE_POOL = (
    '갊걺곬굻긺깖뀁뀄뀝끎낢넒놂늚닒덞돎떪뜁륏맒멂몲묾밂밗밞벎붊빎빪뺙'
    '섟솖싻썲쏢쐤쒔쓺쓿얾엾옰욺읔읾잚쟎졺줆쫬쬈쭸챦췻캭컫큇턺퉜튁틂팖'
    '폣풂퓟헒홅휫흖뷁뷔쉔쐐쒜쓩앝앳얩옜웍웡윰읗읬잗잤쨈쩰쪗쬬쮸쯍찡챤'
)

_L, _V, _T = 588, 28, 1        # 초성/중성/종성 자리값


def ksx1001():
    """KS X 1001 완성형 2350자 (EUC-KR 0xB0A1..0xC8FE 순서)"""
    out = []
    for c1 in range(0xB0, 0xC9):
        for c2 in range(0xA1, 0xFF):
            try:
                out.append(bytes([c1, c2]).decode('euc-kr'))
            except UnicodeDecodeError:
                pass
    return out


def _jamo(ch):
    n = ord(ch) - 0xAC00
    return n // _L, (n % _L) // _V, n % _V


def corpus_counts(root=None):
    """번역문 전체에서 (초성, 중성, 종성) 등장 횟수를 센다"""
    root = root or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
    L = collections.Counter(); V = collections.Counter(); T = collections.Counter()
    for p in sorted(glob.glob(os.path.join(root, 'work', 'tr_*.py'))):
        try:
            spec = importlib.util.spec_from_file_location('h', p)
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
        except Exception:
            continue
        for v in m.T.values():
            for ch in v:
                if 0xAC00 <= ord(ch) <= 0xD7A3:
                    a, b, c = _jamo(ch)
                    L[a] += 1; V[b] += 1; T[c] += 1
    return L, V, T


def pick(limit, must=()):
    """limit 개 선정. must 는 반드시 포함. 남은 칸은 말뭉치 자모 빈도 순."""
    all_ = ksx1001()
    aset = set(all_)
    must = {c for c in must if c in aset}
    if len(must) > limit:
        raise ValueError(f'실사용 음절 {len(must)}자 > 칸 {limit}개. 코드 용량을 늘려야 함.')
    if len(all_) <= limit:
        return all_

    L, V, T = corpus_counts()
    rare = set(RARE_POOL) & aset

    def score(ch):
        a, b, c = _jamo(ch)
        # 로그 대신 단순 곱 — 순위만 쓰므로 충분하다
        return (L[a] + 1) * (V[b] + 1) * (T[c] + 1)

    rest = [c for c in all_ if c not in must]
    rest.sort(key=lambda c: (c in rare, -score(c)))
    keep = must | set(rest[:limit - len(must)])
    return [c for c in all_ if c in keep]     # 원래 코드 순서 유지


def dropped(limit, must=()):
    keep = set(pick(limit, must))
    return [c for c in ksx1001() if c not in keep]
