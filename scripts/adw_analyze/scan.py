"""--scan: the last guard before a dated folder is committed (spec §5.4). Transcripts have held a
private key twice. A hit is a secret pattern in any output, or a 40-character run of a transcript line
(sampled every 20 characters, so any copied span of 59 or more characters is caught) that also appears
in an output. Every string of every record is read (tool results keep whole files outside the message),
over every file in the app transcript dirs: the critical pass can read all of them. Hits print as
file:line and kind, never the matched text."""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass

from .facts import transcript_paths

WINDOW = 40
STRIDE = 20
SECRETS = [re.compile(p) for p in (
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r'"private_key"\s*:', r"AKIA[0-9A-Z]{16}", r"gh[pousr]_[A-Za-z0-9]{36,}",
    r"github_pat_[A-Za-z0-9_]{40,}", r"AIza[0-9A-Za-z_-]{35}", r"xox[abprs]-[A-Za-z0-9-]{10,}",
    r"sk-ant-[A-Za-z0-9_-]{20,}", r"sk-[A-Za-z0-9]{32,}", r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}",
)]
PREDICTS = re.compile(r"\bpredicts\s")
ANALYZER = ("adw-analyze.py", '"/adw-analyze')


@dataclass
class Hit:
    file: str
    line: int
    kind: str


def norm(s: str) -> str:
    return " ".join(s.split())


def offsets(n: int):
    if n < WINDOW:
        return []
    out = list(range(0, n - WINDOW + 1, STRIDE))
    if out[-1] != n - WINDOW:
        out.append(n - WINDOW)
    return out


def strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for v in o.values():
            yield from strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v)


def ran_analyzer(main_path: str) -> bool:
    with open(main_path, errors="replace") as f:
        return any(a in line for line in f for a in ANALYZER)


def scan(out_dir: str, transcript_paths_: list[str]) -> list[Hit]:
    hits, index = [], {}
    for name in sorted(os.listdir(out_dir)):
        path = os.path.join(out_dir, name)
        if not os.path.isfile(path):
            continue
        with open(path, errors="replace") as f:
            for i, line in enumerate(f, 1):
                if any(rx.search(line) for rx in SECRETS):
                    hits.append(Hit(name, i, "secret"))
                t = norm(line)
                for j in range(0, len(t) - WINDOW + 1):
                    index.setdefault(t[j:j + WINDOW], (name, i))
    seen = set()
    for p in transcript_paths_:
        with open(p, errors="replace") as f:
            for raw in f:
                try:
                    o = json.loads(raw)
                except ValueError:
                    continue
                if not isinstance(o, dict):
                    continue
                for s in strings(o):
                    for line in s.splitlines():
                        t = norm(line)
                        if len(t) < WINDOW or PREDICTS.search(t):
                            continue
                        for j in offsets(len(t)):
                            where = index.get(t[j:j + WINDOW])
                            if where and where not in seen:
                                seen.add(where)
                                hits.append(Hit(where[0], where[1], "transcript"))
    return sorted(hits, key=lambda h: (h.file, h.line, h.kind))


def scan_paths(projects_dir: str, repos: list) -> list[str]:
    out = []
    for r in repos:
        if r.role != "app":
            continue
        paths = transcript_paths(projects_dir, r)
        skip = {os.path.basename(p)[:-len(".jsonl")] for p in paths if "/subagents/" not in p and ran_analyzer(p)}
        for p in paths:
            sid = p.split(os.sep)[-3] if "/subagents/" in p else os.path.basename(p)[:-len(".jsonl")]
            if sid not in skip:
                out.append(p)
    return out


def run_scan(reports: str, repos: list, args) -> int:
    if not args.date or not os.path.isdir(os.path.join(reports, args.date)):
        print(f"adw-analyze: --scan needs --date naming an existing folder in {reports}", file=sys.stderr)
        return 2
    hits = scan(os.path.join(reports, args.date), scan_paths(os.path.expanduser(args.projects), repos))
    for h in hits:
        print(f"{h.file}:{h.line} {h.kind}")
    print(f"leak scan: {len(hits)} hit(s)" if hits else "leak scan: clean")
    return 4 if hits else 0
