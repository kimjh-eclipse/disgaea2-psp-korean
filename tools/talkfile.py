# -*- coding: utf-8 -*-
"""talkXX_jp.dat / scriptXX.dat 구조 파서 + 문자열 패치 (길이 변경 지원)

※ 선행바이트 범위는 0x81-0x9F / 0xE0-0xFC. 한글 코드가 0xF0~0xFC 이므로
  0xEF 까지만 보면 번역된 파일의 문자열을 탐지하지 못한다(실제로 겪음).

포맷
  +0x00  u32 count
  +0x04  u32 count (중복)
  +0x08  record[count], 각 0x20 바이트
           +0x00 u32 stream_offset  ← 레코드 테이블 끝 기준 바이트코드 오프셋
           +0x04 ...               (나머지 필드는 그대로 보존)
  table_end = 8 + count*0x20
  이후      바이트코드 스트림. 문자열은 `01 <SJIS...> 00` 패턴으로 인라인.

길이를 바꾸면 record.stream_offset 을 전부 보정해야 한다(rebuild 가 처리).
"""
import struct

REC = 0x20


def parse(data):
    cnt = struct.unpack('<I', data[:4])[0]
    cnt2 = struct.unpack('<I', data[4:8])[0]
    table_end = 8 + cnt * REC
    if cnt != cnt2 or table_end > len(data):
        return None                      # 이 포맷이 아님
    offs = [struct.unpack_from('<I', data, 8 + i * REC)[0] for i in range(cnt)]
    if any(o > len(data) - table_end for o in offs):
        return None
    if any(offs[i + 1] < offs[i] for i in range(cnt - 1)):
        return None                      # 단조증가여야 함
    return dict(count=cnt, table_end=table_end, offs=offs)


def _sjis_runs(data, lo, hi, minjp=1):
    """[lo,hi) 구간에서 `01 <SJIS> 00` 패턴만 추출 -> [(start, raw)]"""
    res = []
    i = lo
    n = hi
    while i < n:
        if data[i] != 0x01:
            i += 1
            continue
        j = i + 1
        jp = 0
        while j < n:
            b = data[j]
            if 0x20 <= b < 0x7f:
                j += 1
            elif (0x81 <= b <= 0x9f or 0xe0 <= b <= 0xfc) and j + 1 < n \
                    and 0x40 <= data[j + 1] <= 0xfc and data[j + 1] != 0x7f:
                jp += 1
                j += 2
            else:
                break
        if j < n and data[j] == 0x00 and jp >= minjp and j > i + 1:
            res.append((i + 1, bytes(data[i + 1:j])))
            i = j + 1
        else:
            i += 1
    return res


def strings(data, minjp=1):
    info = parse(data)
    if not info:
        return []
    return _sjis_runs(data, info['table_end'], len(data), minjp)


def rebuild(data, edits):
    """edits: {abs_offset: new_bytes}. 길이 변경 허용 — stream_offset 자동 보정."""
    info = parse(data)
    if not info:
        raise ValueError('지원하지 않는 포맷')
    te = info['table_end']
    items = sorted(edits.items())
    for off, _ in items:
        if off < te:
            raise ValueError(f'스트림 밖 오프셋 {off:#x}')

    # 새 스트림 조립 + (old_pos -> delta) 누적 맵
    out = bytearray(data[te:])            # 스트림만 따로
    # 뒤에서부터 치환하면 앞쪽 오프셋이 안 밀림
    deltas = []                           # (old_stream_pos, delta)
    for off, new in reversed(items):
        s = off - te
        old = _read_until_nul(out, s)
        out[s:s + len(old)] = new
        deltas.append((s, len(new) - len(old)))
    deltas.sort()

    def shift(old_off):
        """old stream offset -> new stream offset"""
        acc = 0
        for pos, dl in deltas:
            if pos < old_off:
                acc += dl
            else:
                break
        return old_off + acc

    head = bytearray(data[:te])
    for i, o in enumerate(info['offs']):
        struct.pack_into('<I', head, 8 + i * REC, shift(o))
    return bytes(head) + bytes(out)


def _read_until_nul(buf, s):
    e = s
    while e < len(buf) and buf[e] != 0:
        e += 1
    return bytes(buf[s:e])
