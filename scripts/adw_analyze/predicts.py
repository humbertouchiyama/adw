"""The predicts line every contract PR carries (spec §5.2):

    predicts  <metric-id> <down|up> <N%|N|to-zero> by <YYYY-MM-DD> for <path>[ §<section>] [repo <name>]
    predicts  none — <reason>

A line that starts with `predicts` and breaks the grammar or names a bad metric, path or deadline is
rejected and counted, so a typo shows up in the next report instead of silently never being judged."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Callable

from .github import PR
from .metrics import REGISTRY
from .transcripts import ts_seconds

MAX_DAYS = 49
START = re.compile(r"^\s*`?predicts\s")
LINE = re.compile(r"^\s*`?predicts\s+(?P<metric>[a-z0-9_.-]+)\s+(?P<dir>down|up)\s+(?P<amt>to-zero|\d+(?:\.\d+)?%?)"
                  r"\s+by\s+(?P<by>\d{4}-\d{2}-\d{2})\s+for\s+(?P<path>\S+)(?:\s+§(?P<sec>\S+))?"
                  r"(?:\s+repo\s+(?P<repo>\S+))?\s*`?\s*$")
NONE = re.compile(r"^\s*`?predicts\s+none\s*(?:—|--|-)\s*(?P<reason>.*?\S)\s*`?\s*$")


@dataclass
class Prediction:
    pr: int
    key: str
    line: str
    metric: str
    direction: str
    amount: float
    unit: str
    by: str
    for_path: str
    section: str | None
    repo: str | None
    merged: str
    merge_sha: str
    kind = "prediction"


@dataclass
class NoPrediction:
    pr: int
    reason: str
    kind = "none"


@dataclass
class Rejected:
    pr: int
    line: str
    reason: str
    kind = "rejected"


def read_predictions(pr: PR, path_exists: Callable[[str, str], bool]) -> list:
    if not pr.merged:
        return []
    out = []
    for raw in (pr.body or "").splitlines():
        if not START.match(raw):
            continue
        line = raw.strip().strip("`").strip()
        n = NONE.match(raw)
        if n:
            out.append(NoPrediction(pr=pr.number, reason=n.group("reason")))
            continue
        m = LINE.match(raw)
        if not m:
            out.append(Rejected(pr=pr.number, line=line, reason="bad grammar"))
            continue
        reason = check(m, pr, path_exists)
        if reason:
            out.append(Rejected(pr=pr.number, line=line, reason=reason))
            continue
        amt = m.group("amt")
        unit = "zero" if amt == "to-zero" else "pct" if amt.endswith("%") else "abs"
        out.append(Prediction(pr=pr.number, key=f"{pr.number}:{hashlib.sha1(line.encode()).hexdigest()[:8]}", line=line,
                              metric=m.group("metric"), direction=m.group("dir"),
                              amount=0.0 if unit == "zero" else float(amt.rstrip("%")), unit=unit, by=m.group("by"),
                              for_path=m.group("path"), section=m.group("sec"), repo=m.group("repo"),
                              merged=pr.merged, merge_sha=pr.merge_sha or ""))
    return out


def check(m: re.Match, pr: PR, path_exists: Callable[[str, str], bool]) -> str | None:
    metric = REGISTRY.get(m.group("metric"))
    if metric is None:
        return "unknown metric"
    if not metric.predictable:
        return "metric not predictable"
    if not path_exists(pr.merge_sha or "", m.group("path")):
        return "path not at merge commit"
    days = (ts_seconds(m.group("by") + "T00:00:00Z") - ts_seconds(pr.merged)) / 86400
    if days < 0:
        return "deadline before merge"
    if days > MAX_DAYS:
        return "deadline over 49 days"
    return None
