"""Facts: transcripts and PRs joined into intents, and the Slice every metric is computed over."""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field
from typing import Callable

from .attribute import attribute_all
from .config import Repo
from .github import PR, SourceError, fetch_open_prs, fetch_prs
from .transcripts import SessionFacts, read_session, ts_seconds

WAIT_CAP_H = 12.0


def wait_h(s: SessionFacts) -> float:
    """Σ min(gap, cap) over human prompts, gap = prompt − the assistant record before it."""
    return sum(min(max(ts_seconds(t) - ts_seconds(prev), 0) / 3600, WAIT_CAP_H) for t, prev in s.human_prompts if t and prev)


def run_h(s: SessionFacts) -> float:
    """Wall time with every gap capped like the wait, so a share compares like with like."""
    ts = [ts_seconds(t) for t in s.turn_ts]
    return sum(min(b - a, WAIT_CAP_H * 3600) for a, b in zip(ts, ts[1:])) / 3600


@dataclass
class Intent:
    repo: str
    slug: str
    prs: list = field(default_factory=list)
    sessions: list = field(default_factory=list)

    @property
    def mains(self) -> list[SessionFacts]:
        return [s for s in self.sessions if s.is_main]

    @property
    def first_prompt(self) -> str | None:
        ts = [t for s in self.mains for t, _ in s.human_prompts if t]
        return min(ts, key=ts_seconds) if ts else None

    @property
    def last_merge(self) -> str | None:
        ts = [p.merged for p in self.prs if p.merged]
        return max(ts, key=ts_seconds) if ts else None

    @property
    def contract_sha(self) -> str | None:
        for p in sorted(self.prs, key=lambda p: p.created):
            if p.contract_sha:
                return p.contract_sha
        return None

    @property
    def cost(self) -> float:
        return sum(s.cost for s in self.sessions)

    @property
    def prompts(self) -> int:
        return sum(len(s.human_prompts) for s in self.mains)

    @property
    def owner_wait_h(self) -> float:
        return sum(wait_h(s) for s in self.mains)

    @property
    def run_h(self) -> float:
        return sum(run_h(s) for s in self.mains)

    @property
    def lead_h(self) -> float | None:
        a, b = self.first_prompt, self.last_merge
        return (ts_seconds(b) - ts_seconds(a)) / 3600 if a and b else None


@dataclass
class Facts:
    until: str
    repos: list
    sessions: list
    prs: list
    open_prs: list
    intents: list
    slug_of: dict
    repo_of: dict
    excluded_sessions: int = 0
    predict_lines: dict = field(default_factory=dict)

    def role_of(self, repo_name: str) -> str:
        return next((r.role for r in self.repos if r.name == repo_name), "app")

    def intent(self, repo: str, slug: str | None) -> Intent | None:
        if slug is None:
            return None
        return self._index.get((repo, slug))

    def __post_init__(self):
        self._index = {(i.repo, i.slug): i for i in self.intents}


def assemble(repos: list[Repo], sessions_by_repo: dict[str, list[SessionFacts]], prs: list[PR], open_prs: list[PR],
             until: str, excluded_sessions: int = 0) -> Facts:
    slug_of, repo_of, intents = {}, {}, {}
    for p in prs:
        if p.adw and p.slug:
            intents.setdefault((p.repo, p.slug), Intent(repo=p.repo, slug=p.slug)).prs.append(p)
    for r in repos:
        if r.role != "app":
            continue
        ss = sessions_by_repo.get(r.name, [])
        known = {slug for (repo, slug) in intents if repo == r.name}
        by_number = {p.number: p.slug for p in prs if p.repo == r.name and p.adw}
        for path, slug in attribute_all(ss, known, by_number, r.slug).items():
            slug_of[path] = slug
        for s in ss:
            repo_of[s.path] = r.name
            slug = slug_of.get(s.path)
            if slug:
                intents[(r.name, slug)].sessions.append(s)
    sessions = [s for r in repos for s in sessions_by_repo.get(r.name, [])]
    return Facts(until=until, repos=repos, sessions=sessions, prs=prs, open_prs=open_prs, intents=list(intents.values()),
                 slug_of=slug_of, repo_of=repo_of, excluded_sessions=excluded_sessions)


def transcript_paths(projects_dir: str, repo: Repo) -> list[str]:
    out = set()
    for pattern in repo.transcripts:
        base = os.path.join(projects_dir, pattern)
        out.update(glob.glob(os.path.join(base, "*.jsonl")))
        out.update(glob.glob(os.path.join(base, "*", "subagents", "*.jsonl")))
    return sorted(out)


