"""Tests for adw-gate.py `skip`, adw-init Phase 2's skip test. Run: cd scripts && python3 -m unittest -v test_adw_gate"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "adw-gate.py")

PROFILE = """# Repo profile

## §3 — Branches

| Role | Value |
|---|---|
| **default base** | `develop` |
| **production branch** | `main` |
"""

SURFACE = """Intent: fix the ward list
merge   auto → develop, after a clean walk

needs you  none
decided  Q1 cap refunds: yes · Q2 export: pick-lists only

cut     independent: u1 · u2
  u1  spec     the ward list loads
  u2  express  copy fix

⚠ spec criteria covered by no unit: none
⚠ shared-file hazard: u1 and u2 both touch src/list.ts
⚠ SwiftUI is compile only
"""

DECIDE = """Q1 | decided: yes — the code already caps them
Q2 | decided: pick-lists only — the export has no other consumer
"""


class Skip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.files = {"profile": PROFILE, "surface": SURFACE, "decide": DECIDE}

    def run_skip(self, questions="Q1 Q2", base="develop", **override):
        paths = {}
        for k, v in {**self.files, **override}.items():
            paths[k] = os.path.join(self.tmp, k)
            if v is None:
                if os.path.exists(paths[k]):
                    os.remove(paths[k])
            else:
                with open(paths[k], "w") as f:
                    f.write(v)
        p = subprocess.run([sys.executable, SCRIPT, "skip", "--profile", paths["profile"], "--surface", paths["surface"],
                            "--decide", paths["decide"], "--questions", questions, "--base", base],
                           capture_output=True, text=True)
        return p.returncode, p.stdout.strip()

    def assertWait(self, n, out_rc, starts=""):
        rc, out = out_rc
        self.assertEqual(rc, 1, out)
        self.assertTrue(out.startswith("wait %d %s" % (n, starts)), out)

    def test_all_four_hold_skips(self):
        self.assertEqual(self.run_skip(), (0, "skip"))

    def test_no_questions_skips(self):
        self.assertEqual(self.run_skip(questions="none", decide=""), (0, "skip"))
        self.assertEqual(self.run_skip(questions="", decide=""), (0, "skip"))

    def test_an_ask_line_waits(self):
        self.assertWait(1, self.run_skip(decide="Q1 | decided: yes\nQ2 | ask\n"), "Q2 is ask")

    def test_an_omitted_id_is_ask(self):
        self.assertWait(1, self.run_skip(decide="Q1 | decided: yes\n"), "no decided line for Q2")

    def test_an_unparseable_reply_is_ask(self):
        self.assertWait(1, self.run_skip(decide="I think both are fine.\n"), "no decided line for Q1, Q2")
        self.assertWait(1, self.run_skip(decide="Q1 | decided:\nQ2 | decided: x\n"), "no decided line for Q1")

    def test_an_id_both_ask_and_decided_is_ask(self):
        self.assertWait(1, self.run_skip(decide=DECIDE + "Q2 | ask\n"), "Q2 is ask")

    def test_marked_lines_parse(self):
        self.assertEqual(self.run_skip(decide="- `Q1 | decided: yes`\n**Q2** | decided: no\n"), (0, "skip"))

    def test_a_needs_you_count_waits(self):
        self.assertWait(1, self.run_skip(surface=SURFACE.replace("needs you  none", "needs you  1\n  Q3 — x? default: y")),
                        "the surface prints")

    def test_no_needs_you_line_waits(self):
        self.assertWait(1, self.run_skip(surface=SURFACE.replace("needs you  none\n", "")))

    def test_tier_line_blocks(self):
        s = SURFACE + "⚠ orchestrator on opus — 60–91% of run cost is this window; restart with claude --model sonnet\n"
        self.assertWait(2, self.run_skip(surface=s), "⚠ orchestrator on opus")

    def test_uncovered_criteria_block(self):
        s = SURFACE.replace("no unit: none", "no unit: AC 3 of u1")
        self.assertWait(2, self.run_skip(surface=s), "⚠ spec criteria covered by no unit: AC 3 of u1")

    def test_missing_coverage_line_blocks(self):
        s = SURFACE.replace("⚠ spec criteria covered by no unit: none\n", "")
        self.assertWait(2, self.run_skip(surface=s), "the surface has no")

    def test_no_gate_unit_blocks(self):
        self.assertWait(2, self.run_skip(surface=SURFACE + "⚠ no trustworthy gate sees u2\n"), "⚠ no trustworthy gate sees u2")

    def test_informational_warnings_do_not_block(self):
        s = SURFACE + "⚠ uncharted territory: no test touches the export\n"
        self.assertEqual(self.run_skip(surface=s), (0, "skip"))

    def test_a_base_line_waits(self):
        s = SURFACE.replace("merge   auto", "base    feature/x — the redesign branch\nmerge   auto")
        self.assertWait(3, self.run_skip(surface=s), "the surface prints")

    def test_a_base_other_than_the_default_waits(self):
        self.assertWait(3, self.run_skip(base="feature/x"), "the intent's base feature/x")

    def test_extend_mode_waits(self):
        s = SURFACE.replace("merge   auto → develop, after a clean walk",
                            "merge   auto → develop, after a clean walk\nextends ward-list · u1–u2: merged u1 · unbuilt u2")
        self.assertWait(4, self.run_skip(surface=s), "the surface prints")

    def test_lines_in_a_draft_spec_block_are_not_surface_lines(self):
        s = SURFACE + "```\n# u2 — copy fix\n⚠ no trustworthy gate sees u2\nbase: develop\n```\n"
        self.assertEqual(self.run_skip(surface=s), (0, "skip"))

    def test_first_failure_wins(self):
        s = SURFACE + "⚠ no trustworthy gate sees u2\n"
        self.assertWait(1, self.run_skip(surface=s, decide="Q1 | ask\n"))

    def test_errors_fail_closed(self):
        rc, out = self.run_skip(profile="## §3\n| **default base** | develop |\n")
        self.assertEqual((rc, out), (2, "wait 0 error: repo-profile §3 has no default base row with a branch in backticks"))
        rc, out = self.run_skip(surface=None)
        self.assertEqual(rc, 2)
        self.assertTrue(out.startswith("wait 0 error: cannot read"), out)
        rc, out = self.run_skip(surface="")
        self.assertEqual((rc, out), (2, "wait 0 error: the surface file is empty"))
        rc, out = self.run_skip(questions="1 2")
        self.assertEqual(rc, 2)
        p = subprocess.run([sys.executable, SCRIPT, "skip"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertTrue(p.stdout.startswith("wait 0 error:"), p.stdout)


if __name__ == "__main__":
    unittest.main()
