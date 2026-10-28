"""report.md, metrics.json and issue.md. Aggregates, metric ids, PR numbers and predicts lines only:
no transcript, prompt, command or file text ever reaches these files (spec §5.1)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .facts import WAIT_CAP_H, Facts
from .metrics import REGISTRY, MetricValue
from .pricing import PRICES, PRICES_AS_OF
from .verdicts import record_entry

NOT_MEASURED = [
    "background gate time ({bg} background gate runs in the window have no completion record)",
    "owner-found device defects",
    "escape rate (no Sentry release attribution yet; design §8)",
    "base-red truth on a repo with no CI",
    "any window before transcripts exist (earliest transcript read: {earliest})",
]
SELF_REPORT = "evidence"
LOOP = "loop"


@dataclass
class Run:
    until: str
    window: tuple
    prior: tuple
    facts: Facts
    win: dict
    pri: dict
    predictions: list = field(default_factory=list)
    verdicts: list = field(default_factory=list)
    records: dict = field(default_factory=dict)
    rejected: list = field(default_factory=list)
    legacy: list = field(default_factory=list)
    sources_hash: str = ""

    @property
    def date(self) -> str:
        return self.until[:10]


def fmt(metric_id: str, v: float | None) -> str:
    if v is None:
        return "no data"
    unit = REGISTRY[metric_id].unit
    if unit == "usd":
        return f"${v:,.2f}"
    if unit == "ratio":
        return f"{v * 100:.1f}%"
    if unit == "hours":
        return f"{v:.1f} h"
    if unit == "per1k":
        return f"{v:.2f}"
    return str(int(v)) if float(v).is_integer() else f"{v:.2f}"


def cell(metric_id: str, mv: MetricValue) -> str:
    if mv.status == "no data":
        return "no data"
    s = fmt(metric_id, mv.value)
    return s + f" (n {mv.n} < {REGISTRY[metric_id].min_n})" if mv.status == "below minimum" else s


def change(a: MetricValue, b: MetricValue) -> float | None:
    if a.value is None or b.value is None or b.value == 0:
        return None
    return (a.value - b.value) / abs(b.value) * 100


def amount_text(p) -> str:
    return "to-zero" if p.unit == "zero" else f"{p.amount:g}%" if p.unit == "pct" else f"{p.amount:g}"


def totals(facts: Facts) -> dict:
    ss = facts.sessions
    first = min((s.first_ts for s in ss if s.first_ts), default=None)
    unknown = {}
    for s in ss:
        for k, v in s.unknown_types.items():
            unknown[k] = unknown.get(k, 0) + v
    return {"sessions": len(ss), "excluded_sessions": facts.excluded_sessions, "bad_lines": sum(s.bad_lines for s in ss),
            "unknown_types": unknown, "unknown_models": sum(s.unknown_models for s in ss),
            "background_gate_calls": sum(s.background_gate_calls for s in ss), "earliest_transcript": first}


def entries(run: Run) -> dict:
    by_key = {p.key: p for p in run.predictions}
    out = {}
    for v in run.verdicts:
        p = by_key[v.key]
        e = record_entry(v, run.records)
        e.update(baseline=v.baseline.value, after=v.after.value, n_baseline=v.baseline.n, n_after=v.after.n,
                 unknown_shas=len(v.unknown_shas), pr=p.pr, metric=p.metric, for_path=p.for_path, section=p.section,
                 line=p.line)
        out[v.key] = e
    return out


def orphans(run: Run) -> list:
    """Records whose predicts line changed or was removed: the record stands (spec §5.3)."""
    live = {p.key for p in run.predictions}
    return [dict(r, key=k) for k, r in sorted(run.records.items()) if k not in live]


def metrics_json(run: Run, verdicts: dict, t: dict) -> dict:
    ms = {}
    for mid in REGISTRY:
        w, p = run.win[mid], run.pri[mid]
        ms[mid] = {"window": w.value, "prior": p.value, "n_window": w.n, "n_prior": p.n, "status_window": w.status,
                   "status_prior": p.status, "breakdown": w.breakdown}
    return {
        "schema": 1, "until": run.until, "window": list(run.window), "prior": list(run.prior),
        "prices": {"as_of": PRICES_AS_OF, "per_mtok_in_out_cacheread": PRICES, "cache_write_5m_x_in": 1.25,
                   "cache_write_1h_x_in": 2.0},
        "owner_wait_cap_h": WAIT_CAP_H, "sources_hash": run.sources_hash, "metrics": ms,
        "predictions": {p.key: {"pr": p.pr, "line": p.line, "metric": p.metric, "by": p.by} for p in run.predictions},
        "verdicts": verdicts,
        "rejected": [{"pr": r.pr, "line": r.line, "reason": r.reason} for r in run.rejected],
        "not_measured": [x.format(bg=t["background_gate_calls"], earliest=t["earliest_transcript"]) for x in NOT_MEASURED],
        **t,
    }


def delete_candidates(run: Run, verdicts: dict) -> list:
    """(pr, for_path, section, metric) of every failed verdict of record, live or orphaned."""
    out = [(p.pr, p.for_path, p.section, p.metric) for p in run.predictions if verdicts.get(p.key, {}).get("verdict") == "failed"]
    out += [(r.get("pr"), r.get("for_path"), r.get("section"), r.get("metric")) for r in orphans(run) if r.get("verdict") == "failed"]
    return out


def report_md(run: Run, verdicts: dict, t: dict) -> str:
    w0, w1 = run.window
    p0, p1 = run.prior
    out = [f"# ADW analysis {run.date}", "",
           f"Window {w0[:10]} → {w1[:10]}; prior {p0[:10]} → {p1[:10]}. Schema 1 · prices as of {PRICES_AS_OF} · "
           f"owner-wait gaps capped at {WAIT_CAP_H:g} h · sources {run.sources_hash}.",
           f"Sessions read {t['sessions']}, excluded {t['excluded_sessions']} (the analyzer's own) · bad lines "
           f"{t['bad_lines']} · unknown record types {sum(t['unknown_types'].values())} · unpriced models {t['unknown_models']}.",
           "", "## Verdicts", ""]
    if run.predictions:
        out += ["| PR | metric | predicts | baseline | after | verdict | note |", "|---|---|---|---|---|---|---|"]
        for p in run.predictions:
            e = verdicts[p.key]
            note = "; ".join(x for x in [
                f"record {e['record']} ({e['record_date']})" if e["record"] else "",
                f"restated {e['restated']}" if e["restated"] else "", e["cause"] or "",
                f"{e['unknown_shas']} unknown contract shas" if e["unknown_shas"] else ""] if x)
            out.append(f"| #{p.pr} | `{p.metric}` | {p.direction} {amount_text(p)} by {p.by} | {fmt(p.metric, e['baseline'])} "
                       f"(n {e['n_baseline']}) | {fmt(p.metric, e['after'])} (n {e['n_after']}) | {e['verdict']} | {note} |")
    else:
        out.append("No predicts lines yet.")
    lost = orphans(run)
    if lost:
        out += ["", "Records whose predicts line changed or was removed (the record stands):", ""]
        out += [f"- #{r.get('pr')} `{r.get('metric')}` — {r.get('verdict')} ({r.get('date')}); record stands" for r in lost]
    out += ["", "## Delete candidates", ""]
    cands = delete_candidates(run, verdicts)
    out += [f"- #{pr} `{path}`{' §' + sec if sec else ''} — `{metric}` failed. The owner decides."
            for pr, path, sec, metric in cands] or ["None."]
    out += ["", "## Metrics", "", "| id | window | prior | change | n |", "|---|---|---|---|---|"]
    out += metric_rows(run, lambda m: m.group not in (SELF_REPORT, LOOP))
    bds = [(mid, run.win[mid].breakdown) for mid in REGISTRY if run.win[mid].breakdown]
    if bds:
        out += ["", "Breakdowns (window):", ""]
        for mid, bd in bds:
            parts = ", ".join(f"{k} {fmt(mid, v) if REGISTRY[mid].unit != 'ratio' else v}" for k, v in sorted(bd.items()))
            out.append(f"- `{mid}`: {parts}")
    out += ["", "## Self-report trust", "", "PR-body evidence block, checked against git and gh.", "",
            "| id | window | prior | change | n |", "|---|---|---|---|---|"]
    out += metric_rows(run, lambda m: m.group == SELF_REPORT)
    out += ["", "## The loop", "", "| id | window | prior | change | n |", "|---|---|---|---|---|"]
    out += metric_rows(run, lambda m: m.group == LOOP)
    out += ["", "## Legacy verdicts (information only)", ""]
    out += [f"- #{x.get('pr')} {x.get('for')} — {x.get('verdict')}. {x.get('note', '')}".rstrip() for x in run.legacy] or ["None."]
    out += ["", "## Rejected predicts lines", ""]
    out += [f"- #{r.pr} `{r.line}` — {r.reason}" for r in run.rejected] or ["None."]
    out += ["", "## NOT MEASURED", ""]
    out += [f"- {x.format(bg=t['background_gate_calls'], earliest=t['earliest_transcript'])}" for x in NOT_MEASURED]
    out += ["", "## Critical pass", "", "critical pass: pending", ""]
    return "\n".join(out)


def metric_rows(run: Run, keep) -> list:
    rows = []
    for mid, m in REGISTRY.items():
        if not keep(m):
            continue
        w, p = run.win[mid], run.pri[mid]
        c = change(w, p)
        rows.append(f"| `{mid}` | {cell(mid, w)} | {cell(mid, p)} | {'—' if c is None else f'{c:+.0f}%'} | {w.n} |")
    return rows


def issue_md(run: Run, verdicts: dict) -> str:
    out = [f"ADW analysis {run.date}, window {run.window[0][:10]} → {run.window[1][:10]}.", "", "Verdicts reached this run:"]
    reached = [p for p in run.predictions if verdicts[p.key]["of_record"]]
    out += [f"- #{p.pr} `{p.metric}`: {verdicts[p.key]['verdict']}" for p in reached] or ["- none"]
    moved = []
    for mid, m in REGISTRY.items():
        w, p = run.win[mid], run.pri[mid]
        c = change(w, p)
        if m.predictable and w.status == "ok" and p.status == "ok" and c is not None:
            moved.append((abs(c), mid, c, w, p))
    moved.sort(reverse=True)
    out += ["", "Moved most (predictable, both windows ok):"]
    out += [f"- `{mid}`: {fmt(mid, p.value)} → {fmt(mid, w.value)} ({c:+.0f}%)" for _, mid, c, w, p in moved[:5]] or ["- none"]
    out += ["", "Delete candidates:"]
    out += [f"- #{pr} `{path}` — `{metric}`" for pr, path, _, metric in delete_candidates(run, verdicts)] or ["- none"]
    out += ["", "critical pass: pending", "leak scan: pending", "", f"Report: `{run.date}/report.md`", ""]
    return "\n".join(out)


def write_outputs(out_dir: str, run: Run) -> None:
    os.makedirs(out_dir)
    verdicts = entries(run)
    t = totals(run.facts)
    with open(os.path.join(out_dir, "metrics.json"), "w") as f:
        json.dump(metrics_json(run, verdicts, t), f, indent=1, sort_keys=True)
        f.write("\n")
    with open(os.path.join(out_dir, "report.md"), "w") as f:
        f.write(report_md(run, verdicts, t))
    with open(os.path.join(out_dir, "issue.md"), "w") as f:
        f.write(issue_md(run, verdicts))
