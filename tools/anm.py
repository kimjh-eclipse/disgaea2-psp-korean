# -*- coding: utf-8 -*-
"""Disgaea 2 Portable ANMPACK sprite-sheet image helpers.

The PSP SH variant has a 0x18-byte wrapper followed by an eight-u16 header,
nine relative section offsets, palette descriptors and sheet descriptors.
Only the indexed image portions are handled here; animation/keyframe data is
left untouched.
"""
from __future__ import annotations

import struct
from PIL import Image

from txp import swizzle, unswizzle


BASE = 0x18


def parse(data: bytes, base: int = BASE) -> dict:
    header = struct.unpack_from('<8H', data, base)
    offsets = struct.unpack_from('<9I', data, base + 0x10)
    animations, bundles, palette_count, sheet_count = header[:4]

    palettes = []
    palette_desc = base + offsets[3]
    for i in range(palette_count):
        off, count = struct.unpack_from('<II', data, palette_desc + i * 8)
        # External/sentinel descriptors use packed values rather than a count.
        if count > 256 or off == 0:
            palettes.append([])
            continue
        start = base + off
        palettes.append([
            tuple(data[start + j * 4:start + j * 4 + 4])
            for j in range(count)
        ])

    sheets = []
    sheet_desc = base + offsets[4]
    for i in range(sheet_count):
        bpp, tile_w, tile_h, mip, off, width, height = struct.unpack_from(
            '<BBBBIHH', data, sheet_desc + i * 12)
        sheets.append(dict(bpp=bpp, tile_w=tile_w, tile_h=tile_h, mip=mip,
                           off=off, width=width, height=height))

    return dict(base=base, header=header, offsets=offsets, palettes=palettes,
                sheets=sheets, animations=animations, bundles=bundles)


def decode_indices(data: bytes, sheet: dict, base: int = BASE) -> bytearray:
    width, height, bpp = sheet['width'], sheet['height'], sheet['bpp']
    if not width or not height or not sheet['off']:
        return bytearray()
    rowbytes = width if bpp == 8 else width // 2
    size = rowbytes * height
    start = base + sheet['off']
    raw = data[start:start + size]
    if sheet['tile_w'] and rowbytes >= 16 and height >= 8:
        raw = unswizzle(raw, rowbytes, height)
    if bpp == 8:
        return bytearray(raw)
    if bpp != 4:
        raise ValueError(f"unsupported ANM bpp: {bpp}")
    out = bytearray(width * height)
    for i, value in enumerate(raw):
        out[i * 2] = value & 0x0F
        out[i * 2 + 1] = value >> 4
    return out


def render(data: bytes, sheet_index: int, palette_index: int = 0,
           base: int = BASE) -> Image.Image:
    info = parse(data, base=base)
    sheet = info['sheets'][sheet_index]
    idx = decode_indices(data, sheet, base=base)
    palette = info['palettes'][palette_index]
    if not idx or not palette:
        return Image.new('RGBA', (max(1, sheet['width']), max(1, sheet['height'])))
    rgba = bytearray(len(idx) * 4)
    for i, value in enumerate(idx):
        color = palette[value] if value < len(palette) else (255, 0, 255, 255)
        rgba[i * 4:i * 4 + 4] = bytes(color)
    return Image.frombytes('RGBA', (sheet['width'], sheet['height']), bytes(rgba))


def encode_indices(data: bytes, sheet_index: int, indices: bytes,
                   base: int = BASE) -> bytes:
    """Replace one sheet's indices without changing any offsets or sizes."""
    info = parse(data, base=base)
    sheet = info['sheets'][sheet_index]
    width, height, bpp = sheet['width'], sheet['height'], sheet['bpp']
    if len(indices) != width * height:
        raise ValueError('index image size mismatch')
    if bpp == 8:
        raw = bytes(indices)
        rowbytes = width
    elif bpp == 4:
        raw = bytearray(width * height // 2)
        for i in range(0, len(indices), 2):
            raw[i // 2] = (indices[i] & 0x0F) | ((indices[i + 1] & 0x0F) << 4)
        raw = bytes(raw)
        rowbytes = width // 2
    else:
        raise ValueError(f"unsupported ANM bpp: {bpp}")
    if sheet['tile_w'] and rowbytes >= 16 and height >= 8:
        raw = swizzle(raw, rowbytes, height)
    out = bytearray(data)
    start = base + sheet['off']
    out[start:start + len(raw)] = raw
    return bytes(out)