def build_facts(repos: list[Repo], projects_dir: str, until: str, since: str,
                read: Callable[[str, dict], SessionFacts] = read_session) -> Facts:
    projects_dir = os.path.expanduser(projects_dir)
    lo, hi = ts_seconds(since), ts_seconds(until)
    by_repo, excluded = {}, 0
    for r in repos:
        if r.role != "app":
            continue
        paths = transcript_paths(projects_dir, r)
        if not paths:
            raise SourceError(r.name, f"no transcript files match {r.transcripts} under {projects_dir}")
        ss = []
        for p in paths:
            if os.path.getmtime(p) < lo:
                continue
            s = read(p, r.gates)
            if s.first_ts and ts_seconds(s.first_ts) < hi and s.last_ts and ts_seconds(s.last_ts) >= lo:
                ss.append(s)
        analyzer = {s.session_id for s in ss if s.ran_analyzer}
        excluded += sum(1 for s in ss if s.session_id in analyzer)
        by_repo[r.name] = [s for s in ss if s.session_id not in analyzer]
    prs, open_prs = [], []
    for r in repos:
        prs += fetch_prs(r, since if r.role == "app" else None)
        if r.role == "app":
            open_prs += fetch_open_prs(r)
    return assemble(repos, by_repo, prs, open_prs, until, excluded)


class Slice:
    """A time range, optionally one side of a contract-version split (spec §5.3)."""

    def __init__(self, facts: Facts, start: str, end: str, side: tuple[str, str] | None = None,
                 is_after: Callable[[str, str], bool | None] | None = None, split_at: str | None = None,
                 repo: str | None = None):
        """side = ("after"|"before", merge sha). An item with no contract sha falls back to the clock:
        after when its time is at or past split_at; with no split_at it is on both sides."""
        if side and not is_after:
            raise ValueError("a side split needs is_after")
        self.facts, self.start, self.end, self.side, self.is_after = facts, start, end, side, is_after
        self.lo, self.hi = ts_seconds(start), ts_seconds(end)
        self.split = ts_seconds(split_at) if split_at else None
        self.repo = repo
        self.unknown_shas: set = set()

    @property
    def is_current(self) -> bool:
        return self.hi == ts_seconds(self.facts.until)

    def inside(self, ts: str | None) -> bool:
        return bool(ts) and self.lo <= ts_seconds(ts) < self.hi

    def in_repo(self, repo: str | None) -> bool:
        return self.repo is None or repo == self.repo

    def side_ok(self, sha: str | None, ts: str | None = None) -> bool:
        if not self.side:
            return True
        after = self.side[0] == "after"
        if not sha:
            return self.split is None or not ts or (ts_seconds(ts) >= self.split) == after
        r = self.is_after(self.side[1], sha)
        if r is None:
            self.unknown_shas.add(sha)
            return False
        return r == after

    def pr_sha(self, p: PR) -> str | None:
        if p.contract_sha:
            return p.contract_sha
        i = self.facts.intent(p.repo, p.slug)
        return i.contract_sha if i else None

    def prs(self, field: str = "created", adw: bool = True) -> list[PR]:
        return [p for p in self.facts.prs if self.facts.role_of(p.repo) == "app" and (p.adw or not adw)
                and self.in_repo(p.repo) and self.inside(getattr(p, field))
                and self.side_ok(self.pr_sha(p), getattr(p, field))]

    def contract_prs(self, field: str = "merged") -> list[PR]:
        return [p for p in self.facts.prs if self.facts.role_of(p.repo) == "contract" and self.inside(getattr(p, field))
                and any(f.startswith(("commands/", "scripts/")) for f in p.files)]

    def sessions(self) -> list[SessionFacts]:
        out = []
        for s in self.facts.sessions:
            repo = self.facts.repo_of.get(s.path)
            if not self.inside(s.first_ts) or not self.in_repo(repo):
                continue
            i = self.facts.intent(repo, self.facts.slug_of.get(s.path))
            if self.side_ok(i.contract_sha if i else None, s.first_ts):
                out.append(s)
        return out

    def intents(self, anchor: str = "last_merge") -> list[Intent]:
        """Intents with at least one attributed session: every intent metric reads transcripts."""
        return [i for i in self.facts.intents if i.sessions and self.in_repo(i.repo) and self.inside(getattr(i, anchor))
                and self.side_ok(i.contract_sha, getattr(i, anchor))]
