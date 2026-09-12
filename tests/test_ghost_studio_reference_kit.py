from __future__ import annotations

import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("ghost_studio_reference_kit", ROOT / "tools" / "ghost_studio_reference_kit.py")
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def png(width: int, height: int) -> bytes:
    def chunk(name: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + name + payload + struct.pack(">I", zlib.crc32(name + payload) & 0xFFFFFFFF)
    rows = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


class GhostStudioReferenceKitTests(unittest.TestCase):
    def test_contract_binds_nine_canonical_assets_and_scale(self):
        contract = MODULE.reference_contract()
        self.assertEqual(tuple(contract["canonical_assets"]), MODULE.CANONICAL_ASSETS)
        self.assertEqual(contract["scale"]["relay_height_m"], 3.0)
        self.assertEqual(contract["scale"]["floor_panel_m"], [1.0, 1.0])
        self.assertEqual(contract["scale"]["wall_panel_m"], [2.0, 2.0])
        self.assertTrue(contract["delivery"]["simple_collision"])

    def test_reference_requires_real_large_png_or_jpeg(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            valid = root / "reference.png"
            valid.write_bytes(png(1536, 1024))
            state = MODULE.validate_reference(valid)
            self.assertEqual(state["dimensions_px"], [1536, 1024])
            self.assertEqual(state["image_format"], "PNG")
            small = root / "small.png"
            small.write_bytes(png(100, 100))
            with self.assertRaisesRegex(MODULE.TrialError, "too small"):
                MODULE.validate_reference(small)
            bad = root / "bad.png"
            bad.write_bytes(b"not a png")
            with self.assertRaisesRegex(MODULE.TrialError, "PNG or JPEG"):
                MODULE.validate_reference(bad)

    def test_material_states_include_both_relay_signals(self):
        self.assertGreater(MODULE.MATERIALS["teal_glow"]["emissive"][1], 0.9)
        self.assertGreater(MODULE.MATERIALS["red_glow"]["emissive"][0], 0.9)
        self.assertGreater(MODULE.MATERIALS["dark_metal"]["metallic"], 0.8)

    def test_jpeg_metadata_is_dependency_free(self):
        jpeg = (
            b"\xff\xd8\xff\xc0\x00\x11\x08"
            + struct.pack(">HH", 1024, 1536)
            + b"\x03\x01\x11\x00\x02\x11\x00\x03\x11\x00\xff\xd9"
        )
        self.assertEqual(MODULE._image_metadata(jpeg), ("JPEG", 1536, 1024))


if __name__ == "__main__":
    unittest.main()
