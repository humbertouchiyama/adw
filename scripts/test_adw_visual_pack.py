"""Tests for adw-visual-pack.py (the design sign-off pack of adw-build §3.2a)."""
from __future__ import annotations

import importlib.util
import io
import json
import os
import struct
import tempfile
import unittest
import zlib
from contextlib import redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("adw_visual_pack", os.path.join(HERE, "adw-visual-pack.py"))
pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)


def png(path: str, w: int = 4, h: int = 6) -> str:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + b"\x80\x40\x20" * w for _ in range(h))
    data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


class Pack(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.base = png(os.path.join(self.d, "base", "Main.png"))
        self.head = png(os.path.join(self.d, "head", "Main.png"))
        self.design = png(os.path.join(self.d, "design", "Main.png"), 4, 8)
        self.hud_base = png(os.path.join(self.d, "base", "Hud.png"))
        self.hud_head = png(os.path.join(self.d, "head", "Hud.png"))
        self.out = os.path.join(self.d, "pack")

    def tearDown(self):
        self.tmp.cleanup()

    def manifest(self, **over) -> dict:
        m = {"slug": "idl-62-shops", "title": "Shops", "contract": "abc1234", "round": 1, "note": "",
             "prs": ["#105 final PR · ready"],
             "units": [{"unit": "u4", "title": "Merchant <views>", "summary": "Gold title bar & tabs.",
                        "checks": ["gates      tsc 0", "visual     rows 3 · rounds 5"],
                        "rows": [
                            {"id": "V1", "state": "Shops/Main", "crop": "0,0,4,2", "design_crop": "", "rmse": "0.1735",
                             "limit": "baseline", "result": "unscored", "graded": "#105 v2",
                             "before": self.base, "after": self.head, "goal": self.design},
                            {"id": "V2", "state": "Shops/Main", "crop": "0,2,4,2", "design_crop": "0,3,4,2",
                             "rmse": "0.0100", "limit": "0.0500", "result": "pass", "graded": "#105 v2",
                             "before": self.base, "after": self.head, "goal": self.design},
                            {"id": "G1", "state": "Hud/Main", "crop": "0,4,4,2", "rmse": "0.0000", "limit": "baseline",
                             "result": "unscored", "graded": "#100 v2",
                             "before": self.hud_base, "after": self.hud_head, "goal": ""}]}]}
        m.update(over)
        return m

    def run_pack(self, m) -> tuple[int, str]:
        mf = os.path.join(self.d, "manifest.json")
        with open(mf, "w", encoding="utf-8") as f:
            f.write(m if isinstance(m, str) else json.dumps(m))
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = pack.main(["--pack", self.out, "--manifest", mf])
        return code, buf.getvalue().strip()

    def page(self) -> str:
        with open(os.path.join(self.out, "index.html"), encoding="utf-8") as f:
            return f.read()

    def test_builds_page_and_copies_each_image_once(self):
        code, line = self.run_pack(self.manifest())
        self.assertEqual(code, 0, line)
        self.assertRegex(line, r"^pack .*/index\.html · 1 units · 3 rows · 5 images · 0 missing$")
        copied = [os.path.join(r, f) for r, _, fs in os.walk(os.path.join(self.out, "img")) for f in fs]
        self.assertEqual(len(copied), 5)
        page = self.page()
        for want in ("before", "after", "goal", "V1", "V2", "G1", "Shops/Main", "Hud/Main", "0.1735", "#105 v2",
                     "Sign-off: one answer for the whole run", "docs(spec): visual limits"):
            self.assertIn(want, page)

    def test_writes_a_self_ignoring_gitignore(self):
        self.run_pack(self.manifest())
        with open(os.path.join(self.out, ".gitignore"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "*\n")

    def test_design_crop_is_used_for_the_goal_zoom(self):
        self.run_pack(self.manifest())
        self.assertIn('data-crop="0,3,4,2"', self.page())
        self.assertIn('data-crop="0,2,4,2"', self.page())

    def test_guard_row_has_no_goal_image(self):
        self.run_pack(self.manifest())
        page = self.page()
        self.assertIn("guard rows only", page)
        self.assertIn("= before", page)

    def test_missing_image_is_shown_and_counted(self):
        m = self.manifest()
        m["units"][0]["rows"][0]["before"] = ""
        m["units"][0]["rows"][1]["before"] = ""
        m["units"][0]["rows"][2]["after"] = os.path.join(self.d, "gone.png")
        code, line = self.run_pack(m)
        self.assertEqual(code, 0, line)
        self.assertIn("· 3 missing", line)
        self.assertIn("no image", self.page())

    def test_text_is_escaped(self):
        self.run_pack(self.manifest(note="u4: <b>too low</b>"))
        page = self.page()
        self.assertIn("Merchant &lt;views&gt;", page)
        self.assertIn("Gold title bar &amp; tabs.", page)
        self.assertIn("u4: &lt;b&gt;too low&lt;/b&gt;", page)
        self.assertIn("Your last note", page)

    def test_bad_crop_fails_and_writes_nothing(self):
        m = self.manifest()
        m["units"][0]["rows"][0]["crop"] = "0,0,4"
        code, line = self.run_pack(m)
        self.assertEqual(code, 1)
        self.assertTrue(line.startswith("pack failed — u4 V1: crop"), line)
        self.assertFalse(os.path.exists(os.path.join(self.out, "index.html")))

    def test_bad_row_id_fails(self):
        m = self.manifest()
        m["units"][0]["rows"][0]["id"] = "u4 V1"
        code, line = self.run_pack(m)
        self.assertEqual(code, 1)
        self.assertIn("is not V<n> or G<n>", line)

    def test_missing_summary_fails(self):
        m = self.manifest()
        m["units"][0]["summary"] = " "
        code, line = self.run_pack(m)
        self.assertEqual(code, 1)
        self.assertIn("summary is missing", line)

    def test_unreadable_manifest_fails(self):
        code, line = self.run_pack("{not json")
        self.assertEqual(code, 1)
        self.assertTrue(line.startswith("pack failed — manifest"), line)

    def test_rebuild_replaces_the_page(self):
        self.run_pack(self.manifest())
        code, _ = self.run_pack(self.manifest(round=2, note="u4: move the bar"))
        self.assertEqual(code, 0)
        self.assertIn("pack 2", self.page())
        self.assertIn("move the bar", self.page())


if __name__ == "__main__":
    unittest.main()
