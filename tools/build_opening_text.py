# -*- coding: utf-8 -*-
"""Korean opening text -> ANMPACK/anm7101.dat -> ISO.

The opening background is TXPPACK/wbg06.txp.  The narration is a separate
512x512, 4-bpp swizzled atlas stored in the final 0x20720-byte resource of
ANMPACK/anm7101.dat:

  resource +0x0320: 16-entry RGBA palette
  resource +0x0720: 512x512 packed indices (low nibble first, PSP swizzled)

The ImageGen edit in work/opening_text_kr_imagegen.png is retained as the
layout reference.  Final glyphs are rendered from a local Korean font into
separate fill/outline masks before conversion to the original 16-color
palette.  Keeping those masks separate prevents light raster noise from
turning into black holes inside glyphs.
"""
from pathlib import Path
import argparse
import shutil
import struct
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import scriptpack
from txp import swizzle


SOURCE_IMAGE = ROOT / "work/opening_text_kr_imagegen.png"
BASE_ISO = ROOT / "build_jp/D2_JP_KR_title.iso"
OUTPUT_ISO = ROOT / "build_jp/D2_JP_KR_opening.iso"
ANMPACK_LBA = 282896
ANMPACK_SIZE = 68324111
MEMBER = "anm7101.dat"
RESOURCE_OFFSET = 0x40660
RESOURCE_SIZE = 0x20720
PALETTE_OFFSET = 0x320
PIXEL_OFFSET = 0x720
WIDTH = HEIGHT = 512
ORIGINAL_TEXT_BOUNDS = (1, 2, 509, 368)
FONT_PATH = Path(r"C:\Windows\Fonts\malgunbd.ttf")
FONT_SIZE = 24
SUPERSAMPLE = 4
STROKE_WIDTH = 1.5
KOREAN_LINES = (
    "마계…….",
    "그것은 우주에 만연한 사악한 세계.",
    "흉악한 자들이 본능대로 살아가는",
    "무질서한 마의 대지…….",
    "마왕이라 불리는 권력자들의 손에서",
    "지배, 멸망, 부흥, 분열을 거듭하며,",
    "수천 수만 나라로 불어난 마계는",
    "우주에 끝없는 혼돈을 가져왔다.",
    "그리고, 새롭게 또 하나,",
    "마계의 어둠에 삼켜지려는",
    "세계가 있었다…….",
)


def rgba_palette(resource):
    start = PALETTE_OFFSET
    return [tuple(resource[start + i * 4:start + i * 4 + 4]) for i in range(16)]


def imagegen_layout(path):
    gray = Image.open(path).convert("L")
    # ImageGen returned a real light checkerboard rather than alpha.  All
    # lettering lies below 240; the board starts at roughly 244.
    mask = gray.point(lambda value: 255 if value < 240 else 0)
    bounds = mask.getbbox()
    if not bounds:
        raise ValueError("ImageGen result contains no detectable text")
    cropped = gray.crop(bounds)
    target_height = ORIGINAL_TEXT_BOUNDS[3] - ORIGINAL_TEXT_BOUNDS[1]
    scale = target_height / cropped.height
    target_width = round(cropped.width * scale)
    fitted = mask.crop(bounds).resize(
        (target_width, target_height), Image.Resampling.LANCZOS
    )
    occupied = [fitted.crop((0, y, target_width, y + 1)).getbbox() is not None
                for y in range(target_height)]
    rows = []
    start = None
    for y, present in enumerate(occupied + [False]):
        if present and start is None:
            start = y
        elif not present and start is not None:
            rows.append((start + ORIGINAL_TEXT_BOUNDS[1],
                         y - 1 + ORIGINAL_TEXT_BOUNDS[1]))
            start = None
    if len(rows) != len(KOREAN_LINES):
        raise ValueError(f"expected 11 ImageGen text rows, found {len(rows)}")
    return rows, bounds


