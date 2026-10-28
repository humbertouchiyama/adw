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
if argv[:2] == ["api", "graphql"]:
    fields = {}
    for i, a in enumerate(argv):
        if a in ("-f", "-F") and "=" in argv[i + 1]:
            k, v = argv[i + 1].split("=", 1)
            fields[k] = v
    slug = fields["owner"] + "/" + fields["name"]
    kind = "open" if "states: OPEN" in fields["query"] else "prs"
    nodes = data.get(kind, {}).get(slug, [])
    if kind == "prs":
        nodes = sorted(nodes, key=lambda n: n["createdAt"], reverse=True)
    page = int(os.environ.get("FAKE_GH_PAGE", "2"))
    start = int(fields.get("cursor") or 0)
    chunk = nodes[start:start + page]
    more = start + page < len(nodes)
    print(json.dumps({"data": {"repository": {"pullRequests": {
        "pageInfo": {"hasNextPage": more, "endCursor": str(start + page) if more else None}, "nodes": chunk}}}}))
    sys.exit(0)
print("unsupported fake gh call: " + " ".join(argv), file=sys.stderr)
sys.exit(2)
'''


def usage(**over) -> dict:
    u = {"input_tokens": 10, "output_tokens": 100, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}
    u.update(over)
    return u


def assistant(ts: str, msg_id: str, model: str = "claude-opus-5-5", usage_: dict | None = None, tools=(), text=None, **extra) -> dict:
    content = list(tools) + ([{"type": "text", "text": text}] if text else [])
    return {"type": "assistant", "timestamp": ts, **extra,
            "message": {"id": msg_id, "model": model, "usage": usage_ or usage(), "content": content}}


def tool_use(id: str, name: str, **input) -> dict:
    return {"type": "tool_use", "id": id, "name": name, "input": input}


def user_prompt(ts: str, text: str = "go", **extra) -> dict:
    return {"type": "user", "timestamp": ts, "origin": {"kind": "human"}, "promptSource": "typed", **extra,
            "message": {"role": "user", "content": text}}


def tool_result(ts: str, tool_use_id: str, text: str = "", is_error: bool = False, **extra) -> dict:
    return {"type": "user", "timestamp": ts, **extra, "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_use_id, "content": text, "is_error": is_error}]}}


def system(ts: str, subtype: str, **fields) -> dict:
    return {"type": "system", "subtype": subtype, "timestamp": ts, **fields}


def _write_lines(path: str, records) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for r in records:
            f.write((r if isinstance(r, str) else json.dumps(r)) + "\n")
    return path


def write_session(projects: str, project: str, sid: str, records) -> str:
    """A string in records is written verbatim (a bad line)."""
    return _write_lines(os.path.join(projects, project, sid + ".jsonl"), records)


def write_subagent(projects: str, project: str, sid: str, agent_id: str, records, tool_use_id: str,
                   parent_agent_id: str | None = None, **meta) -> str:
    base = os.path.join(projects, project, sid, "subagents", "agent-" + agent_id)
    m = {"toolUseId": tool_use_id, "spawnDepth": 2 if parent_agent_id else 1, **meta}
    if parent_agent_id:
        m["parentAgentId"] = parent_agent_id
    os.makedirs(os.path.dirname(base), exist_ok=True)
    with open(base + ".meta.json", "w") as f:
        json.dump(m, f)
    return _write_lines(base + ".jsonl", records)


def pr_node(number: int, title: str, body: str = "", state: str = "MERGED", created: str = "2026-10-10T10:00:00Z",
            merged: str | None = "auto", closed: str | None = None, last_edited: str | None = None, base: str = "develop",
            head: str = "h", merge_oid: str | None = None, commits=(), labels=(), labeled=(), files=None) -> dict:
    """commits: (headline, date) pairs or headlines; labeled: label names from LABELED_EVENTs."""
    if merged == "auto":
        merged = created.replace("T10:", "T12:") if state == "MERGED" else None
    cs = []
    for i, c in enumerate(commits):
        h, d = (c, created) if isinstance(c, str) else c
        cs.append({"commit": {"oid": f"{number:04d}{i:036d}", "messageHeadline": h, "committedDate": d}})
    n = {"number": number, "title": title, "body": body, "state": state, "createdAt": created, "mergedAt": merged,
         "closedAt": closed or merged, "lastEditedAt": last_edited, "baseRefName": base, "headRefName": head,
         "mergeCommit": {"oid": merge_oid} if merge_oid else None,
         "labels": {"nodes": [{"name": x} for x in labels]},
         "timelineItems": {"nodes": [{"label": {"name": x}} for x in labeled]},
         "commits": {"nodes": cs}}
    if files is not None:
        n["files"] = {"nodes": [{"path": p} for p in files]}
    return n


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
