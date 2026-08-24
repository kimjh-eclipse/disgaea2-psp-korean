# -*- coding: utf-8 -*-
"""고정 레코드 DB (HABIT / dungeon / charhelp / magic / mitem / music) 문자열 필드 입출력

포맷 (6개 파일 공통)
  +0x00  u32 count
  +0x04  u32 count (중복)
  +hdr   record[count], 각 rs 바이트. 문자열 필드는 레코드 내 고정 오프셋·고정 폭.

talk 계열과 달리 **필드 폭이 고정**이다. 번역문이 폭을 넘으면 다음 필드를 침범하므로
put() 이 예외를 던진다. 종단 NUL 1바이트를 위해 실제 가용은 (w-1) 바이트.

한글은 이 인코딩에서 2바이트/음절 = 한자와 동일하므로, 원문이 한자 위주면 대개 들어가고
가나 위주(1바이트 아님, 가나도 2바이트)여도 동일하다. 문제는 ASCII 위주 원문뿐이다.
"""
import struct

# 파일 -> (헤더크기, 레코드크기, [(필드오프셋, 필드폭), ...])
# 바이너리 필드는 제외하고 실제 텍스트 필드만 등록한다.
#
# ★★ 폭을 넉넉하게 잡으면 안 된다 — 문자열 뒤가 바이너리인 필드가 있다.
#   레코드 크기까지 폭을 늘려 잡았다가 **아이템 DB 의 무기 종류·사거리·공격력을
#   전부 0 으로 지웠다.** 인게임 증상: 무기를 껴도 `공격` 이 동작하지 않음(사용자 제보).
#     HABIT.dat   +0x15  87 -> 57   (344 레코드 x 30B 소실)
#     dungeon.dat +0x00  64 -> 32   (119 레코드 x 32B 소실)
#     mitem.dat   +0x20  72 -> 64   ( 77 레코드 x  8B 소실)
#   산출 근거: 원본에서 (문자열 최대길이+1) <= (NUL 뒤 첫 0 아닌 바이트의 최소 위치).
#   폭 정정과 별개로 put() 이 꼬리를 아예 건드리지 않게 고쳤다(이중 안전장치).
#   검사 도구: tools/check_recdat.py
SPEC = {
    'HABIT.dat':    (8,  120, [(0x00, 21), (0x15, 57)]),
    'dungeon.dat':  (8,   64, [(0x00, 32)]),
    'charhelp.dat': (8,   80, [(0x00, 22)]),
    'magic.dat':    (8,  152, [(0x00, 50), (0x32, 50), (0x64, 50)]),
    'mitem.dat':    (16, 104, [(0x08, 24), (0x20, 64)]),
    'music.dat':    (8,  140, [(0x28, 47), (0x57, 53)]),
    # 스킬 DB (372 x 112). +0x00 u16 스킬ID / +0x02 이름 / +0x19 설명
    # ★ 설명 필드는 선언상 87 이 들어가지만(0x19+87=112 로 레코드를 꽉 채움)
    #   **진짜 폭은 57** 이다. 그 뒤 30바이트가 위력·거리·범위·SP 파라미터다.
    #   87 로 썼으면 372개 스킬 전부를 또 망가뜨렸다 (HABIT.dat 과 동일한 함정).
    'char.dat':     (16, 112, [(0x02, 23), (0x19, 57)]),
}


# ISO 루트(/PSP_GAME/USRDIR) 에 있는 같은 형식의 파일. START 안이 아니라 별도로 읽는다.
# ★ 지명 간판(`ホルルト村`)의 출처가 여기다. "이미지라서 못 찾았다"고 결론냈던 것은
#   패치 대상 파일만 훑은 결과였다 — 전수 탐색(tools/find_string.py)으로 찾았다.
#   레코드 +0x16 부터 u16 스테이지 ID 등 바이너리가 붙어 있으므로 폭은 22 를 넘기면 안 된다.
ROOT_SPEC = {
    'DUNGEON.DAT':  (8, 0x50, [(0x00, 22)]),
}


def spec(name):
    """SPEC(START 내부) 과 ROOT_SPEC(ISO 루트) 를 함께 찾는다"""
    if name in SPEC:
        return SPEC[name]
    return ROOT_SPEC[name]


def count(data):
    a, b = struct.unpack_from('<II', data, 0)
    if a != b:
        raise ValueError(f'count 불일치 {a} != {b}')
    return a


def items(name, data):
    """[(rec_index, field_offset, width, raw_bytes)] — 비어있지 않은 필드만"""
    hdr, rs, fields = spec(name)
    n = count(data)
    if hdr + n * rs > len(data):
        raise ValueError('레코드 영역이 파일보다 큼')
    out = []
    for i in range(n):
        b = hdr + i * rs
        for off, w in fields:
            s = data[b + off:b + off + w]
            e = s.find(0)
            s = s[:e] if e >= 0 else s
            if s:
                out.append((i, off, w, bytes(s)))
    return out


def capacity(name, data, i, off):
    """레코드 i / 필드 off 에 실제로 쓸 수 있는 바이트 수 (종단 NUL 제외).

    선언 폭을 그대로 믿지 않는다. **원본 문자열의 NUL 뒤에 0 아닌 바이트가 있으면
    그 앞까지만** 쓸 수 있다 — 그 뒤는 바이너리 데이터다(무기 종류·사거리 등).
    이 검사가 없어서 아이템 DB 를 통째로 망가뜨린 적이 있다(SPEC 주석 참고).
    """
    hdr, rs, fields = spec(name)
    w = {o: ww for o, ww in fields}[off]
    b = hdr + i * rs + off
    f = data[b:b + w]
    e = f.find(0)
    if e < 0:
        return w                     # 종단 없음 = 폭을 꽉 쓰는 문자열
    for j in range(e + 1, w):
        if f[j]:
            return j - 1             # 꼬리 데이터 앞까지 (NUL 자리 확보)
    return w - 1


def put(name, data, edits):
    """edits: {(rec_index, field_offset): new_bytes}. 용량 초과는 예외.

    ★ 문자열 + 종단 NUL 만 쓰고 **그 뒤는 원본 그대로 남긴다.**
      예전에는 필드 폭 전체를 NUL 로 채워 뒤따르는 바이너리를 지웠다.
      게임은 NUL 까지만 읽으므로 남은 잉여 바이트는 무해하다.
    """
    hdr, rs, fields = spec(name)
    out = bytearray(data)
    for (i, off), new in edits.items():
        cap = capacity(name, data, i, off)
        if len(new) > cap:
            raise ValueError(f'{name} rec{i} +{off:#x}: {len(new)}B > 가용 {cap}B')
        b = hdr + i * rs + off
        out[b:b + len(new) + 1] = new + b'\0'
    return bytes(out)
