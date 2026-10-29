"""Tests for adw_analyze.github. Run: cd scripts && python3 -m unittest -v test_adw_analyze_github"""
import os
import unittest
from unittest import mock

from adw_analyze import github
from adw_analyze.config import Repo
from adw_analyze.testkit import TmpCase, pr_node

BLOCK = """contract   abc1234def            depth D2       resumed-from 0
tier       orchestrator sonnet · author sonnet · impl sonnet · level u2+u3
cycles     fix 1/3 · review v2 2/2      progress-conditions none fired
phases     implement 9m · gates 14m · verify 7m · review 21m · reverify 6m
owner-wait 1h 5m
gates      g1 0 · g2 0 · g4 0 (base red: SnapshotTest — pré-existente)
open-findings none — read 4 comments"""
APP = Repo(name="app", slug="o/app", base="develop")


class Block(unittest.TestCase):
    def test_block_fenced_unfenced_details(self):
        shapes = [f"Intro\n\n```\n{BLOCK}\n```\n\nTail",
                  f"Intro\n\n{BLOCK}\n\nTail",
                  f"## blocked\n<details><summary>evidence</summary>\n\n```text\n{BLOCK}\n```\n</details>"]
        for body in shapes:
            rows, n = github.parse_block(body)
            self.assertEqual(n, 1)
            self.assertEqual(set(rows), {"contract", "tier", "cycles", "phases", "owner-wait", "gates", "open-findings"})

    def test_block_raw_strings_kept(self):
        rows, _ = github.parse_block(f"```\n{BLOCK}\n```")
        self.assertEqual(rows["gates"], "g1 0 · g2 0 · g4 0 (base red: SnapshotTest — pré-existente)")
        self.assertTrue(rows["contract"].startswith("abc1234def"))

    def test_two_blocks_counted(self):
        rows, n = github.parse_block(f"```\n{BLOCK}\n```\nold:\n```\ncontract   0000000\nowner-wait 9m\n```")
        self.assertEqual(n, 2)
        self.assertEqual(rows["owner-wait"], "1h 5m")

    def test_block_stops_at_the_fence(self):
        rows, _ = github.parse_block("```\ncontract   abc1234\n```\n\nphases  this is prose, not a row")
        self.assertEqual(set(rows), {"contract"})

    def test_no_contract_row_is_none(self):
        self.assertEqual(github.parse_block("```\nowner-wait 0m\ncycles fix 0/3\n```"), (None, 0))

    def test_minutes(self):
        self.assertEqual(github.minutes("1h 5m"), 65.0)
        self.assertEqual(github.minutes("0m"), 0.0)
        self.assertIsNone(github.minutes("unmeasured (Docker restart halts)"))
        self.assertIsNone(github.minutes(None))

    def test_cycles(self):
        c = github.cycles("fix 1/3 · review v2 2/2      progress-conditions none fired")
        self.assertEqual((c["fix"], c["fix_cap"], c["review"], c["review_cap"], c["progress"]), (1, 3, 2, 2, "none"))
        self.assertEqual(github.cycles("fix 0/3 · review 0/2 progress-conditions P3 fired")["progress"], "fired")
        self.assertEqual(github.cycles("fix 0/3 progress-conditions P2 evaluated, not consumed")["progress"], "not consumed")
        self.assertIsNone(github.cycles("fix 0/3")["progress"])


class Prs(TmpCase):
    def fetch(self, nodes, since="2026-10-01T00:00:00Z", repo=APP, **env):
        self.gh.set(prs={repo.slug: nodes})
        with mock.patch.dict(os.environ, {**self.gh.env(), **env}):
            return github.fetch_prs(repo, since)

    def test_final_pr_excludes_inherited(self):
        [pr] = self.fetch([pr_node(50, "[adw s] The intent", commits=[
            "[adw s u01] unit one (#41)", "fix-attempt-3: nope", "[adw s u02] unit two (#42)",
            "fix-attempt-2: gate 4", "fix(review): naming"])])
        self.assertIsNone(pr.unit)
        self.assertEqual((pr.slug, pr.adw), ("s", True))
        self.assertEqual([c.inherited for c in pr.commits], [True, False, True, False, False])
        self.assertEqual((pr.fix_cycles, pr.review_fix_commits), (3, 1))

    def test_unit_pr_fields(self):
        [pr] = self.fetch([pr_node(41, "[adw s u01] unit one", body=f"```\n{BLOCK}\n```", merge_oid="f" * 40,
                                   labels=["blocked"], last_edited="2026-10-10T11:00:00Z")])
        self.assertEqual((pr.unit, pr.contract_sha, pr.merge_sha, pr.base), ("u01", "abc1234def", "f" * 40, "develop"))
        self.assertEqual((pr.block_count, pr.labels_now), (1, {"blocked"}))

    def test_fetch_paginates_and_stops_at_since(self):
        nodes = [pr_node(n, f"[adw s u0{n}] x", created=f"2026-10-0{n}T10:00:00Z") for n in range(1, 6)]
        got = self.fetch(nodes, since="2026-10-03T00:00:00Z")
        self.assertEqual(sorted(p.number for p in got), [3, 4, 5])
        pages = [c for c in self.gh.calls() if c[:2] == ["api", "graphql"]]
        self.assertEqual(len(pages), 2)

    def test_gh_failure_raises_source_error(self):
        with self.assertRaises(github.SourceError) as e:
            self.fetch([pr_node(1, "x")], FAKE_GH_FAIL="api")
        self.assertEqual(e.exception.repo, "app")

    def test_labels_ever(self):
        [pr] = self.fetch([pr_node(41, "[adw s u01] x", labeled=["blocked"], labels=["failed"])])
        self.assertEqual(pr.labels_ever, {"blocked", "failed"})
        self.assertEqual(pr.labels_now, {"failed"})

    def test_contract_repo_reads_files(self):
        adw = Repo(name="adw", slug="humbertouchiyama/adw", role="contract", base="main")
        [pr] = self.fetch([pr_node(9, "adw-build: x", files=["commands/adw-build.md"])], repo=adw)
        self.assertEqual(pr.files, ["commands/adw-build.md"])
        self.assertFalse(pr.adw)
        query = next(c for c in self.gh.calls() if c[:2] == ["api", "graphql"])
        self.assertTrue(any("files(first: 100)" in a for a in query))

    def test_open_prs(self):
        self.gh.set(open={APP.slug: [pr_node(7, "[adw s u01] x", state="OPEN", labels=["blocked"],
                                             created="2026-06-01T10:00:00Z")]})
        with mock.patch.dict(os.environ, self.gh.env()):
            [pr] = github.fetch_open_prs(APP)
        self.assertEqual((pr.number, pr.state, pr.merged), (7, "OPEN", None))


if __name__ == "__main__":
    unittest.main()
