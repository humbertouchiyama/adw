"""`gh` GraphQL → PR facts, and the PR-body evidence block (commands/adw-build.md §3.4).

Trust order (spec §5.1): git and gh facts first, transcripts second, the evidence block last. Rows are
kept as raw strings and read by regex: the `gates` row alone has 233 shapes, some in Portuguese.
A row a body does not carry is no data, never 0."""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field

from .config import Repo

ROWS = ("contract", "tier", "cycles", "phases", "owner-wait", "asks", "gates", "mutation", "artifact",
        "open-findings", "smoke")
ROW_RX = re.compile(r"^\s*`?(" + "|".join(re.escape(r) for r in ROWS) + r")`?\s+(.*?)\s*$")
CONTRACT_RX = re.compile(r"^\s*`?contract`?\s+`?([0-9a-f]{7,40})\b")
TITLE = re.compile(r"^\[adw ([^\]\s]+)(?: ([^\]]+))?\]")
FIX_ATTEMPT = re.compile(r"^fix-attempt-(\d+)\b")
BLOCK_LINES = 15

QUERY = """query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    pullRequests(first: 40, after: $cursor, orderBy: {field: CREATED_AT, direction: DESC}%s) {
      pageInfo { hasNextPage endCursor }
      nodes {
        number title body state createdAt mergedAt closedAt lastEditedAt baseRefName headRefName
        mergeCommit { oid }
        labels(first: 20) { nodes { name } }
        timelineItems(first: 50, itemTypes: [LABELED_EVENT]) { nodes { ... on LabeledEvent { label { name } } } }
        commits(last: 100) { nodes { commit { oid messageHeadline committedDate } } }%s
      }
    }
  }
}"""
FILES = "\n        files(first: 100) { nodes { path } }"


class SourceError(Exception):
    def __init__(self, repo: str, reason: str):
        super().__init__(f"{repo}: {reason}")
        self.repo = repo
        self.reason = reason


@dataclass
class Commit:
    oid: str
    headline: str
    date: str
    inherited: bool


@dataclass
class PR:
    repo: str
    number: int
    title: str
    slug: str | None
    unit: str | None
    adw: bool
    state: str
    created: str
    merged: str | None
    closed: str | None
    last_edited: str | None
    base: str
    head: str
    merge_sha: str | None
    labels_now: set = field(default_factory=set)
    labels_ever: set = field(default_factory=set)
    commits: list = field(default_factory=list)
    files: list = field(default_factory=list)
    body: str = field(default="", repr=False)
    block: dict | None = None
    block_count: int = 0

    @property
    def own_commits(self) -> list[Commit]:
        return [c for c in self.commits if not c.inherited]

    @property
    def fix_cycles(self) -> int:
        ns = [int(m.group(1)) for c in self.own_commits for m in [FIX_ATTEMPT.match(c.headline)] if m]
        return max(ns) if ns else 0

    @property
    def review_fix_commits(self) -> int:
        return sum(1 for c in self.own_commits if c.headline.startswith("fix(review)"))

    @property
    def contract_sha(self) -> str | None:
        if not self.block or "contract" not in self.block:
            return None
        m = re.match(r"`?([0-9a-f]{7,40})", self.block["contract"])
        return m.group(1) if m else None


def parse_block(body: str) -> tuple[dict[str, str] | None, int]:
    lines = (body or "").splitlines()
    starts = [i for i, line in enumerate(lines) if CONTRACT_RX.match(line)]
    if not starts:
        return None, 0
    rows = {}
    for line in lines[starts[0]:starts[0] + BLOCK_LINES]:
        if line.strip().startswith("```"):
            break
        m = ROW_RX.match(line)
        if m and m.group(1) not in rows:
            rows[m.group(1)] = m.group(2)
    return rows, len(starts)


def minutes(text: str | None) -> float | None:
    found = re.findall(r"(\d+(?:\.\d+)?)\s*(h|m)\b", text or "")
    if not found:
        return None
    return sum(float(n) * (60 if unit == "h" else 1) for n, unit in found)


