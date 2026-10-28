"""Tests for adw_analyze.predicts. Run: cd scripts && python3 -m unittest -v test_adw_analyze_predicts"""
import unittest

from adw_analyze.github import PR
from adw_analyze.predicts import NoPrediction, Prediction, Rejected, read_predictions

MERGED = "2026-10-09T11:00:00Z"
EXISTS = {"commands/adw-build.md", "scripts/adw-run-clean.py"}


def contract_pr(body, merged=MERGED, number=12):
    return PR(repo="adw", number=number, title="x", slug=None, unit=None, adw=False, state="MERGED" if merged else "OPEN",
              created="2026-10-09T10:00:00Z", merged=merged, closed=merged, last_edited=None, base="main", head="h",
              merge_sha="m" * 40 if merged else None, body=body, files=["commands/adw-build.md"])


def read(body, **kw):
    return read_predictions(contract_pr(body, **kw), lambda sha, path: path in EXISTS)


class Parse(unittest.TestCase):
    def test_relative(self):
        [p] = read("Body.\n\npredicts  friction.denials_per_1k_calls.v1 down 30% by 2026-11-20 for commands/adw-build.md §3.4\n")
        self.assertIsInstance(p, Prediction)
        self.assertEqual((p.metric, p.direction, p.amount, p.unit), ("friction.denials_per_1k_calls.v1", "down", 30.0, "pct"))
        self.assertEqual((p.by, p.for_path, p.section, p.repo), ("2026-11-20", "commands/adw-build.md", "3.4", None))
        self.assertEqual((p.pr, p.merged, p.merge_sha, p.kind), (12, MERGED, "m" * 40, "prediction"))
        self.assertTrue(p.key.startswith("12:"))

    def test_absolute_and_zero_and_repo(self):
        a, z = read("predicts  outcome.fix_cycles_per_pr.v1 down 0.5 by 2026-11-20 for scripts/adw-run-clean.py repo AXCMedApp\n"
                    "  predicts  outcome.ever_blocked_rate.v1 down to-zero by 2026-11-20 for commands/adw-build.md §3.7\n")
        self.assertEqual((a.amount, a.unit, a.repo, a.section), (0.5, "abs", "AXCMedApp", None))
        self.assertEqual((z.amount, z.unit, z.section), (0.0, "zero", "3.7"))

    def test_none_line(self):
        [n] = read("predicts  none — this PR builds the measurement; nothing to predict yet")
        self.assertIsInstance(n, NoPrediction)
        self.assertEqual((n.reason, n.kind), ("this PR builds the measurement; nothing to predict yet", "none"))

    def test_each_rejection(self):
        cases = {
            "predicts  no.such.metric.v1 down 10% by 2026-11-01 for commands/adw-build.md": "unknown metric",
            "predicts  cost.total_usd.v1 down 10% by 2026-11-01 for commands/adw-build.md": "metric not predictable",
            "predicts  cost.usd_per_merged_pr.v1 sideways by 2026-11-01": "bad grammar",
            "predicts  cost.usd_per_merged_pr.v1 down 10% by 2026-11-01 for commands/gone.md": "path not at merge commit",
            "predicts  cost.usd_per_merged_pr.v1 down 10% by 2026-11-28 for commands/adw-build.md": "deadline over 49 days",
            "predicts  cost.usd_per_merged_pr.v1 down 10% by 2026-10-01 for commands/adw-build.md": "deadline before merge",
        }
        for line, reason in cases.items():
            [r] = read(line)
            self.assertIsInstance(r, Rejected, line)
            self.assertEqual((r.reason, r.kind, r.line), (reason, "rejected", line), line)

    def test_49_days_is_allowed(self):
        [p] = read("predicts  cost.usd_per_merged_pr.v1 down 10% by 2026-11-27 for commands/adw-build.md")
        self.assertIsInstance(p, Prediction)

    def test_two_lines_two_predictions(self):
        a, b = read("predicts  cost.usd_per_merged_pr.v1 down 10% by 2026-11-20 for commands/adw-build.md §3.4\n"
                    "predicts  cost.usd_per_merged_pr.v1 down 10% by 2026-11-20 for commands/adw-build.md §3.6\n")
        self.assertNotEqual(a.key, b.key)

    def test_prose_and_unmerged_are_ignored(self):
        self.assertEqual(read("This predicts nothing.\nThe word predicts appears here."), [])
        self.assertEqual(read("predicts  none — x", merged=None), [])


if __name__ == "__main__":
    unittest.main()
