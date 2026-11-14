"""Tests for adw-screens.py against a temp bare remote, a fake `gh` and, for the moving-remote cases, a
`git` wrapper that moves the remote ref just before a push. Run: cd scripts && python3 -m unittest -v test_adw_screens"""
from __future__ import annotations

import json
import os
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "adw-screens.py")
# Production passes refs/adw-screens (GitHub takes it); a local receive-pack refuses a one-level ref as "funny".
REF = "refs/adw/screens"
HEAD = "0123456789abcdef0123456789abcdef01234567"

FAKE_GH = r'''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
body = None
if "--input" in args:
    with open(args[args.index("--input") + 1]) as f:
        body = json.load(f).get("body")
with open(os.environ["FAKE_GH_LOG"], "a") as f:
    f.write(json.dumps({"args": args, "body": body}) + "\n")
fails = os.environ.get("FAKE_GH_FAIL_WRITES")
method = args[args.index("-X") + 1] if "-X" in args else "GET"
if method != "GET" and fails:
    sys.exit(1)
if method == "GET":
    with open(os.environ["FAKE_GH_COMMENTS"]) as f:
        print(json.dumps(json.load(f)))
elif method == "POST":
    print(json.dumps({"id": 900, "html_url": "https://github.com/o/r/pull/7#issuecomment-900"}))
else:
    cid = args[args.index("-X") + 2].rsplit("/", 1)[1]
    print(json.dumps({"id": int(cid), "html_url": "https://github.com/o/r/pull/7#issuecomment-" + cid}))
'''

# Moves the remote ref before each of the first FAKE_MOVES pushes, the way another walk's push would.
FAKE_GIT = r'''#!/usr/bin/env python3
import os, subprocess, sys
real = os.environ["REAL_GIT"]
if "push" in sys.argv[1:]:
    counter = os.environ["FAKE_MOVES_FILE"]
    with open(counter) as f:
        done = int(f.read() or 0)
    moves = os.environ["FAKE_MOVES"].split()
    if done < len(moves):
        subprocess.run([real, "-C", os.environ["FAKE_MOVER"], "push", "-q", "-f", "origin",
                        moves[done] + ":" + os.environ["FAKE_REF"]], check=True)
        with open(counter, "w") as f:
            f.write(str(done + 1))
os.execv(real, [real] + sys.argv[1:])
'''