def render_clean_indices(rows):
    scale = SUPERSAMPLE
    size = (WIDTH * scale, HEIGHT * scale)
    fill = Image.new("L", size, 0)
    whole = Image.new("L", size, 0)
    fill_draw = ImageDraw.Draw(fill)
    whole_draw = ImageDraw.Draw(whole)
    font = ImageFont.truetype(str(FONT_PATH), FONT_SIZE * scale)
    stroke = round(STROKE_WIDTH * scale)

    for text, (top, bottom) in zip(KOREAN_LINES, rows):
        center_y = (top + bottom + 1) * scale / 2
        box = whole_draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
        x = (size[0] - (box[2] - box[0])) / 2 - box[0]
        y = center_y - (box[3] - box[1]) / 2 - box[1]
        whole_draw.text((x, y), text, font=font, fill=255,
                        stroke_width=stroke, stroke_fill=255)
        fill_draw.text((x, y), text, font=font, fill=255)

    fill = fill.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    whole = whole.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    fill_values = bytes(fill.getdata())
    whole_values = bytes(whole.getdata())
    indices = bytearray(WIDTH * HEIGHT)
    for i, (fill_alpha, whole_alpha) in enumerate(zip(fill_values, whole_values)):
        if fill_alpha >= 96:
            # The gray half of the native palette is intentionally reserved
            # for the glyph face.  Solid faces are index 15.
            indices[i] = 8 + round(7 * (fill_alpha - 96) / 159)
        elif whole_alpha:
            # Outline antialiasing uses the dark alpha ramp only.
            indices[i] = max(1, round(7 * whole_alpha / 255))
    return bytes(indices), fill, whole


def render_preview(indices, palette):
    rgba = bytearray(len(indices) * 4)
    for i, index in enumerate(indices):
        rgba[i * 4:i * 4 + 4] = bytes(palette[index])
    return Image.frombytes("RGBA", (WIDTH, HEIGHT), bytes(rgba))


def pack_indices(indices):
    packed = bytes(
        indices[i] | (indices[i + 1] << 4)
        for i in range(0, len(indices), 2)
    )
    return swizzle(packed, WIDTH // 2, HEIGHT)


def read_anmpack(iso_path):
    with iso_path.open("rb") as stream:
        stream.seek(ANMPACK_LBA * 2048)
        return stream.read(ANMPACK_SIZE)


def build(make_iso):
    pack = read_anmpack(BASE_ISO)
    entries = scriptpack.unpack(pack)
    entry = next(item for item in entries if item["name"] == MEMBER)
    if len(entry["data"]) != 396672:
        raise ValueError(f"unexpected {MEMBER} size: {len(entry['data'])}")
    resource = bytearray(
        entry["data"][RESOURCE_OFFSET:RESOURCE_OFFSET + RESOURCE_SIZE]
    )
    if struct.unpack_from("<I", resource)[0] != RESOURCE_SIZE:
        raise ValueError("opening resource size/header mismatch")
    if len(resource[PIXEL_OFFSET:]) != WIDTH * HEIGHT // 2:
        raise ValueError("opening atlas payload mismatch")

    rows, source_bounds = imagegen_layout(SOURCE_IMAGE)
    indices, fill_mask, whole_mask = render_clean_indices(rows)
    palette = rgba_palette(resource)
    preview = render_preview(indices, palette)
    pixel_data = pack_indices(indices)
    resource[PIXEL_OFFSET:] = pixel_data

    out_dir = ROOT / "build_jp"
    out_dir.mkdir(exist_ok=True)
    fill_mask.save(out_dir / "opening_text_kr_fill_mask.png")
    whole_mask.save(out_dir / "opening_text_kr_outline_mask.png")
    preview.save(out_dir / "opening_text_kr_preview.png")
    (out_dir / "opening_text_resource_kr.bin").write_bytes(resource)

    changed_member = bytearray(entry["data"])
    changed_member[RESOURCE_OFFSET:RESOURCE_OFFSET + RESOURCE_SIZE] = resource
    entry["data"] = bytes(changed_member)
    rebuilt = scriptpack.pack(entries)
    if len(rebuilt) != len(pack):
        raise ValueError(f"ANMPACK size changed: {len(pack)} -> {len(rebuilt)}")
    (out_dir / "ANMPACK_opening.dat").write_bytes(rebuilt)

    print("ImageGen text bounds", source_bounds)
    print("atlas", f"{WIDTH}x{HEIGHT}", "4bpp swizzled", len(pixel_data), "bytes")
    print("preview", out_dir / "opening_text_kr_preview.png")
    print("ANMPACK", len(rebuilt), "bytes (unchanged)")

    if make_iso:
        shutil.copyfile(BASE_ISO, OUTPUT_ISO)
        with OUTPUT_ISO.open("r+b") as stream:
            stream.seek(ANMPACK_LBA * 2048)
            stream.write(rebuilt)
        print("ISO", OUTPUT_ISO)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iso", action="store_true")
    args = parser.parse_args()
    build(args.iso)


if __name__ == "__main__":
    main()
