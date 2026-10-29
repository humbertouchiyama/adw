"""Tests for adw_analyze.verdicts. Run: cd scripts && python3 -m unittest -v test_adw_analyze_verdicts"""
import json
import os

from adw_analyze import facts as F
from adw_analyze import verdicts as V
from adw_analyze.config import Repo
from adw_analyze.predicts import Prediction
from adw_analyze.testkit import TmpCase, make_pr

APP = Repo(name="app", slug="o/app", base="develop")
ADW = Repo(name="adw", slug="o/adw", role="contract", base="main")
MERGE = "2026-10-10T00:00:00Z"
BY = "2026-10-31"
NEVER = lambda repo, start, end: None  # noqa: E731


def day(d, h=12):
    return f"2026-{d}T{h:02d}:00:00Z"


class Base(TmpCase):
    def setUp(self):
        super().setUp()
        self.adw = self.git_repo("a b/adw")
        self.sha = {}
        for name in ("A", "B", "C"):
            with open(os.path.join(self.adw, name), "w") as f:
                f.write(name)
            self.git("add", name, cwd=self.adw)
            self.git("commit", "-q", "-m", name, cwd=self.adw)
            self.sha[name] = self.git("rev-parse", "HEAD", cwd=self.adw)
        self.is_after = V.git_is_after(self.adw)
        self.n = 0

    def prs(self, count, sha, fix, start_day, merged_day=None):
        out = []
        for i in range(count):
            self.n += 1
            created = day(start_day)
            out.append(make_pr(self.n, f"[adw s{self.n} u01] x", created, merged=day(merged_day or start_day, 13),
                               block=f"contract   {sha}", commits=[f"fix-attempt-{fix}: y"] if fix else []))
        return out

    def prediction(self, direction="down", amount=30.0, unit="pct", by=BY, key="12:aaaa", metric="outcome.fix_cycles_per_pr.v1",
                   merged=MERGE, repo=None):
        return Prediction(pr=12, key=key, line="predicts  …", metric=metric, direction=direction, amount=amount, unit=unit,
                          by=by, for_path="commands/adw-build.md", section=None, repo=repo, merged=merged,
                          merge_sha=self.sha["B"])

    def sample(self, before_fix=10, after_fix=6):
        return self.prs(20, self.sha["A"], before_fix, "10-01") + self.prs(20, self.sha["C"], after_fix, "10-20")

    def facts(self, prs, until="2026-11-01T00:00:00Z", since=None):
        return F.assemble([APP, ADW], {"app": []}, prs, [], until=until, since=since)

    def judge(self, p, prs, others=(), watch=NEVER, until="2026-11-01T00:00:00Z"):
        return V.judge(p, self.facts(prs, until), [p, *others], self.is_after, watch)


class Split(Base):
    def test_is_after_and_path_with_space(self):
        self.assertTrue(self.is_after(self.sha["B"], self.sha["C"]))
        self.assertFalse(self.is_after(self.sha["B"], self.sha["A"]))
        self.assertIsNone(self.is_after(self.sha["B"], "deadbee"))
        exists = V.git_path_exists(self.adw)
        self.assertTrue(exists(self.sha["B"], "A"))
        self.assertFalse(exists(self.sha["A"], "C"))

    def test_run_started_before_merge_counts_before(self):
        base = self.prs(19, self.sha["A"], 10, "10-01") + self.prs(1, self.sha["A"], 10, "10-01", merged_day="10-15")
        after = self.prs(20, self.sha["C"], 6, "10-20")
        v = self.judge(self.prediction(), base + after)
        self.assertEqual((v.baseline.n, v.after.n), (20, 20))

    def test_unknown_sha_excluded(self):
        prs = self.prs(20, self.sha["A"], 10, "10-01") + self.prs(20, self.sha["C"], 6, "10-20") + self.prs(3, "deadbee", 1, "10-20")
        v = self.judge(self.prediction(), prs)
        self.assertEqual((v.baseline.n, v.after.n), (20, 20))
        self.assertIn("deadbee", v.unknown_shas)