def png(path: str, w: int, h: int) -> None:
    raw = b"".join(b"\x00" + b"\x80\x80\x80" * w for _ in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.bin = os.path.join(self.tmp, "bin")
        os.mkdir(self.bin)
        self.tool("gh", FAKE_GH)
        self.env = dict(os.environ, PATH=self.bin + os.pathsep + os.environ["PATH"],
                        GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1",
                        GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                        GIT_COMMITTER_EMAIL="t@t",
                        FAKE_GH_LOG=os.path.join(self.tmp, "gh.log"),
                        FAKE_GH_COMMENTS=os.path.join(self.tmp, "comments.json"))
        self.comments([])
        self.origin = os.path.join(self.tmp, "origin.git")
        self.checkout = os.path.join(self.tmp, "App Repo")  # a space, on purpose
        self.git("init", "-q", "--bare", self.origin, cwd=self.tmp)
        self.git("clone", "-q", self.origin, self.checkout, cwd=self.tmp)
        self.sweep = os.path.join(self.tmp, "sweep")
        self.screens_dir = os.path.join(self.sweep, "screens")
        os.makedirs(self.screens_dir)
        self.screens_md = os.path.join(self.sweep, "screens.md")
        with open(self.screens_md, "w") as f:
            f.write("## Screens\n- SCREEN-1 · Enfermarias · iphone17, ipad\n- SCREEN-2 · Detalhe do paciente · iphone17\n")

    def tool(self, name: str, text: str) -> None:
        path = os.path.join(self.bin, name)
        with open(path, "w") as f:
            f.write(text)
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)

    def comments(self, items: list) -> None:
        with open(os.path.join(self.tmp, "comments.json"), "w") as f:
            json.dump(items, f)

    def gh_calls(self) -> list:
        path = self.env["FAKE_GH_LOG"]
        if not os.path.exists(path):
            return []
        with open(path) as f:
            return [json.loads(line) for line in f]

    def writes(self) -> list:
        return [c for c in self.gh_calls() if "-X" in c["args"]]

    def git(self, *args, cwd=None) -> str:
        p = subprocess.run(["git", *args], cwd=cwd or self.checkout, env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout.strip()

    def remote_commit(self, files: dict, parent: str | None = None) -> str:
        """A commit made elsewhere and pushed to the screens ref, as an earlier walk would."""
        work = os.path.join(self.tmp, "elsewhere")
        if not os.path.exists(work):
            self.git("clone", "-q", self.origin, work, cwd=self.tmp)
        idx = os.path.join(self.tmp, "idx-elsewhere")
        env = dict(self.env, GIT_INDEX_FILE=idx)
        run = lambda *a, **k: subprocess.run(["git", *a], cwd=work, env=env, capture_output=True, text=True, check=True, **k).stdout.strip()
        if parent:
            run("read-tree", parent)
        else:
            run("read-tree", "--empty")
        for path, text in files.items():
            blob = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=work, env=env, input=text,
                                  capture_output=True, text=True, check=True).stdout.strip()
            run("update-index", "--add", "--cacheinfo", "100644,%s,%s" % (blob, path))
        tree = run("write-tree")
        commit = run("commit-tree", tree, *(["-p", parent] if parent else []), "-m", "elsewhere")
        os.remove(idx)
        return commit

    def push_remote(self, commit: str) -> None:
        self.git("push", "-q", "-f", "origin", "%s:%s" % (commit, REF), cwd=os.path.join(self.tmp, "elsewhere"))

    def image(self, name: str, w: int = 20, h: int = 40) -> None:
        png(os.path.join(self.screens_dir, name), w, h)

    def run_script(self, *extra, env=None):
        args = [sys.executable, SCRIPT, "--repo", "o/r", "--checkout", self.checkout, "--pr", "7",
                "--head", HEAD, "--walk", "2", "--screens", self.screens_md, "--dir", self.screens_dir,
                "--ref", REF, *extra]
        return subprocess.run(args, env=env or self.env, capture_output=True, text=True)

    def remote_tip(self) -> str:
        out = self.git("ls-remote", self.origin, REF)
        return out.split()[0] if out else ""

    def tree_paths(self, commit: str) -> list:
        return self.git("ls-tree", "-r", "--name-only", commit, cwd=self.origin).splitlines()


class TestPush(Base):
    def test_pushes_one_commit_under_pr_path(self):
        old = self.remote_commit({"pr-1/aaaaaaa/walk-1/SCREEN-1-iphone17.png": "old"})
        self.push_remote(old)
        self.image("SCREEN-1-iphone17.png")
        p = self.run_script()
        self.assertEqual(p.returncode, 0, p.stderr)
        tip = self.remote_tip()
        self.assertIn("pr-7/0123456/walk-2/SCREEN-1-iphone17.png", self.tree_paths(tip))
        self.assertIn("pr-1/aaaaaaa/walk-1/SCREEN-1-iphone17.png", self.tree_paths(tip))
        self.assertEqual(self.git("rev-parse", tip + "^", cwd=self.origin), old)

    def test_creates_ref_when_missing(self):
        self.image("SCREEN-1-iphone17.png")
        p = self.run_script()
        self.assertEqual(p.returncode, 0, p.stderr)
        tip = self.remote_tip()
        self.assertTrue(tip)
        self.assertEqual(self.git("rev-list", "--parents", "-n", "1", tip, cwd=self.origin), tip)

    def test_downscales_to_1000(self):
        self.image("SCREEN-1-iphone17.png", 1206, 2622)
        p = self.run_script()
        self.assertEqual(p.returncode, 0, p.stderr)
        out = os.path.join(self.tmp, "fetched.png")
        blob = self.git("rev-parse", self.remote_tip() + ":pr-7/0123456/walk-2/SCREEN-1-iphone17.png", cwd=self.origin)
        with open(out, "wb") as f:
            f.write(subprocess.run(["git", "cat-file", "blob", blob], cwd=self.origin, capture_output=True, check=True).stdout)
        dims = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", out], capture_output=True, text=True).stdout
        self.assertIn("pixelHeight: 1000", dims)