def cycles(text: str | None) -> dict:
    text = text or ""
    out = {"fix": None, "fix_cap": None, "review": None, "review_cap": None, "progress": None}
    m = re.search(r"\bfix (\d+)/(\d+)", text)
    if m:
        out["fix"], out["fix_cap"] = int(m.group(1)), int(m.group(2))
    m = re.search(r"\breview(?: v\d+)? (\d+)/(\d+)", text)
    if m:
        out["review"], out["review_cap"] = int(m.group(1)), int(m.group(2))
    if "progress-conditions" in text:
        tail = text.split("progress-conditions", 1)[1]
        if "none fired" in tail:
            out["progress"] = "none"
        elif re.search(r"not[ -]consumed", tail):
            out["progress"] = "not consumed"
        elif "fired" in tail:
            out["progress"] = "fired"
    return out


def to_pr(repo: Repo, n: dict) -> PR:
    m = TITLE.match(n.get("title") or "")
    commits = []
    for c in ((n.get("commits") or {}).get("nodes") or []):
        c = c.get("commit") or {}
        h = c.get("messageHeadline") or ""
        commits.append(Commit(oid=c.get("oid") or "", headline=h, date=c.get("committedDate") or "",
                              inherited=h.startswith("[adw ")))
    labels_now = {x["name"] for x in ((n.get("labels") or {}).get("nodes") or []) if x}
    labeled = {x["label"]["name"] for x in ((n.get("timelineItems") or {}).get("nodes") or []) if x and x.get("label")}
    body = n.get("body") or ""
    block, count = parse_block(body)
    return PR(repo=repo.name, number=int(n["number"]), title=n.get("title") or "", slug=m.group(1) if m else None,
              unit=m.group(2) if m else None, adw=bool(m), state=n.get("state") or "", created=n.get("createdAt") or "",
              merged=n.get("mergedAt"), closed=n.get("closedAt"), last_edited=n.get("lastEditedAt"),
              base=n.get("baseRefName") or "", head=n.get("headRefName") or "",
              merge_sha=(n.get("mergeCommit") or {}).get("oid"), labels_now=labels_now,
              labels_ever=labels_now | labeled, commits=commits,
              files=[f["path"] for f in ((n.get("files") or {}).get("nodes") or []) if f],
              body=body, block=block, block_count=count)


def pages(repo: Repo, open_only: bool):
    owner, name = repo.slug.split("/", 1)
    query = QUERY % (", states: OPEN" if open_only else "", FILES if repo.role == "contract" else "")
    cursor = None
    while True:
        argv = ["gh", "api", "graphql", "-f", "query=" + query, "-f", "owner=" + owner, "-f", "name=" + name]
        if cursor:
            argv += ["-f", "cursor=" + cursor]
        r = subprocess.run(argv, capture_output=True, text=True)
        if r.returncode != 0:
            raise SourceError(repo.name, "gh api graphql failed: " + (r.stderr.strip().splitlines() or ["no output"])[-1])
        try:
            data = json.loads(r.stdout)
            conn = data["data"]["repository"]["pullRequests"]
        except (ValueError, KeyError, TypeError):
            raise SourceError(repo.name, "gh api graphql returned an unexpected shape")
        yield conn.get("nodes") or []
        info = conn.get("pageInfo") or {}
        if not info.get("hasNextPage"):
            return
        cursor = info.get("endCursor")


def fetch_prs(repo: Repo, since: str | None) -> list[PR]:
    out = []
    for nodes in pages(repo, open_only=False):
        for n in nodes:
            if since and (n.get("createdAt") or "") < since:
                return out
            out.append(to_pr(repo, n))
    return out


def fetch_open_prs(repo: Repo) -> list[PR]:
    return [to_pr(repo, n) for nodes in pages(repo, open_only=True) for n in nodes]
