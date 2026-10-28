"""End-to-end tests for scripts/adw-analyze.py, and the leak test. Run: cd scripts && python3 -m unittest -v test_adw_analyze"""
import json
import os
import unittest

from adw_analyze.metrics import REGISTRY
from adw_analyze.testkit import (TmpCase, assistant, pr_node, tool_result, tool_use, user_prompt, write_session,
                                 write_subagent)

UNTIL = "2026-10-29"
HEADINGS = ["## Verdicts", "## Delete candidates", "## Metrics", "## Self-report trust", "## The loop",
            "## Legacy verdicts (information only)", "## Rejected predicts lines", "## NOT MEASURED", "## Critical pass"]
KEY = "-----BEGIN PRIVATE KEY-----MIIEvQIBADANBgkqhkiG9w0BAQEFAASC"
MARKER = "the owner said the staging password lives in the shared drive under ops"


class E2E(TmpCase):
    def setUp(self):
        super().setUp()
        self.projects = self.mkdir("projects")
        self.adw = self.git_repo("adw")
        os.makedirs(os.path.join(self.adw, "commands"))
        with open(os.path.join(self.adw, "commands", "adw-build.md"), "w") as f:
            f.write("contract\n")
        self.git("add", ".", cwd=self.adw)
        self.git("commit", "-q", "-m", "c", cwd=self.adw)
        self.merge = self.git("rev-parse", "HEAD", cwd=self.adw)
        self.reports = self.git_repo("reports", remote="git@github.com:o/adw-analysis.git")
        self.write_json(os.path.join(self.reports, "sources.json"), {"schema": 1, "repos": [
            {"name": "app", "slug": "o/app", "checkout": self.mkdir("app"), "transcripts": ["-app"],
             "gates": {"gate 4": "gradlew"}},
            {"name": "adw", "slug": "o/adw", "role": "contract", "checkout": self.adw}]})
        self.write_json(os.path.join(self.reports, "legacy-verdicts.json"),
                        [{"pr": 12, "for": "commands/adw-init.md handoff decide pass", "verdict": "failed", "note": "16 of 22 still stopped"}])
        recs = [user_prompt("2026-10-20T08:00:00Z", "/adw-build alpha " + MARKER, gitBranch="adw/alpha")]
        for i in range(25):
            recs.append(assistant(f"2026-10-20T08:{i:02d}:30Z", f"m{i}", text=MARKER,
                                  tools=[tool_use(f"t{i}", "Bash", command="cd .claude/worktrees/adw-alpha-u01 && ./gradlew test")]))
            recs.append(tool_result(f"2026-10-20T08:{i:02d}:40Z", f"t{i}", KEY + "\n" + MARKER))
        write_session(self.projects, "-app", "m1", recs)
        write_subagent(self.projects, "-app", "m1", "a1", [assistant("2026-10-20T09:00:00Z", "x1", text=MARKER)], "t0")
        write_session(self.projects, "-app", "m9", [assistant("2026-10-21T08:00:00Z", "y1", tools=[
            tool_use("u1", "Bash", command="python3 scripts/adw-analyze.py --reports r")])])
        self.gh.set(visibility={"o/adw-analysis": "PRIVATE"}, open={"o/app": []}, prs={
            "o/app": [pr_node(1, "[adw alpha u01] a", created="2026-10-20T10:00:00Z",
                              body="```\ncontract   abcdef1\ncycles     fix 0/3 progress-conditions none fired\n```")],
            "o/adw": [pr_node(9, "adw-build: x", created="2026-10-09T10:00:00Z", merge_oid=self.merge,
                              files=["commands/adw-build.md"],
                              body="predicts  outcome.fix_cycles_per_pr.v1 down 30% by 2026-11-20 for commands/adw-build.md\n"
                                   "predicts  cost.total_usd.v1 down 10% by 2026-11-20 for commands/adw-build.md")]})

    def run_reader(self, *extra, **env):
        return self.run_cli("--reports", self.reports, "--until", UNTIL, "--projects", self.projects, *extra, **env)

    def out(self, name):
        with open(os.path.join(self.reports, UNTIL, name)) as f:
            return f.read()

    def test_end_to_end(self):
        r = self.run_reader()
        self.assertEqual(r.returncode, 0, r.stderr)
        report = self.out("report.md")
        for h in HEADINGS:
            self.assertIn(h, report)
        self.assertIn("critical pass: pending", report)
        self.assertIn("#12", report)
        self.assertIn("metric not predictable", report)
        m = json.loads(self.out("metrics.json"))
        self.assertEqual(m["schema"], 1)
        self.assertEqual(set(m["metrics"]), set(REGISTRY))
        self.assertEqual(m["window"], ["2026-10-01T00:00:00Z", "2026-10-29T00:00:00Z"])
        [v] = m["verdicts"].values()
        self.assertEqual(v["verdict"], "too early")
        self.assertIn("leak scan: pending", self.out("issue.md"))
        halts = next(line for line in report.splitlines() if "owner.halts_per_merged_pr.v1" in line)
        self.assertNotIn("%", halts)

    def test_same_date_twice_exits_2(self):
        self.assertEqual(self.run_reader().returncode, 0)
        before = self.out("report.md")
        r = self.run_reader()
        self.assertEqual(r.returncode, 2)
        self.assertEqual(self.out("report.md"), before)

    def test_gh_failure_leaves_nothing(self):
        r = self.run_reader(FAKE_GH_FAIL="api")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(sorted(x for x in os.listdir(self.reports) if not x.startswith(".git")),
                         ["legacy-verdicts.json", "sources.json"])

    def test_missing_transcripts_exit_1(self):
        os.rename(os.path.join(self.projects, "-app"), os.path.join(self.projects, "-gone"))
        r = self.run_reader()
        self.assertEqual(r.returncode, 1)
        self.assertIn("app", r.stderr)

    def test_analyzer_sessions_excluded(self):
        self.run_reader()
        self.assertEqual(json.loads(self.out("metrics.json"))["excluded_sessions"], 1)

    def test_no_data_prints_no_data(self):
        self.run_reader()
        m = json.loads(self.out("metrics.json"))["metrics"]["evidence.review0_with_fixreview_rate.v1"]
        self.assertEqual((m["window"], m["status_window"]), (None, "no data"))
        row = next(line for line in self.out("report.md").splitlines() if "evidence.review0_with_fixreview_rate.v1" in line)
        self.assertIn("no data", row)


if __name__ == "__main__":
    unittest.main()
