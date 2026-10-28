"""Test-only builders: scratch dirs, a fake `gh`, transcript records. Never imported by the reader."""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(SCRIPTS, "adw-analyze.py")

FAKE_GH = r'''#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as f:
    f.write(json.dumps(argv) + "\n")
if argv and os.environ.get("FAKE_GH_FAIL") == argv[0]:
    sys.exit(1)
with open(os.environ["FAKE_GH_DATA"]) as f:
    data = json.load(f)
if argv[:2] == ["repo", "view"]:
    vis = data.get("visibility", {}).get(argv[2])
    if vis is None:
        sys.exit(1)
    print(vis)
    sys.exit(0)
print("unsupported fake gh call: " + " ".join(argv), file=sys.stderr)
sys.exit(2)
'''


class FakeGh:
    def __init__(self, tmp: str):
        self.bin = os.path.join(tmp, "bin")
        os.makedirs(self.bin, exist_ok=True)
        self.data_path = os.path.join(tmp, "gh-data.json")
        self.log_path = os.path.join(tmp, "gh-log.jsonl")
        path = os.path.join(self.bin, "gh")
        with open(path, "w") as f:
            f.write(FAKE_GH.replace("#!/usr/bin/env python3", "#!" + sys.executable, 1))
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
        self.data = {}
        self.set()

    def set(self, **parts) -> None:
        self.data.update(parts)
        with open(self.data_path, "w") as f:
            json.dump(self.data, f)

    def calls(self) -> list[list[str]]:
        if not os.path.exists(self.log_path):
            return []
        with open(self.log_path) as f:
            return [json.loads(line) for line in f]

    def env(self) -> dict:
        return {"PATH": self.bin + os.pathsep + os.environ.get("PATH", ""),
                "FAKE_GH_DATA": self.data_path, "FAKE_GH_LOG": self.log_path}


class TmpCase(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.gh = FakeGh(self.tmp)

    def mkdir(self, rel: str) -> str:
        d = os.path.join(self.tmp, rel)
        os.makedirs(d, exist_ok=True)
        return d

    def write_json(self, path: str, obj) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(obj, f)

    def git(self, *args, cwd: str) -> str:
        return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()

    def git_repo(self, rel: str, remote: str | None = None) -> str:
        d = self.mkdir(rel)
        self.git("init", "-q", "-b", "main", cwd=d)
        self.git("config", "user.email", "t@t", cwd=d)
        self.git("config", "user.name", "t", cwd=d)
        if remote:
            self.git("remote", "add", "origin", remote, cwd=d)
        return d

    def run_cli(self, *args, **env) -> subprocess.CompletedProcess:
        full = {k: v for k, v in os.environ.items() if k != "ADW_ANALYSIS_DIR"}
        full.update(self.gh.env())
        full.update(env)
        return subprocess.run([sys.executable, CLI, *args], capture_output=True, text=True, env=full)
