# -*- coding: utf-8 -*-
"""ISO9660 파일 교체 — 슬롯이 부족하면 ISO 끝에 재배치

- 슬롯 안에 들어가면 제자리 교체 (기존 레이아웃 유지)
- 넘치면 ISO 끝에 섹터 정렬로 추가하고 디렉터리 레코드의 LBA/크기를 갱신,
  PVD volume_space_size 도 함께 갱신한다. 기존 파일 데이터는 건드리지 않는다.
"""
import struct, os

SECTOR = 2048


def _find_record(dirsec, name):
    p = dirsec.find(name)
    if p < 0:
        return None
    return p - 33          # 디렉터리 레코드 시작


def replace(iso_path, dir_lba, name, data, slot_lba=None, slot_sectors=None):
    """name: bytes (예: b'SCRIPTPACK.DAT')"""
    f = open(iso_path, 'r+b')
    f.seek(dir_lba * SECTOR)
    dirsec = bytearray(f.read(SECTOR))
    rec = _find_record(dirsec, name)
    if rec is None:
        f.close()
        raise KeyError(f'{name!r} 레코드 없음')
    cur_lba = struct.unpack_from('<I', dirsec, rec + 2)[0]
    cur_size = struct.unpack_from('<I', dirsec, rec + 10)[0]

    # ★ 슬롯을 안 넘겨도, 새 데이터가 **그 파일이 이미 차지한 섹터 범위** 안에
    #   들어가면 제자리 교체한다. 예전에는 무조건 ISO 끝에 붙여서, 크기가 같은
    #   파일을 넣었는데도 ISO 가 커졌다(DUNGEON.DAT 13,208B -> ISO +14,336B).
    #   ISO 크기가 변하면 구간 패처(원본·패치본 크기 동일 전제)가 깨진다.
    if slot_sectors is None:
        own = (cur_size + SECTOR - 1) // SECTOR
        if own and len(data) <= own * SECTOR:
            slot_lba, slot_sectors = cur_lba, own
    slot = (slot_sectors * SECTOR) if slot_sectors else None
    if slot is not None and len(data) <= slot:
        # 제자리 교체
        f.seek((slot_lba or cur_lba) * SECTOR)
        f.write(data)
        f.write(bytes(slot - len(data)))
        new_lba = slot_lba or cur_lba
        where = '제자리'
    else:
        # ISO 끝에 추가
        f.seek(0, os.SEEK_END)
        end = f.tell()
        if end % SECTOR:
            f.write(bytes(SECTOR - end % SECTOR))
            end = f.tell()
        new_lba = end // SECTOR
        f.write(data)
        pad = (-len(data)) % SECTOR
        if pad:
            f.write(bytes(pad))
        where = f'ISO 끝(LBA {new_lba})'
        # PVD volume_space_size 갱신
        total = f.tell() // SECTOR
        f.seek(16 * SECTOR)
        pvd = bytearray(f.read(SECTOR))
        struct.pack_into('<I', pvd, 80, total)
        struct.pack_into('>I', pvd, 84, total)
        f.seek(16 * SECTOR); f.write(pvd)

    struct.pack_into('<I', dirsec, rec + 2, new_lba)
    struct.pack_into('>I', dirsec, rec + 6, new_lba)
    struct.pack_into('<I', dirsec, rec + 10, len(data))
    struct.pack_into('>I', dirsec, rec + 14, len(data))
    f.seek(dir_lba * SECTOR); f.write(dirsec)
    f.close()
    return dict(lba=new_lba, size=len(data), where=where,
                old_lba=cur_lba, old_size=cur_size)
