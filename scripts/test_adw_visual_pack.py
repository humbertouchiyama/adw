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
        for want in ("Before", "After", "Design", "Shops · Main", "Hud · Main", "0.1735", "#105 v2", "Your answer"):
            self.assertIn(want, page)
        for gone in ("docs(spec): visual limits", "RMSE", "fork point", "verified head"):
            self.assertNotIn(gone, page)
        self.assertNotIn(self.base, page)  # no absolute path in the page

    def test_writes_a_self_ignoring_gitignore(self):
        self.run_pack(self.manifest())
        with open(os.path.join(self.out, ".gitignore"), encoding="utf-8") as f:
            self.assertEqual(f.read(), "*\n")

    def test_design_crop_is_used_for_the_goal_zoom(self):
        self.run_pack(self.manifest())
        self.assertIn('data-crop="0,3,4,2"', self.page())
        self.assertIn('data-crop="0,2,4,2"', self.page())

    def test_guard_row_has_no_goal_image(self):
        m = self.manifest()
        m["units"][0]["rows"][2]["rmse"] = "0.0040"
        self.run_pack(m)
        page = self.page()
        self.assertIn("it must look the same as Before", page)
        self.assertIn("Not measured: it should look the same as before", page)
        hud = self.card(page, "s2")
        self.assertNotIn('data-k="goal"', hud)

    def card(self, page: str, sid: str) -> str:
        return page.split('<article class="screen" id="%s"' % sid)[1].split("</article>")[0]

    def test_changed_areas_come_first(self):
        m = self.manifest()
        m["units"][0]["rows"][2]["rmse"] = "0.0040"
        self.run_pack(m)
        page = self.page()
        shops, hud = self.card(page, "s1"), self.card(page, "s2")
        top = shops.split('<details class="full">')[0]
        self.assertEqual(top.count('class="area"'), 2)  # V1 and V2, above the full screens
        v1 = top.split('<i class="tag v">V1</i>')[1].split('class="area"')[0]
        self.assertLess(v1.index("<figcaption>After"), v1.index("<figcaption>Design"))
        self.assertIn('data-crop="0,0,4,2"', v1)
        g1 = hud.split('<details class="full">')[0].split('<i class="tag g">G1</i>')[1]
        self.assertLess(g1.index("<figcaption>Before"), g1.index("<figcaption>After"))
        self.assertNotIn("<figcaption>Design", g1)
        full = shops.split('<details class="full">')[1].split("</details>")[0]
        for k in ("before", "after", "goal"):
            self.assertIn('data-k="%s"' % k, full)

    def test_full_screens_box_every_area_by_kind(self):
        m = self.manifest()
        m["units"][0]["rows"][2]["rmse"] = "0.0040"
        self.run_pack(m)
        page = self.page()
        full = self.card(page, "s1").split('<details class="full">')[1]
        before = full.split('data-k="before"')[1].split("</figure>")[0]
        self.assertIn('<span class="box v" data-box="0,0,4,2" hidden>', before)
        self.assertIn('<span class="box v" data-box="0,2,4,2" hidden>', before)
        goal = full.split('data-k="goal"')[1].split("</figure>")[0]
        self.assertIn('data-box="0,3,4,2"', goal)  # the design crop, on the design
        self.assertNotIn('data-box="0,2,4,2"', goal)
        hud = self.card(page, "s2").split('<details class="full">')[1]
        self.assertIn('<span class="box g" data-box="0,4,4,2" hidden><span class="ids"><i class="tag g">G1</i>', hud)
        self.assertIn("b.style.left=(c[0]/W*100)+'%'", page)  # percent of the natural size

    def test_one_box_for_rows_that_share_an_area(self):
        m = self.manifest()
        m["units"][0]["rows"][1]["crop"] = "0,0,4,2"
        self.run_pack(m)
        before = self.card(self.page(), "s1").split('data-k="before"')[1].split("</figure>")[0]
        self.assertEqual(before.count('class="box'), 1)
        self.assertIn('<i class="tag v">V1</i><i class="tag v">V2</i>', before)

    def test_check_line_from_rows_else_summary(self):
        self.run_pack(self.manifest())
        self.assertIn('<p class="look"><b>Check:</b> Gold title bar &amp; tabs.</p>', self.card(self.page(), "s1"))
        m = self.manifest()
        m["units"][0]["rows"][0]["check"] = "The title reads MERCADOR"
        self.run_pack(m)
        self.assertIn('<b>Check:</b> The title reads MERCADOR</p>', self.card(self.page(), "s1"))
        m["units"][0]["rows"][1]["check"] = "The tabs sit under the title"
        self.run_pack(m)
        self.assertIn("<b>Check:</b> V1: The title reads MERCADOR · V2: The tabs sit under the title</p>", self.page())

    def test_check_must_be_a_string(self):
        m = self.manifest()
        m["units"][0]["rows"][0]["check"] = ["no"]
        code, line = self.run_pack(m)
        self.assertEqual(code, 1)
        self.assertIn("V1: check is not a string", line)

    def test_unchanged_guard_screens_fold_into_one_line(self):
        self.run_pack(self.manifest())  # G1 measured 0.0000
        page = self.page()
        unit = page.split('<section class="unit"')[1].split("</section>")[0]
        self.assertNotIn('id="s2"', unit)
        same = page.split('<section class="same" id="same">')[1].split("</section>")[0]
        self.assertIn("<b>1 screen unchanged</b>", same)
        self.assertIn('<details class="one"><summary>u4 · Hud · Main</summary><article class="screen" id="s2"', same)
        self.assertIn("Unchanged: the same as before", same)
        self.assertIn('<a href="#same">1 screen unchanged</a>', page.split('<section class="unit"')[0])
        self.assertIn('name="s2" value="wrong"', same)  # its card still feeds the one answer

    def test_guard_screen_with_any_difference_stays_in_full(self):
        for rmse, result in (("0.0061", "unscored"), ("", "no image"), ("0", "fail")):
            m = self.manifest()
            m["units"][0]["rows"][2].update(rmse=rmse, result=result)
            self.run_pack(m)
            page = self.page()
            self.assertNotIn('id="same"', page, rmse)
            self.assertIn('id="s2"', page.split('<section class="unit"')[1].split("</section>")[0])

    def test_unit_with_only_unchanged_screens_points_to_the_fold(self):
        m = self.manifest()
        m["units"].append({"unit": "u5", "title": "Hud only", "summary": "Nothing moves.",
                           "rows": [dict(m["units"][0]["rows"][2])]})
        self.run_pack(m)
        page = self.page()
        u5 = page.split('<section class="unit" id="u5">')[1].split("</section>")[0]
        self.assertIn("Every screen of this unit is unchanged", u5)
        self.assertIn("<b>2 screens unchanged</b>", page)

    def test_missing_image_is_shown_and_counted(self):
        m = self.manifest()
        m["units"][0]["rows"][0]["before"] = ""
        m["units"][0]["rows"][1]["before"] = ""
        m["units"][0]["rows"][2]["after"] = os.path.join(self.d, "gone.png")
        code, line = self.run_pack(m)
        self.assertEqual(code, 0, line)
        self.assertIn("· 3 missing", line)
        self.assertIn("No image to show", self.page())

    def test_none_says_why_and_is_not_missing(self):
        m = self.manifest()
        for r in m["units"][0]["rows"][:2]:
            r["before"] = "none"
        m["units"][0]["rows"][2]["after"] = "None"
        code, line = self.run_pack(m)
        self.assertEqual(code, 0, line)
        self.assertIn("· 0 missing", line)
        page = self.page()
        self.assertIn("New screen: there was nothing here before", page)
        self.assertIn("Not shown after the change", page)
        self.assertNotIn("No image to show", page)

    def test_a_real_image_wins_over_none_in_one_state(self):
        m = self.manifest()
        m["units"][0]["rows"][0]["before"] = "none"
        code, line = self.run_pack(m)
        self.assertEqual(code, 0, line)
        before = self.page().split('<figcaption><b>Before</b>')[1].split("</figure>")[0]
        self.assertIn('data-k="before"', before)

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

    def test_plain_verdicts_and_banner(self):
        m = self.manifest()
        m["units"][0]["rows"][1]["result"] = "fail"
        self.run_pack(m)
        page = self.page()
        self.assertIn("Differs from the design", page)
        self.assertIn("1 of 2 screens differ from the design", page)
        self.assertIn('href="#s1"', page)
        m["units"][0]["rows"][1]["result"] = "pass"
        self.run_pack(m)
        self.assertIn("could not be measured", self.page())

    def test_screens_map_names_a_screen(self):
        self.run_pack(self.manifest(screens={"Shops/Main": "Merchant, Buy tab"}))
        page = self.page()
        self.assertIn("Merchant, Buy tab", page)
        self.assertIn('data-unit="u4" data-title="Merchant, Buy tab"', page)

    def test_diff_buttons_only_when_both_images_exist(self):
        m = self.manifest()
        self.run_pack(m)
        self.assertIn("Before vs After", self.page())
        self.assertIn("After vs Design", self.page())
        for r in m["units"][0]["rows"]:
            r["before"] = "none"
        self.run_pack(m)
        self.assertNotIn("Before vs After", self.page())

    def test_numbers_are_folded_away(self):
        self.run_pack(self.manifest())
        self.assertIn("<details><summary>Numbers</summary><div class=\"scroll\"><table>", self.page())

    def test_rebuild_replaces_the_page(self):
        self.run_pack(self.manifest())
        code, _ = self.run_pack(self.manifest(round=2, note="u4: move the bar"))
        self.assertEqual(code, 0)
        self.assertIn("pack 2", self.page())
        self.assertIn("move the bar", self.page())


if __name__ == "__main__":
    unittest.main()
