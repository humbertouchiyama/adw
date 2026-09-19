#!/usr/bin/env python3
"""Tests for check-anchors.py. Run: python3 -B test_check_anchors.py"""
import os, shutil, subprocess, sys, tempfile, unittest

CA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "check-anchors.py")
BASE = {
    "README.md": "# r\n",
    "docs/00-design.md": "# D\n\n## 1. One\n\n**61.4% of AI PRs get no review**\n",
    "docs/repo-profile-EXAMPLE.md": "## §1 — A\n\n## §18 — Z\n",
    "commands/review-core.md": "## §1 — One\n\n## §9 — Nine\n",
    "commands/cleanup.md": "## 1. Steps\n\n> **Phase 0 reads the core first**\n\nSee `review-core §1`.\n",
}


def sh(cwd, *args):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=True).stdout


class Case(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        sh(self.d, "git", "init", "-q", "-b", "main")
        sh(self.d, "git", "config", "user.email", "t@t")
        sh(self.d, "git", "config", "user.name", "t")
        self.commit(BASE)

    def tearDown(self):
        shutil.rmtree(self.d)

    def commit(self, files, append=(), branch=None, start="main"):
        if branch:
            sh(self.d, "git", "checkout", "-q", "-B", branch, start)
        for path, text in files.items():
            os.makedirs(os.path.dirname(os.path.join(self.d, path)), exist_ok=True)
            with open(os.path.join(self.d, path), "w") as f:
                f.write(text)
        for path, text in append:
            with open(os.path.join(self.d, path), "a") as f:
                f.write(text)
        sh(self.d, "git", "add", "-A")
        sh(self.d, "git", "commit", "-q", "--allow-empty", "-m", "c")

    def check(self, base="main", head="pr", cwd=None):
        r = subprocess.run([sys.executable, "-B", CA, base, head], cwd=cwd or self.d,
                           capture_output=True, text=True)
        return r.returncode, r.stdout

    def pr(self, *append, files=None):
        self.commit(files or {}, append=append, branch="pr")


class Checker(Case):
    def test_clean(self):
        self.pr(("README.md", "See `review-core §9`.\n"))
        self.assertEqual(self.check(), (0, "all parsed citations resolve\n"))

    def test_unreadable_ref_is_exit_2(self):
        self.pr()
        self.assertEqual(self.check(head="nope")[0], 2)
        self.assertEqual(self.check(base="nope")[0], 2)

    def test_runs_from_a_subdirectory(self):
        self.pr(("README.md", "See `review-core §9`.\n"))
        self.assertEqual(self.check(cwd=os.path.join(self.d, "commands"))[0], 0)

    def test_wrapped_and_blockquoted_cites_are_read(self):
        self.pr(("README.md", "see\n`review-core`\n§77\n\n> quoted `review-core`\n> §88\n"))
        code, out = self.check()
        self.assertEqual(code, 1)
        self.assertIn("review-core §77", out)
        self.assertIn("review-core §88", out)

    def test_slash_list_is_read(self):
        self.pr(("README.md", "See `review-core §1/§77`.\n"))
        code, out = self.check()
        self.assertEqual(code, 1)
        self.assertIn("review-core §77", out)
        self.assertNotIn("§1 ", out)

    def test_anchor_main_fixed_after_the_branch_is_not_new(self):
        self.commit({}, append=[("README.md", "See `review-core §5`.\n")], branch="main")
        self.commit({}, branch="pr", start="main")
        sh(self.d, "git", "checkout", "-q", "main")
        self.commit({"README.md": "# r\n"})
        code, out = self.check()
        self.assertEqual(code, 0)
        self.assertIn("OLD  review-core §5", out)

    def test_moving_a_broken_cite_is_new_and_lists_only_the_added_site(self):
        self.commit({}, append=[("commands/cleanup.md", "See `review-core §5`.\n")], branch="main")
        self.commit({"commands/cleanup.md": BASE["commands/cleanup.md"]}, branch="pr")
        self.commit({}, append=[("README.md", "See `review-core §5`.\n")])
        code, out = self.check()
        self.assertEqual(code, 1)
        self.assertEqual(out.strip(), "NEW  review-core §5 does not resolve  <- README.md:2")

    def test_every_site_is_printed(self):
        self.pr(("README.md", "See `review-core §5`.\n" * 7))
        self.assertEqual(self.check()[1].count("README.md:"), 7)

    def test_optional_anchor_old_sites_are_opt_and_new_sites_stay_new(self):
        self.commit({}, append=[("commands/cleanup.md", "Read `repo-profile §19`.\n")], branch="main")
        self.pr(("README.md", "Read `repo-profile §19`, stop if absent.\n"))
        code, out = self.check()
        self.assertEqual(code, 1)
        self.assertIn("NEW  repo-profile §19 does not resolve  <- README.md:2", out)
        self.assertIn("OPT  repo-profile §19 does not resolve  <- commands/cleanup.md", out)

    def test_a_new_command_file_is_checked(self):
        self.pr(("README.md", "See `adw-x §2`.\n"), files={"commands/adw-x.md": "## §1 — X\n"})
        code, out = self.check()
        self.assertEqual(code, 1)
        self.assertIn("adw-x §2", out)

    def test_bare_number_bold_lead_is_not_an_anchor_but_a_phase_lead_is(self):
        self.pr(("README.md", "See `design §61` and `cleanup Phase 0`.\n"))
        code, out = self.check()
        self.assertEqual(code, 1)
        self.assertIn("design §61", out)
        self.assertNotIn("Phase 0", out)


if __name__ == "__main__":
    unittest.main()