class Judge(Base):
    def test_worked_and_failed_by_pct(self):
        self.assertEqual(self.judge(self.prediction(amount=30.0), self.sample()).verdict, "worked")
        self.assertEqual(self.judge(self.prediction(amount=50.0), self.sample()).verdict, "failed")

    def test_absolute_and_zero(self):
        self.assertEqual(self.judge(self.prediction(amount=4.0, unit="abs"), self.sample()).verdict, "worked")
        self.assertEqual(self.judge(self.prediction(amount=0.0, unit="zero"), self.sample()).verdict, "failed")
        self.assertEqual(self.judge(self.prediction(amount=0.0, unit="zero"), self.sample(after_fix=0)).verdict, "worked")

    def test_already_low_baseline_cannot_pass(self):
        prs = self.prs(10, self.sha["A"], 1, "10-01") + self.prs(10, self.sha["A"], 0, "10-01")
        prs += self.prs(10, self.sha["C"], 1, "10-20") + self.prs(10, self.sha["C"], 0, "10-20")
        v = self.judge(self.prediction(amount=10.0), prs)
        self.assertEqual((v.baseline.value, v.after.value, v.verdict), (0.5, 0.5, "failed"))

    def test_too_early_shows_the_running_value(self):
        v = self.judge(self.prediction(), self.sample(), until="2026-10-25T00:00:00Z")
        self.assertEqual(v.verdict, "too early")
        self.assertEqual(v.after.value, 6.0)

    def test_deadline_today_is_judged(self):
        self.assertEqual(self.judge(self.prediction(), self.sample(), until="2026-10-31T00:00:00Z").verdict, "worked")

    def test_one_below_minimum_is_no_data(self):
        prs = self.prs(19, self.sha["A"], 10, "10-01") + self.prs(20, self.sha["C"], 6, "10-20")
        self.assertEqual(self.judge(self.prediction(), prs).verdict, "no data")

    def test_confounded_by_overlap(self):
        other = self.prediction(key="13:bbbb", merged="2026-10-20T00:00:00Z", by="2026-11-05")
        v = self.judge(self.prediction(), self.sample(), others=[other])
        self.assertEqual(v.verdict, "confounded")
        self.assertEqual(v.cause, "overlaps #12")
        other_metric = self.prediction(key="13:cccc", metric="outcome.ever_blocked_rate.v1")
        self.assertEqual(self.judge(self.prediction(), self.sample(), others=[other_metric]).verdict, "worked")

    def test_confounded_by_watch_path(self):
        v = self.judge(self.prediction(), self.sample(), watch=lambda repo, start, end: "watch path changed in app")
        self.assertEqual((v.verdict, v.cause), ("confounded", "watch path changed in app"))

    def test_met_exactly_is_worked(self):
        prs = self.prs(5, self.sha["A"], 1, "10-01") + self.prs(15, self.sha["A"], 0, "10-01")
        prs += self.prs(4, self.sha["C"], 1, "10-20") + self.prs(16, self.sha["C"], 0, "10-20")
        self.assertEqual(self.judge(self.prediction(amount=20.0), prs).verdict, "worked")      # 0.25 -> 0.20 is -20%
        self.assertEqual(self.judge(self.prediction(amount=0.05, unit="abs"), prs).verdict, "worked")

    def test_baseline_before_the_data_is_no_data(self):
        p = self.prediction()
        facts = self.facts(self.sample(), since="2026-09-25T00:00:00Z")   # baseline starts 09-19
        v = V.judge(p, facts, [p], self.is_after, NEVER)
        self.assertEqual((v.verdict, v.cause), ("no data", "baseline starts before the data read"))

    def test_baseline_start(self):
        self.assertEqual(V.baseline_start(self.prediction()), "2026-09-19T00:00:00Z")


