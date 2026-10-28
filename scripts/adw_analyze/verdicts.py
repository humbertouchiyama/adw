"""Verdicts on predicts lines (spec §5.3).

Before and after are split by contract version, not by clock: an ADW run reads the contract once at
its start, and long intents straddle merges. A PR is after when the predicting PR's merge commit is
an ancestor of the PR's `contract <sha>`. The after span runs merge → deadline; the baseline is the
same length before the merge (capped at 28 days) plus any old-contract run that finished after it.
The first committed metrics.json after the deadline holds the verdict of record; later runs print a
differing recompute as restated and never replace the record."""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from .config import Repo
from .facts import Facts, Slice
from .metrics import MetricValue, compute
from .predicts import Prediction
from .transcripts import ts_seconds

BASELINE_CAP_DAYS = 28
DATED = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass
class Verdict:
    key: str
    verdict: str
    baseline: MetricValue
    after: MetricValue
    cause: str | None = None
    unknown_shas: set = field(default_factory=set)


def iso(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def deadline(p: Prediction) -> str:
    return p.by + "T00:00:00Z"


def git_is_after(adw_dir: str) -> Callable[[str, str], bool | None]:
    cache = {}

    def is_after(merge_sha: str, contract_sha: str) -> bool | None:
        k = (merge_sha, contract_sha)
        if k not in cache:
            r = subprocess.run(["git", "-C", adw_dir, "merge-base", "--is-ancestor", merge_sha, contract_sha],
                               capture_output=True)
            cache[k] = True if r.returncode == 0 else False if r.returncode == 1 else None
        return cache[k]
    return is_after


def git_path_exists(adw_dir: str) -> Callable[[str, str], bool]:
    def exists(sha: str, path: str) -> bool:
        return subprocess.run(["git", "-C", adw_dir, "cat-file", "-e", f"{sha}:{path}"], capture_output=True).returncode == 0
    return exists


def git_watch_changed(repos: list[Repo]) -> Callable[[str | None, str, str], bool]:
    def changed(repo_name: str | None, start: str, end: str) -> bool:
        for r in repos:
            if r.role != "app" or not r.watch or not r.checkout or (repo_name and r.name != repo_name):
                continue
            out = subprocess.run(["git", "-C", r.checkout, "log", "--format=%H", f"origin/{r.base}", f"--since={start}",
                                  f"--until={end}", "--", *r.watch], capture_output=True, text=True).stdout
            if out.strip():
                return True
        return False
    return changed


def spans(p: Prediction, facts: Facts) -> tuple[str, str]:
    m, by = ts_seconds(p.merged), ts_seconds(deadline(p))
    start = iso(m - min(by - m, BASELINE_CAP_DAYS * 86400))
    end = iso(min(by, ts_seconds(facts.until)))
    return start, end


def overlapping(p: Prediction, others: list[Prediction], start: str) -> Prediction | None:
    lo, hi = ts_seconds(start), ts_seconds(deadline(p))
    for o in others:
        if o.key == p.key or o.metric != p.metric or (p.repo and o.repo and p.repo != o.repo):
            continue
        if ts_seconds(o.merged) < hi and ts_seconds(deadline(o)) > lo:
            return o
    return None


def met(p: Prediction, b: float, a: float) -> bool | None:
    if p.unit == "zero":
        return a == 0
    if p.unit == "pct":
        if b == 0:
            return None
        change = (a - b) / abs(b) * 100
    else:
        change = a - b
    return (-change if p.direction == "down" else change) >= p.amount


def judge(p: Prediction, facts: Facts, all_predictions: list[Prediction], is_after: Callable[[str, str], bool | None],
          watch_changed: Callable[[str | None, str, str], bool]) -> Verdict:
    start, end = spans(p, facts)
    common = dict(is_after=is_after, split_at=p.merged, repo=p.repo)
    after_sl = Slice(facts, p.merged, end, side=("after", p.merge_sha), **common)
    base_sl = Slice(facts, start, end, side=("before", p.merge_sha), **common)
    after, baseline = compute(p.metric, after_sl), compute(p.metric, base_sl)
    v = Verdict(key=p.key, verdict="", baseline=baseline, after=after, unknown_shas=after_sl.unknown_shas | base_sl.unknown_shas)
    if ts_seconds(facts.until) < ts_seconds(deadline(p)):
        v.verdict = "too early"
        return v
    other = overlapping(p, all_predictions, start)
    if other:
        v.verdict, v.cause = "confounded", f"overlaps #{other.pr}"
        return v
    if watch_changed(p.repo, start, deadline(p)):
        v.verdict, v.cause = "confounded", "watch path changed" + (f" in {p.repo}" if p.repo else "")
        return v
    if baseline.status != "ok" or after.status != "ok":
        v.verdict = "no data"
        return v
    ok = met(p, baseline.value, after.value)
    if ok is None:
        v.verdict, v.cause = "no data", "baseline 0"
    else:
        v.verdict = "worked" if ok else "failed"
    return v


def read_records(reports_dir: str) -> dict[str, dict]:
    out = {}
    if not os.path.isdir(reports_dir):
        return out
    import json
    for name in sorted(os.listdir(reports_dir)):
        path = os.path.join(reports_dir, name, "metrics.json")
        if not DATED.match(name) or not os.path.isfile(path):
            continue
        try:
            with open(path) as f:
                data = json.load(f)
        except ValueError:
            continue
        for key, v in (data.get("verdicts") or {}).items():
            if v.get("of_record") and key not in out:
                out[key] = {"verdict": v.get("verdict"), "date": name}
    return out


def record_entry(v: Verdict, records: dict[str, dict]) -> dict:
    rec = records.get(v.key)
    if rec:
        return {"verdict": rec["verdict"], "of_record": False, "record": rec["verdict"], "record_date": rec["date"],
                "restated": v.verdict if v.verdict != rec["verdict"] else None, "cause": v.cause}
    return {"verdict": v.verdict, "of_record": v.verdict != "too early", "record": None, "record_date": None,
            "restated": None, "cause": v.cause}
