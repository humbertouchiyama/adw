"""Tests for adw_analyze.config and the CLI guard. Run: cd scripts && python3 -m unittest -v test_adw_analyze_config"""
import json
import os
import unittest
from unittest import mock

from adw_analyze import config
from adw_analyze.testkit import TmpCase

TWO_REPOS = {"schema": 1, "repos": [
    {"name": "app", "slug": "o/app", "checkout": "/x/app", "base": "develop",
     "transcripts": ["-x-app", "-x-app--claude-worktrees-*"],
     "watch": ["repo-profile.md"], "gates": {"gate 4": "testDebugUnitTest"}},
    {"name": "adw", "slug": "humbertouchiyama/adw", "role": "contract", "checkout": "/x/adw"},
]}


class Guard(TmpCase):
    def test_public_checkout_is_refused(self):
        repo = self.git_repo("reports", remote="https://github.com/humbertouchiyama/adw.git")
        self.gh.set(visibility={"humbertouchiyama/adw": "PUBLIC"})
        self.assertEqual(self.run_cli("--reports", repo).returncode, 3)

    def test_gh_error_is_refused(self):
        repo = self.git_repo("reports", remote="git@github.com:o/adw-analysis.git")
        self.gh.set(visibility={"o/adw-analysis": "PRIVATE"})
        self.assertEqual(self.run_cli("--reports", repo, FAKE_GH_FAIL="repo").returncode, 3)

    def test_private_checkout_passes(self):
        repo = self.git_repo("reports", remote="git@github.com:o/adw-analysis.git")
        self.gh.set(visibility={"o/adw-analysis": "PRIVATE"})
        with mock.patch.dict(os.environ, self.gh.env()):
            self.assertIsNone(config.check_reports_dir(repo))

    def test_dir_without_remote_passes(self):
        plain = self.mkdir("plain")
        bare = self.git_repo("local-only")
        with mock.patch.dict(os.environ, self.gh.env()):
            self.assertIsNone(config.check_reports_dir(plain))
            self.assertIsNone(config.check_reports_dir(bare))
        self.assertEqual(self.gh.calls(), [])

    def test_path_with_a_space(self):
        repo = self.git_repo("AXC MED/reports", remote="git@github.com:o/adw-analysis.git")
        self.gh.set(visibility={"o/adw-analysis": "PRIVATE"})
        self.write_json(os.path.join(repo, "sources.json"), TWO_REPOS)
        self.assertEqual(self.run_cli("--reports", repo, "--check-config").returncode, 0)


class Sources(TmpCase):
    def test_loads_repos(self):
        d = self.mkdir("reports")
        self.write_json(os.path.join(d, "sources.json"), TWO_REPOS)
        app, adw = config.load_sources(d)
        self.assertEqual((app.name, app.slug, app.base, app.role), ("app", "o/app", "develop", "app"))
        self.assertEqual(app.transcripts, ["-x-app", "-x-app--claude-worktrees-*"])
        self.assertEqual(app.gates, {"gate 4": "testDebugUnitTest"})
        self.assertEqual((adw.role, adw.transcripts, adw.watch), ("contract", [], []))

    def test_transcripts_complete_since(self):
        d = self.mkdir("reports")
        self.write_json(os.path.join(d, "sources.json"), {**TWO_REPOS, "transcripts_complete_since": "2026-09-28"})
        self.assertEqual(config.load_meta(d), {"transcripts_complete_since": "2026-09-28"})
        self.write_json(os.path.join(d, "sources.json"), TWO_REPOS)
        self.assertEqual(config.load_meta(d), {})

    def test_missing_file_and_unknown_key_exit_2(self):
        d = self.mkdir("reports")
        self.assertEqual(self.run_cli("--reports", d, "--check-config").returncode, 2)
        bad = json.loads(json.dumps(TWO_REPOS))
        bad["repos"][0]["colour"] = "red"
        self.write_json(os.path.join(d, "sources.json"), bad)
        r = self.run_cli("--reports", d, "--check-config")
        self.assertEqual(r.returncode, 2)
        self.assertIn("colour", r.stderr)

    def test_env_var_names_the_dir(self):
        d = self.mkdir("reports")
        self.write_json(os.path.join(d, "sources.json"), TWO_REPOS)
        self.assertEqual(self.run_cli("--check-config", ADW_ANALYSIS_DIR=d).returncode, 0)
        self.assertEqual(self.run_cli("--check-config").returncode, 2)


if __name__ == "__main__":
    unittest.main()