class TestMovingRemote(Base):
    def setUp(self):
        super().setUp()
        self.tool("git", FAKE_GIT)
        self.env["REAL_GIT"] = shutil.which("git", path=os.environ["PATH"])
        self.env["FAKE_MOVES_FILE"] = os.path.join(self.tmp, "moves")
        open(self.env["FAKE_MOVES_FILE"], "w").close()
        self.env["FAKE_REF"] = REF
        self.env["FAKE_MOVES"] = ""
        base = self.remote_commit({"base.txt": "b"})
        self.push_remote(base)
        self.env["FAKE_MOVER"] = os.path.join(self.tmp, "elsewhere")
        self.move1 = self.remote_commit({"m1.txt": "1"}, parent=base)
        self.move2 = self.remote_commit({"m2.txt": "2"}, parent=self.move1)
        self.image("SCREEN-1-iphone17.png")

    def test_retries_once_on_rejected_push(self):
        self.env["FAKE_MOVES"] = self.move1
        p = self.run_script()
        self.assertEqual(p.returncode, 0, p.stderr)
        tip = self.remote_tip()
        self.assertEqual(self.git("rev-parse", tip + "^", cwd=self.origin), self.move1)
        self.assertIn("pr-7/0123456/walk-2/SCREEN-1-iphone17.png", self.tree_paths(tip))

    def test_rejected_twice_exits_1_and_posts_nothing(self):
        self.env["FAKE_MOVES"] = "%s %s" % (self.move1, self.move2)
        p = self.run_script()
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        self.assertEqual(self.remote_tip(), self.move2)
        self.assertEqual(self.writes(), [])


class TestComment(Base):
    def test_comment_format(self):
        self.image("SCREEN-1-iphone17.png")
        self.image("SCREEN-1-ipad.png")
        p = self.run_script()
        self.assertEqual(p.returncode, 0, p.stderr)
        (post,) = self.writes()
        self.assertEqual(post["args"][:3], ["api", "-X", "POST"])
        body = post["body"]
        tip = self.remote_tip()
        self.assertTrue(body.startswith("<!-- adw-screens head=%s walk=2 -->\n**Screens at 0123456, walk 2**\n" % HEAD), body)
        self.assertIn("#### SCREEN-1 · Enfermarias\n", body)
        url = "https://github.com/o/r/blob/%s/pr-7/0123456/walk-2/SCREEN-1-iphone17.png?raw=true" % tip
        self.assertIn("![SCREEN-1 · iphone17](%s) ![SCREEN-1 · ipad](" % url, body)
        self.assertEqual(p.stdout.strip(), "screens https://github.com/o/r/pull/7#issuecomment-900 · 2 images")

    def test_replaces_existing_comment(self):
        self.comments([{"id": 5, "body": "unrelated"},
                       {"id": 41, "body": "<!-- adw-screens head=%s walk=1 -->\nold" % ("f" * 40)}])
        self.image("SCREEN-1-iphone17.png")
        p = self.run_script()
        self.assertEqual(p.returncode, 0, p.stderr)
        (patch,) = self.writes()
        self.assertEqual(patch["args"][:4], ["api", "-X", "PATCH", "repos/o/r/issues/comments/41"])
        self.assertIn("#issuecomment-41 · 1 images", p.stdout)

    def test_missing_image_still_posts_others(self):
        self.image("SCREEN-1-iphone17.png")
        self.image("SCREEN-2-iphone17.png")
        p = self.run_script()
        self.assertEqual(p.returncode, 0, p.stderr)
        body = self.writes()[0]["body"]
        self.assertNotIn("SCREEN-1 · ipad", body)
        self.assertIn("#### SCREEN-2 · Detalhe do paciente", body)
        self.assertTrue(p.stdout.strip().endswith("· 2 images"), p.stdout)

    def test_no_screens_dir(self):
        shutil.rmtree(self.screens_dir)
        p = self.run_script()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.strip(), "screens none — no images in %s" % self.screens_dir)
        self.assertEqual(self.gh_calls(), [])
        self.assertEqual(self.remote_tip(), "")

    def test_comment_failure_after_retry_exits_1(self):
        self.env["FAKE_GH_FAIL_WRITES"] = "1"
        self.image("SCREEN-1-iphone17.png")
        p = self.run_script()
        self.assertEqual(p.returncode, 1)
        self.assertEqual(len(self.writes()), 2)

    def test_bad_flag_exits_2(self):
        p = subprocess.run([sys.executable, SCRIPT, "--repo", "o/r"], env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        p = self.run_script("--walk", "x")
        self.assertEqual(p.returncode, 2)


if __name__ == "__main__":
    unittest.main()
