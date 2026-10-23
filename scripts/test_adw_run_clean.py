"""Tests for adw-run-clean.py against scratch git repos and a fake `gh`. Run: python3 -m unittest -v"""
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "adw-run-clean.py")

FAKE_GH = r'''#!/usr/bin/env python3
import json, os, sys
if os.environ.get("FAKE_GH_FAIL"):
    sys.exit(1)
branch = sys.argv[sys.argv.index("--head") + 1]
with open(os.environ["FAKE_GH_PRS"]) as f:
    print(json.dumps(json.load(f).get(branch, [])))
'''

DD_HASH = "abcdefghijklmnopqrstuvwxyzab"  # 28 lowercase letters, the shape Xcode names a DerivedData dir with


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        bin_dir = os.path.join(self.tmp, "bin")
        os.mkdir(bin_dir)
        gh = os.path.join(bin_dir, "gh")
        with open(gh, "w") as f:
            f.write(FAKE_GH)
        os.chmod(gh, os.stat(gh).st_mode | stat.S_IEXEC)
        self.env = dict(os.environ, PATH=bin_dir + os.pathsep + os.environ["PATH"],
                        GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1",
                        GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                        GIT_COMMITTER_EMAIL="t@t")
        self.prs_file = os.path.join(self.tmp, "prs.json")
        self.prs = {}
        self.save_prs()
        self.env["FAKE_GH_PRS"] = self.prs_file
        self.origin = os.path.join(self.tmp, "origin.git")
        self.main = os.path.join(self.tmp, "AXC MED", "AXCMedApp")  # a space, on purpose
        self.wts = os.path.join(self.main, ".claude", "worktrees")
        self.dd = os.path.join(self.tmp, "DerivedData")
        os.makedirs(self.dd)
        self.git("init", "-q", "--bare", self.origin, cwd=self.tmp)
        self.git("clone", "-q", self.origin, self.main, cwd=self.tmp)
        self.write(self.main, "iosApp/Podfile.lock", "COCOAPODS: 1.17.0\n")
        self.write(self.main, ".gitignore", "build/\n.claude/worktrees/\n")
        self.git("add", "-A")
        self.git("commit", "-qm", "base")
        self.git("push", "-q", "origin", "HEAD:main")

    def save_prs(self):
        import json
        with open(self.prs_file, "w") as f:
            json.dump(self.prs, f)

    def pr(self, branch, head, state="OPEN"):
        self.prs.setdefault(branch, []).append({"number": len(self.prs) + 1, "state": state, "headRefOid": head})
        self.save_prs()

    def git(self, *args, cwd=None):
        p = subprocess.run(["git", *args], cwd=cwd or self.main, env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout.strip()

    def write(self, root, rel, text):
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(text)

    def worktree(self, name, branch=None, push=True, detach=False, pr=True):
        """A worktree at .claude/worktrees/<name> with one commit of its own, pushed, with a PR."""
        wt = os.path.join(self.wts, name)
        if detach:
            self.git("worktree", "add", "-q", "--detach", wt, "origin/main")
            return wt
        self.git("worktree", "add", "-q", "-b", branch, wt, "origin/main")
        self.write(wt, f"{name}.txt", name)
        self.git("add", "-A", cwd=wt)
        self.git("commit", "-qm", name, cwd=wt)
        if push:
            self.git("push", "-q", "origin", branch, cwd=wt)
            if pr:
                self.pr(branch, self.git("rev-parse", "HEAD", cwd=wt))
        return wt

    def derived(self, workspace_path, name="iosApp"):
        d = os.path.join(self.dd, f"{name}-{DD_HASH}")
        os.makedirs(os.path.join(d, "Build"))
        with open(os.path.join(d, "info.plist"), "wb") as f:
            plistlib.dump({"WorkspacePath": workspace_path}, f)
        return d

    def run_clean(self, *args, cwd=None):
        p = subprocess.run([sys.executable, SCRIPT, "--repo", self.main, "--derived-data", self.dd, *args],
                           cwd=cwd or self.tmp, env=self.env, capture_output=True, text=True)
        return p.returncode, p.stdout + p.stderr

    def registered(self):
        return [os.path.basename(l[len("worktree "):]) for l in
                self.git("worktree", "list", "--porcelain").splitlines() if l.startswith("worktree ")]


class Scope(Base):
    def test_removes_only_this_slugs_worktrees(self):
        self.worktree("adw-foo-u1", "adw/foo-u1")
        self.worktree("adw-foo-u2+u3", "adw/foo-u2+u3")
        self.worktree("adw-close-foo", "adw/foo")
        self.worktree("adw-foo-bar-u1", "adw/foo-bar-u1")   # another intent whose slug starts with foo
        self.worktree("adw-foobar-u1", "adw/foobar-u1")
        self.worktree("my-work", "my-work")
        rc, out = self.run_clean("--slug", "foo")
        self.assertEqual(rc, 0, out)
        left = self.registered()
        for gone in ("adw-foo-u1", "adw-foo-u2+u3", "adw-close-foo"):
            self.assertNotIn(gone, left, out)
        for kept in ("adw-foo-bar-u1", "adw-foobar-u1", "my-work"):
            self.assertIn(kept, left, out)
        self.assertIn("run-clean: 3 worktrees", out)

    def test_review_worktree_only_for_named_prs(self):
        self.worktree("pr-7", detach=True)
        self.worktree("pr-8", detach=True)
        rc, out = self.run_clean("--slug", "foo", "--pr", "7")
        self.assertNotIn("pr-7", self.registered(), out)
        self.assertIn("pr-8", self.registered(), out)

    def test_verify_worktree_is_reset_then_removed(self):
        wt = self.worktree("pr-ready-foo-u1-v2", detach=True)
        self.worktree("pr-ready-foo-close-v1", detach=True)
        self.write(wt, "iosApp/Podfile.lock", "COCOAPODS: 1.16.2\n")   # a gate-file restore, a lockfile rewrite
        self.write(wt, "gate-output.log", "x")                        # untracked gate output
        rc, out = self.run_clean("--slug", "foo")
        self.assertNotIn("pr-ready-foo-u1-v2", self.registered(), out)
        self.assertNotIn("pr-ready-foo-close-v1", self.registered(), out)

    def test_verify_names_of_other_intents_are_not_matched(self):
        # slug foo must not reach intent foo-u2's or foo-close's verify worktrees, nor an improvised name
        names = ["pr-ready-foo-u2-close-v1", "pr-ready-foo-close-u1-v1", "pr-ready-foo-v1",
                 "pr-ready-foo-final-v1", "pr-ready-42-v1"]
        for n in names:
            self.worktree(n, detach=True)
        rc, out = self.run_clean("--slug", "foo", "--pr", "42")
        for n in names:
            self.assertIn(n, self.registered(), out)

    def test_branch_that_does_not_match_the_name_is_kept(self):
        self.worktree("adw-foo-u1", "something-else")
        rc, out = self.run_clean("--slug", "foo")
        self.assertIn("adw-foo-u1", self.registered())
        self.assertIn("expected adw/foo-u1", out)

    def test_bad_slug_and_a_path_outside_git(self):
        rc, out = self.run_clean("--slug", "../x")
        self.assertEqual(rc, 2, out)
        p = subprocess.run([sys.executable, SCRIPT, "--repo", self.dd, "--slug", "foo"], env=self.env,
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 1, p.stderr)

    def test_repo_may_name_a_worktree(self):
        other = self.worktree("my-work", "my-work")
        self.worktree("adw-foo-u1", "adw/foo-u1")
        p = subprocess.run([sys.executable, SCRIPT, "--repo", other, "--slug", "foo", "--derived-data", self.dd],
                           cwd=self.tmp, env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertNotIn("adw-foo-u1", self.registered(), p.stdout)


class Guards(Base):
    def test_unpushed_head_is_kept(self):
        wt = self.worktree("adw-foo-u1", "adw/foo-u1")
        self.write(wt, "later.txt", "a commit after the push")
        self.git("add", "-A", cwd=wt)
        self.git("commit", "-qm", "later", cwd=wt)
        rc, out = self.run_clean("--slug", "foo")
        self.assertIn("adw-foo-u1", self.registered())
        self.assertIn("HEAD is on no remote ref and is no PR's head", out)

    def test_a_unit_with_no_pr_is_kept(self):
        self.worktree("adw-foo-u1", "adw/foo-u1", pr=False)
        rc, out = self.run_clean("--slug", "foo")
        self.assertIn("adw-foo-u1", self.registered())
        self.assertIn("no PR has head adw/foo-u1", out)

    def test_gh_failure_keeps_units_but_not_verify_worktrees(self):
        self.worktree("adw-foo-u1", "adw/foo-u1")
        self.worktree("pr-ready-foo-u1-v1", detach=True)
        self.env["FAKE_GH_FAIL"] = "1"
        rc, out = self.run_clean("--slug", "foo")
        self.assertIn("adw-foo-u1", self.registered())
        self.assertIn("gh did not answer", out)
        self.assertNotIn("pr-ready-foo-u1-v1", self.registered(), out)

    def test_merged_pr_head_proves_a_branch_the_remote_deleted(self):
        wt = self.worktree("adw-foo-u1", "adw/foo-u1", pr=False)
        head = self.git("rev-parse", "HEAD", cwd=wt)
        self.git("push", "-q", "origin", "--delete", "adw/foo-u1", cwd=wt)
        self.git("fetch", "-q", "--prune", "origin")
        self.pr("adw/foo-u1", head, state="MERGED")
        rc, out = self.run_clean("--slug", "foo")
        self.assertNotIn("adw-foo-u1", self.registered(), out)

    def test_provisioned_file_is_restored_and_anything_else_keeps_it(self):
        wt = self.worktree("adw-foo-u1", "adw/foo-u1")
        self.write(wt, "iosApp/Podfile.lock", "COCOAPODS: 1.16.2\n")
        rc, out = self.run_clean("--slug", "foo")
        self.assertIn("adw-foo-u1", self.registered())
        self.assertIn("uncommitted: iosApp/Podfile.lock", out)
        rc, out = self.run_clean("--slug", "foo", "--provisioned", "iosApp/Podfile.lock")
        self.assertNotIn("adw-foo-u1", self.registered(), out)

    def test_untracked_and_staged_files_keep_it(self):
        wt = self.worktree("adw-foo-u1", "adw/foo-u1")
        self.write(wt, "notes.md", "work in progress")
        wt2 = self.worktree("adw-foo-u2", "adw/foo-u2")
        self.write(wt2, "src.kt", "staged")
        self.git("add", "src.kt", cwd=wt2)
        rc, out = self.run_clean("--slug", "foo", "--provisioned", "iosApp/Podfile.lock")
        self.assertIn("adw-foo-u1", self.registered())
        self.assertIn("adw-foo-u2", self.registered())
        self.assertIn("uncommitted: notes.md", out)

    def test_ignored_build_output_does_not_keep_it(self):
        wt = self.worktree("adw-foo-u1", "adw/foo-u1")
        self.write(wt, "build/out.bin", "x" * 1000)
        rc, out = self.run_clean("--slug", "foo")
        self.assertNotIn("adw-foo-u1", self.registered(), out)
        self.assertFalse(os.path.exists(wt))

    def test_a_process_working_inside_keeps_it_but_an_idle_daemon_does_not(self):
        wt = self.worktree("adw-foo-u1", "adw/foo-u1")
        wt2 = self.worktree("adw-foo-u2", "adw/foo-u2")
        sleeper = "import time; time.sleep(60)"
        busy = subprocess.Popen([sys.executable, "-c", sleeper], cwd=wt)
        daemon = subprocess.Popen([sys.executable, "-c", sleeper,
                                   "org.gradle.launcher.daemon.bootstrap.GradleDaemon"], cwd=wt2)
        for p in (busy, daemon):
            self.addCleanup(p.wait)
            self.addCleanup(p.kill)
        time.sleep(0.3)
        rc, out = self.run_clean("--slug", "foo")
        self.assertIn("adw-foo-u1", self.registered())
        self.assertIn(f"process {busy.pid} uses it", out)
        self.assertNotIn("adw-foo-u2", self.registered(), out)

    def test_the_session_running_inside_a_worktree_never_removes_it(self):
        wt = self.worktree("adw-foo-u1", "adw/foo-u1")
        rc, out = self.run_clean("--slug", "foo", cwd=wt)
        self.assertIn("adw-foo-u1", self.registered())
        self.assertIn("this session runs inside it", out)


class DerivedData(Base):
    def test_only_derived_data_of_a_removed_scope_worktree(self):
        gone = self.worktree("adw-foo-u1", "adw/foo-u1")
        kept = self.worktree("adw-foo-u2", "adw/foo-u2", pr=False)
        d_gone = self.derived(os.path.join(gone, "iosApp/iosApp.xcworkspace"))
        d_kept = self.derived(os.path.join(kept, "iosApp/iosApp.xcworkspace"), name="iosAppB")
        d_verify = self.derived(os.path.join(self.wts, "pr-ready-foo-u1-v1/iosApp/iosApp.xcworkspace"), name="iosAppC")
        d_main = self.derived(os.path.join(self.main, "iosApp/iosApp.xcworkspace"), name="iosAppD")
        d_other = self.derived(os.path.join(self.wts, "adw-bar-u1/iosApp/iosApp.xcworkspace"), name="iosAppE")
        shared = os.path.join(self.dd, "ModuleCache.noindex")
        os.makedirs(shared)
        rc, out = self.run_clean("--slug", "foo")
        self.assertFalse(os.path.exists(d_gone), out)
        self.assertFalse(os.path.exists(d_verify), out)    # its worktree was removed by an earlier pr-ready pass
        for d in (d_kept, d_main, d_other, shared):
            self.assertTrue(os.path.exists(d), out)
        self.assertIn("2 DerivedData dirs", out)

    def test_dry_run_changes_nothing_and_lists_everything(self):
        wt = self.worktree("adw-foo-u1", "adw/foo-u1")
        d = self.derived(os.path.join(wt, "iosApp/iosApp.xcworkspace"))
        rc, out = self.run_clean("--slug", "foo", "--dry-run")
        self.assertIn("adw-foo-u1", self.registered())
        self.assertTrue(os.path.exists(d))
        self.assertIn("would remove  adw-foo-u1", out)
        self.assertIn("would delete", out)
        self.assertIn("(dry run): 1 worktrees, 1 DerivedData dirs", out)

    def test_a_kept_derived_data_dir_is_counted(self):
        wt = self.worktree("adw-foo-u1", "adw/foo-u1")
        d = self.derived(os.path.join(wt, "iosApp/iosApp.xcworkspace"))
        sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", d + "/Build"])
        self.addCleanup(sleeper.wait)
        self.addCleanup(sleeper.kill)
        time.sleep(0.3)
        rc, out = self.run_clean("--slug", "foo")
        self.assertTrue(os.path.exists(d), out)
        self.assertIn("kept 1", out)

    def test_symlinked_or_unreadable_derived_data_is_left(self):
        wt = self.worktree("adw-foo-u1", "adw/foo-u1")
        outside = os.path.join(self.tmp, "precious")
        os.makedirs(outside)
        os.symlink(outside, os.path.join(self.dd, f"iosApp-{DD_HASH}"))
        no_plist = os.path.join(self.dd, f"iosAppZ-{DD_HASH}")
        os.makedirs(no_plist)
        rc, out = self.run_clean("--slug", "foo")
        self.assertTrue(os.path.isdir(outside), out)
        self.assertTrue(os.path.isdir(no_plist), out)


if __name__ == "__main__":
    unittest.main()
