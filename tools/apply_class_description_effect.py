"""Apply class-description effect patch to the single canonical test ISO."""
import hashlib
import json
from pathlib import Path
import struct

from build_jp import patch_eboot_aptitude_names
from patch_class_description_effect import patch as patch_outline
from patch_class_title_width import patch as patch_titles
from patch_ascii_space import patch as patch_spaces
from psp_prx_type1 import decrypt_prx, encrypt_prx


def patch(blob, verify_only=False):
    return patch_spaces(patch_titles(patch_outline(blob, verify_only), verify_only), verify_only)


def main():
    root = Path(__file__).resolve().parents[1]
    iso = root / 'build_jp/D2_JP_KR.iso'
    # Acquire write access before mutating any build artifact.
    with iso.open('r+b') as f:
        before = f.read()
        directory = before[24 * 2048:25 * 2048]
        rec = directory.find(b'EBOOT.BIN') - 33
        assert rec >= 0
        start = struct.unpack_from('<I', directory, rec + 2)[0] * 2048
        size = struct.unpack_from('<I', directory, rec + 10)[0]
        assert start == 32 * 2048
        original = before[start:start + size]
        elf = decrypt_prx(original)
        patched = patch(elf)
        encrypted = encrypt_prx(patched, original)
        assert len(encrypted) == size and decrypt_prx(encrypted) == patched
        patch(patched, verify_only=True)
        build_path = root / 'build_jp/EBOOT_KR.BIN'
        normalized, _, _ = patch_eboot_aptitude_names(build_path.read_bytes())
        assert patch(normalized)[:len(patched)] == patched
        backup = root / 'work/glyph_overlap'
        backup.mkdir(exist_ok=True)
        for name, blob in [('EBOOT_before_effect.enc', original),
                           ('EBOOT_before_effect.elf', elf),
                           ('EBOOT_build_before_effect.BIN', build_path.read_bytes())]:
            target = backup / name
            if not target.exists():
                target.write_bytes(blob)
        f.seek(start)
        f.write(encrypted)
        f.flush()
        f.seek(0)
        after = f.read()
        assert before[:start] == after[:start]
        assert before[start + size:] == after[start + size:]
        assert decrypt_prx(after[start:start + size]) == patched
    build_path.write_bytes(patch(normalized))
    (root / 'build_jp/EBOOT_KR_enc.BIN').write_bytes(encrypted)
    result = dict(iso_sha256=hashlib.sha256(after).hexdigest(), outline_calls=12,
                  horizontal_outline_px=1,
                  title_horizontal_scale=1.0, title_vertical_scale=1.0,
                  ascii_space_px=7,
                  main_calls_preserved=3, encryption_roundtrip='exact',
                  outside_eboot='unchanged', visual_verification='pending user')
    (backup / 'patch_result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