class Records(Base):
    def test_record_vs_restated(self):
        reports = self.mkdir("reports")
        self.write_json(os.path.join(reports, "2026-10-26", "metrics.json"), {"verdicts": {"12:aaaa": {"verdict": "too early", "of_record": False}}})
        self.write_json(os.path.join(reports, "2026-11-02", "metrics.json"), {"verdicts": {"12:aaaa": {"verdict": "failed", "of_record": True}}})
        self.write_json(os.path.join(reports, "2026-11-09", "metrics.json"), {"verdicts": {"12:aaaa": {"verdict": "worked", "of_record": False}}})
        os.makedirs(os.path.join(reports, "notes"))
        recs = V.read_records(reports)
        self.assertEqual(recs["12:aaaa"]["verdict"], "failed")
        self.assertEqual(recs["12:aaaa"]["date"], "2026-11-02")
        self.assertEqual(V.record_entry(self.judge(self.prediction(), self.sample()), recs)["restated"], "worked")
        fresh = V.record_entry(self.judge(self.prediction(key="14:dddd"), self.sample()), recs)
        self.assertEqual((fresh["of_record"], fresh["record"], fresh["restated"]), (True, None, None))
        early = V.record_entry(self.judge(self.prediction(key="15:eeee"), self.sample(), until="2026-10-25T00:00:00Z"), recs)
        self.assertFalse(early["of_record"])

    def test_records_only_from_committed_files(self):
        reports = self.git_repo("reports")
        self.write_json(os.path.join(reports, "2026-11-02", "metrics.json"), {"verdicts": {"12:aaaa": {"verdict": "failed", "of_record": True}}})
        self.assertEqual(V.read_records(reports), {})
        self.git("add", ".", cwd=reports)
        self.git("commit", "-q", "-m", "r", cwd=reports)
        self.assertEqual(V.read_records(reports)["12:aaaa"]["verdict"], "failed")

    def test_record_keeps_what_the_line_said(self):
        reports = self.mkdir("reports")
        entry = {"verdict": "failed", "of_record": True, "pr": 12, "metric": "m.v1", "for_path": "commands/x.md",
                 "section": "3.4", "line": "predicts  m.v1 down 10% by 2026-11-01 for commands/x.md §3.4"}
        self.write_json(os.path.join(reports, "2026-11-02", "metrics.json"), {"verdicts": {"12:aaaa": entry}})
        rec = V.read_records(reports)["12:aaaa"]
        self.assertEqual((rec["pr"], rec["metric"], rec["for_path"], rec["section"], rec["date"]),
                         (12, "m.v1", "commands/x.md", "3.4", "2026-11-02"))


class Watch(Base):
    def test_git_watch_changed(self):
        app = self.git_repo("app checkout")
        origin = self.git_repo("origin")
        self.git("remote", "add", "origin", origin, cwd=app)
        for name, date in (("README", "2026-10-01T10:00:00Z"), ("repo-profile.md", "2026-10-15T10:00:00Z")):
            with open(os.path.join(app, name), "w") as f:
                f.write(name)
            self.git("add", name, cwd=app)
            env = {**os.environ, "GIT_COMMITTER_DATE": date, "GIT_AUTHOR_DATE": date}
            import subprocess
            subprocess.run(["git", "commit", "-q", "-m", name], cwd=app, env=env, check=True)
        self.git("push", "-q", "origin", "main:develop", cwd=app)
        self.git("fetch", "-q", "origin", cwd=app)
        repo = Repo(name="app", slug="o/app", checkout=app, base="develop", watch=["repo-profile.md"])
        changed = V.git_watch_changed([repo, ADW])
        self.assertEqual(changed(None, "2026-10-10T00:00:00Z", "2026-10-20T00:00:00Z"), "watch path changed in app")
        self.assertIsNone(changed("app", "2026-10-16T00:00:00Z", "2026-10-20T00:00:00Z"))
        self.assertIsNone(changed("other", "2026-10-10T00:00:00Z", "2026-10-20T00:00:00Z"))
        broken = Repo(name="app", slug="o/app", checkout=app, base="no-such-branch", watch=["repo-profile.md"])
        self.assertEqual(V.git_watch_changed([broken])(None, "2026-10-10T00:00:00Z", "2026-10-20T00:00:00Z"),
                         "watch check failed in app")
