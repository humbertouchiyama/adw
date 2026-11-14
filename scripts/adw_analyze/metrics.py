"""The metric registry, schema v1. Ids are versioned: a definition change is a new id (spec §5.3).
Only rates, ratios and medians are predictable; counts and totals move with how much work happened.
A value is `no data` when its source is missing, never 0 (design §5.1)."""
from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass, field

from .facts import WAIT_CAP_H, Slice, run_h, wait_h
from .github import ROWS, cycles
from .pricing import family, message_cost
from .transcripts import ts_seconds

PREDICTABLE = ("rate", "ratio", "median")
PEAK = 250_000


@dataclass(frozen=True)
class Metric:
    id: str
    group: str
    kind: str
    min_n: int
    unit: str
    definition: str

    @property
    def predictable(self) -> bool:
        return self.kind in PREDICTABLE


@dataclass
class MetricValue:
    value: float | None
    n: int
    status: str
    breakdown: dict = field(default_factory=dict)


REGISTRY: dict[str, Metric] = {}
FUNCS = {}


def metric(name: str, kind: str, min_n: int, unit: str, definition: str, version: int = 1):
    def deco(fn):
        m = Metric(id=f"{name}.v{version}", group=name.split(".")[0], kind=kind, min_n=min_n, unit=unit,
                   definition=definition)
        REGISTRY[m.id] = m
        FUNCS[m.id] = fn
        return fn
    return deco


TRANSCRIPT_GROUPS = ("cost", "owner", "friction", "time")


def compute(metric_id: str, sl: Slice) -> MetricValue:
    m = REGISTRY[metric_id]
    ts_since = sl.facts.transcripts_since
    if m.group in TRANSCRIPT_GROUPS and ts_since and sl.lo < ts_seconds(ts_since):
        return MetricValue(None, 0, "no data", {})   # the slice starts before complete transcripts
    value, n, breakdown = FUNCS[metric_id](sl)
    if value is None or n == 0:
        return MetricValue(None, n, "no data", breakdown or {})
    return MetricValue(value, n, "below minimum" if n < m.min_n else "ok", breakdown or {})


def ratio(a: float, b: float) -> float | None:
    return a / b if b else None


def p90(xs: list[float]) -> float | None:
    xs = sorted(xs)
    return xs[max(0, math.ceil(0.9 * len(xs)) - 1)] if xs else None


def median(xs: list[float]) -> float | None:
    return statistics.median(xs) if xs else None


# --- cost ------------------------------------------------------------------------------------------

@metric("cost.total_usd", "total", 1, "usd", "$ of app-repo sessions (main and subagents), one dated price table")
def _(sl):
    ss = sl.sessions()
    bd = {}
    for s in ss:
        for k in ("repo:" + sl.facts.repo_of.get(s.path, "?"), "main" if s.is_main else "sub"):
            bd[k] = bd.get(k, 0.0) + s.cost
        for u in s.usage.values():
            k = "model:" + (family(u.model) or "unknown")
            bd[k] = bd.get(k, 0.0) + message_cost(u)
    return sum(s.cost for s in ss), len(ss), bd


@metric("cost.usd_per_merged_pr", "ratio", 10, "usd", "total $ / ADW PRs merged")
def _(sl):
    merged = sl.prs("merged")
    return ratio(sum(s.cost for s in sl.sessions()), len(merged)), len(merged), {}


@metric("cost.usd_per_intent_median", "median", 8, "usd", "median $ of intents whose last PR merged in the window")
def _(sl):
    xs = [i.cost for i in sl.intents()]
    return median(xs), len(xs), {}


@metric("cost.usd_per_intent_p90", "quantile", 8, "usd", "p90 $ of intents whose last PR merged in the window")
def _(sl):
    xs = [i.cost for i in sl.intents()]
    return p90(xs), len(xs), {}


@metric("cost.subagent_share", "ratio", 10, "ratio", "subagent $ / total $")
def _(sl):
    ss = sl.sessions()
    return ratio(sum(s.cost for s in ss if not s.is_main), sum(s.cost for s in ss)), len(ss), {}


@metric("cost.opus_main_share", "ratio", 10, "ratio", "Opus main-thread $ / total $")
def _(sl):
    ss = sl.sessions()
    opus = sum(message_cost(u) for s in ss if s.is_main for u in s.usage.values() if family(u.model) == "opus")
    return ratio(opus, sum(s.cost for s in ss)), len(ss), {}


# --- owner -----------------------------------------------------------------------------------------

def mains(sl):
    return [s for s in sl.sessions() if s.is_main]


@metric("owner.prompts", "count", 1, "count", "human prompts in app-repo main threads")
def _(sl):
    ms = mains(sl)
    return sum(len(s.human_prompts) for s in ms), len(ms), {}


@metric("owner.interrupts", "count", 1, "count", "interrupts in app-repo main threads")
def _(sl):
    ms = mains(sl)
    return sum(len(s.interrupts) for s in ms), len(ms), {}


@metric("owner.prompts_per_intent_median", "median", 8, "count", "median human prompts per intent")
def _(sl):
    xs = [i.prompts for i in sl.intents()]
    return median(xs), len(xs), {}


@metric("owner.wait_hours_per_intent_median", "median", 8, "hours",
        f"median per intent of Σ min(gap, {WAIT_CAP_H:g} h), gap = human prompt − previous assistant record")
def _(sl):
    xs = [i.owner_wait_h for i in sl.intents()]
    return median(xs), len(xs), {}


@metric("owner.wait_share", "ratio", 10, "ratio", "Σ capped owner wait / Σ capped wall time, over app-repo main threads")
def _(sl):
    ms = mains(sl)
    return ratio(sum(wait_h(s) for s in ms), sum(run_h(s) for s in ms)), len(ms), {}


@metric("owner.halts_per_merged_pr", "ratio", 10, "count", "human prompts while one of the intent's ADW PRs was open / merged PRs")
def _(sl):
    its = sl.intents()
    halts, merged = 0, 0
    for i in its:
        spans = [(ts_seconds(p.created), ts_seconds(p.closed or sl.facts.until)) for p in i.prs]
        merged += sum(1 for p in i.prs if p.merged)
        for s in i.mains:
            halts += sum(1 for t, _ in s.human_prompts if t and any(a <= ts_seconds(t) <= b for a, b in spans))
    return ratio(halts, merged), merged, {}


# --- outcomes --------------------------------------------------------------------------------------

@metric("outcome.prs_opened", "count", 1, "count", "ADW PRs opened")
def _(sl):
    n = len(sl.prs("created"))
    return n, n or len(sl.facts.prs), {}


@metric("outcome.prs_merged", "count", 1, "count", "ADW PRs merged")
def _(sl):
    n = len(sl.prs("merged"))
    return n, n or len(sl.facts.prs), {}


@metric("outcome.prs_closed", "count", 1, "count", "ADW PRs closed without merge")
def _(sl):
    n = sum(1 for p in sl.prs("closed") if not p.merged)
    return n, n or len(sl.facts.prs), {}


def label_rate(sl, label):
    opened = sl.prs("created")
    return ratio(sum(1 for p in opened if label in p.labels_ever), len(opened)), len(opened), {}


@metric("outcome.ever_blocked_rate", "rate", 20, "ratio", "opened ADW PRs that ever had the adw:blocked label")
def _(sl):
    return label_rate(sl, "adw:blocked")


@metric("outcome.failed_rate", "rate", 20, "ratio", "opened ADW PRs that ever had the adw:failed label")
def _(sl):
    return label_rate(sl, "adw:failed")


@metric("outcome.fix_cycles_per_pr", "rate", 20, "count", "mean max N of fix-attempt-N over merged ADW PRs (inherited commits excluded)")
def _(sl):
    merged = sl.prs("merged")
    return ratio(sum(p.fix_cycles for p in merged), len(merged)), len(merged), {}


@metric("outcome.review_fix_commits_per_pr", "rate", 20, "count", "mean fix(review): commits over merged ADW PRs")
def _(sl):
    merged = sl.prs("merged")
    return ratio(sum(p.review_fix_commits for p in merged), len(merged)), len(merged), {}


@metric("outcome.reverts", "count", 1, "count", 'PRs titled Revert "[adw')
def _(sl):
    all_prs = sl.prs("created", adw=False)
    return sum(1 for p in all_prs if p.title.startswith('Revert "[adw')), len(all_prs), {}


@metric("outcome.followup_fix_rate", "rate", 20, "ratio", "non-ADW fix PRs citing #N of an earlier merged ADW PR / merged ADW PRs")
def _(sl):
    merged = sl.prs("merged")
    adw = {(p.repo, p.number): p for p in sl.facts.prs if p.adw and p.merged}
    n = 0
    for p in sl.prs("created", adw=False):
        if p.adw or not re.search(r"(?i)\bfix", p.title):
            continue
        cited = {int(x) for x in re.findall(r"#(\d+)\b", p.title + "\n" + p.body)}
        if any((p.repo, c) in adw and ts_seconds(adw[(p.repo, c)].merged) < ts_seconds(p.created) for c in cited):
            n += 1
    return ratio(n, len(merged)), len(merged), {}


# --- auto-merge: the merge row adw-build §3.7's gate writes on independent and final PRs -----------

MERGE_ROW = re.compile(r"(merged)\b|hold (\d|call)\b")
AUTO_LABEL = "adw:auto-merged"
FALSE_PASS_DAYS = 7


def gate_result(p) -> tuple[str, str | None] | None:
    """("merged", None) or ("hold", <condition>) from the PR's merge row; None when it has none.
    §3.7 adds adw:auto-merged before it writes the merged row, so the label stands for a row write
    that was lost or cut."""
    if p.merged and AUTO_LABEL in p.labels_ever:
        return ("merged", None)
    m = MERGE_ROW.match((p.block or {}).get("merge", ""))
    if not m:
        return None
    return ("merged", None) if m.group(1) else ("hold", m.group(2))


def auto_merged(p) -> bool:
    return bool(p.merged) and gate_result(p) == ("merged", None)


def holds(sl) -> dict:
    """Hold count per gate condition (0-9 or call), over ADW PRs opened in the slice."""
    out = {}
    for r in map(gate_result, sl.prs("created")):
        if r and r[0] == "hold":
            out[r[1]] = out.get(r[1], 0) + 1
    return out


def reached_the_gate_or_ended(sl, p) -> bool:
    """An independent or final PR the share counts: the gate ran on it (a merge row), or it ended
    without the gate (blocked, failed or closed; §3.7 never runs on those). A sub-PR, whose base is
    its intent branch, and a PR still in flight are left out."""
    if gate_result(p):
        return True
    base = next((r.base for r in sl.facts.repos if r.name == p.repo), None)
    if p.base != base:
        return False
    return p.state != "OPEN" or bool(p.labels_now & {"adw:blocked", "adw:failed"})


@metric("outcome.auto_merged_share", "rate", 20, "ratio",
        "opened independent and final ADW PRs that were auto-merged / those the gate ran on or that ended without it "
        "(blocked, failed or closed); sub-PRs and PRs in flight are left out")
def _(sl):
    ps = [p for p in sl.prs("created") if reached_the_gate_or_ended(sl, p)]
    return ratio(sum(1 for p in ps if auto_merged(p)), len(ps)), len(ps), {}


FIX_TITLE = re.compile(r"(?i)\bfix")
FOLLOWUP_SLUG = re.compile(r"(.+)-f\d+")


def false_passes(prs: list) -> set:
    """(repo, number) of auto-merged ADW PRs that got, within FALSE_PASS_DAYS after their merge: a revert
    PR (GitHub's `Reverts <repo>#N` body, or titled `Revert "<title>"`), a non-ADW fix PR citing #N (the
    signal outcome.followup_fix_rate reads), or a `<slug>-f<k>` follow-up. A follow-up counts once,
    against the latest auto-merged PR of its slug merged before it opened."""
    auto = [p for p in prs if p.adw and auto_merged(p)]
    span = FALSE_PASS_DAYS * 86400

    def within(p, q):
        return p.repo == q.repo and ts_seconds(p.merged) < ts_seconds(q.created) <= ts_seconds(p.merged) + span

    hit = set()
    for q in prs:
        if q.adw:
            m = FOLLOWUP_SLUG.fullmatch(q.slug or "")
            got = [p for p in auto if m and p.slug == m.group(1) and within(p, q)]
            if got:
                p = max(got, key=lambda p: ts_seconds(p.merged))
                hit.add((p.repo, p.number))
            continue
        for p in auto:
            if not within(p, q):
                continue
            if q.title.startswith('Revert "'):
                if q.title == f'Revert "{p.title}"' or re.search(rf"(?m)^Reverts \S*#{p.number}\b", q.body):
                    hit.add((p.repo, p.number))
            elif FIX_TITLE.search(q.title) and re.search(rf"(?<![\w/])#{p.number}\b", q.title + "\n" + q.body):
                hit.add((p.repo, p.number))
    return hit


@metric("outcome.auto_merge_false_pass", "rate", 20, "ratio",
        f"auto-merged ADW PRs with a revert PR, a non-ADW fix PR citing #N, or a <slug>-f<k> follow-up (counted once, "
        f"against the latest auto-merged PR of its slug) within {FALSE_PASS_DAYS} days / auto-merged ADW PRs, merged in "
        f"the window and at least {FALSE_PASS_DAYS} days before the run date")
def _(sl):
    limit = ts_seconds(sl.facts.until) - FALSE_PASS_DAYS * 86400
    auto = [p for p in sl.prs("merged") if auto_merged(p) and ts_seconds(p.merged) <= limit]
    hit = false_passes(sl.facts.prs)
    return ratio(sum(1 for p in auto if (p.repo, p.number) in hit), len(auto)), len(auto), {}


# --- evidence block --------------------------------------------------------------------------------

@metric("evidence.block_missing_rate", "rate", 20, "ratio", "opened ADW PRs with no evidence block")
def _(sl):
    opened = sl.prs("created")
    return ratio(sum(1 for p in opened if not p.block), len(opened)), len(opened), {}


def coverage(row):
    def fn(sl):
        blocks = [p.block for p in sl.prs("created") if p.block]
        return ratio(sum(1 for b in blocks if row in b), len(blocks)), len(blocks), {}
    return fn


for _row in ROWS:
    metric(f"evidence.coverage.{_row}", "rate", 20, "ratio", f"evidence blocks carrying the {_row} row")(coverage(_row))


@metric("evidence.review0_with_fixreview_rate", "rate", 20, "ratio",
        "review 0/N rows on PRs with fix(review): commits / parsed review rows")
def _(sl):
    parsed = [(p, cycles(p.block.get("cycles"))) for p in sl.prs("created") if p.block]
    parsed = [(p, c) for p, c in parsed if c["review"] is not None]
    bad = sum(1 for p, c in parsed if c["review"] == 0 and p.review_fix_commits > 0)
    return ratio(bad, len(parsed)), len(parsed), {}


@metric("evidence.never_edited_rate", "rate", 20, "ratio", "evidence blocks on PRs never edited after opening")
def _(sl):
    with_block = [p for p in sl.prs("created") if p.block]
    never = sum(1 for p in with_block if not p.last_edited or p.last_edited == p.created)
    return ratio(never, len(with_block)), len(with_block), {}


# --- friction --------------------------------------------------------------------------------------

def per_1k(sl, attr):
    ss = sl.sessions()
    calls = sum(sum(s.tool_calls.values()) for s in ss)
    bd = {}
    for s in ss:
        for k, v in getattr(s, attr).items():
            bd[k] = bd.get(k, 0) + v
    total = sum(bd.values())
    return ratio(total * 1000, calls), calls, {k: v * 1000 / calls for k, v in bd.items()} if calls else {}


@metric("friction.denials_per_1k_calls", "rate", 1000, "per1k", "permission denials per 1,000 tool calls, by source")
def _(sl):
    return per_1k(sl, "denials")


@metric("friction.tool_errors_per_1k_calls", "rate", 1000, "per1k", "tool errors per 1,000 tool calls, by tool")
def _(sl):
    return per_1k(sl, "tool_errors")


def compactions(kind):
    def fn(sl):
        ms = mains(sl)
        return sum(1 for s in ms for _, k in s.compactions if k == kind), len(ms), {}
    return fn


for _kind in ("limit", "idle", "manual"):
    metric(f"friction.compactions_{_kind}", "count", 1, "count", f"{_kind} compactions on main threads")(compactions(_kind))


@metric("friction.limit_compactions_per_intent", "ratio", 8, "count", "context-limit compactions on intents' main threads / intents")
def _(sl):
    its = sl.intents()
    return ratio(sum(1 for i in its for s in i.mains for _, k in s.compactions if k == "limit"), len(its)), len(its), {}


@metric("friction.subagents_over_250k_rate", "rate", 50, "ratio", f"subagents whose context peaked over {PEAK:,} tokens")
def _(sl):
    subs = [s for s in sl.sessions() if not s.is_main]
    over = sum(1 for s in subs if s.peak_context > PEAK)
    return ratio(over, len(subs)), len(subs), {"count": over}


# --- time ------------------------------------------------------------------------------------------

@metric("time.intent_lead_hours_median", "median", 8, "hours", "first human prompt → last merge, intents whose last PR merged in the window")
def _(sl):
    xs = [i.lead_h for i in sl.intents() if i.lead_h is not None]
    return median(xs), len(xs), {}


@metric("time.intent_lead_hours_p90", "quantile", 8, "hours", "p90 of the same")
def _(sl):
    xs = [i.lead_h for i in sl.intents() if i.lead_h is not None]
    return p90(xs), len(xs), {}


def gate_hours(sl):
    bd = {}
    for s in sl.sessions():
        for g, _, sec in s.gate_calls:
            bd[g] = bd.get(g, 0.0) + sec / 3600
    return bd


@metric("time.gate_fg_hours", "total", 1, "hours", "foreground gate wall time (background runs are NOT MEASURED), by gate")
def _(sl):
    bd = gate_hours(sl)
    return sum(bd.values()), len(sl.sessions()), bd


@metric("time.gate_fg_hours_per_merged_pr", "ratio", 10, "hours", "foreground gate hours / merged ADW PRs")
def _(sl):
    merged = sl.prs("merged")
    return ratio(sum(gate_hours(sl).values()), len(merged)), len(merged), {}


# --- design §8 and §9 inputs -----------------------------------------------------------------------

def cycle_rows(sl):
    return [cycles(p.block.get("cycles")) for p in sl.prs("created") if p.block and p.block.get("cycles")]


def progress(bucket):
    def fn(sl):
        cs = [c for c in cycle_rows(sl) if c["progress"] is not None]
        return sum(1 for c in cs if c["progress"] == bucket), len(cs), {}
    return fn


metric("design.progress_fired", "count", 1, "count", "progress-conditions rows that fired (design §8: read only this bucket)")(progress("fired"))
metric("design.progress_not_consumed", "count", 1, "count", "progress-conditions rows evaluated and not consumed")(progress("not consumed"))


@metric("design.instrumented_units", "count", 1, "count", "ADW PRs whose cycles row carries progress-conditions")
def _(sl):
    cs = cycle_rows(sl)
    return sum(1 for c in cs if c["progress"] is not None), len(cs), {}


def cap(which):
    def fn(sl):
        cs = [c for c in cycle_rows(sl) if c[which] is not None]
        return sum(1 for c in cs if c[which] == c[which + "_cap"]), len(cs), {}
    return fn


metric("design.fix_cap_reached", "count", 1, "count", "cycles rows with fix N == cap")(cap("fix"))
metric("design.review_cap_reached", "count", 1, "count", "cycles rows with review N == cap")(cap("review"))


def open_bf(sl):
    return [p for p in sl.facts.open_prs if p.adw and p.labels_now & {"adw:blocked", "adw:failed"}]


@metric("design.open_blocked_failed", "count", 1, "count", "open ADW PRs labelled adw:blocked or adw:failed, as of the window end (design §8: over 5 kills)")
def _(sl):
    if not sl.is_current:
        return None, 0, {}
    return len(open_bf(sl)), len(sl.facts.open_prs) or 1, {}


@metric("design.oldest_blocked_failed_days", "count", 1, "days", "age in days of the oldest of them (design §8: over 7 kills)")
def _(sl):
    if not sl.is_current:
        return None, 0, {}
    ps = open_bf(sl)
    end = ts_seconds(sl.facts.until)
    return (int(max((end - ts_seconds(p.created)) / 86400 for p in ps)) if ps else 0), len(sl.facts.open_prs) or 1, {}


# --- the loop --------------------------------------------------------------------------------------

def kinds(sl, pr):
    return {getattr(x, "kind", None) for x in sl.facts.predict_lines.get(pr.number, [])}


@metric("loop.contract_prs_merged", "count", 1, "count", "adw PRs merged that touch commands/ or scripts/")
def _(sl):
    n = len(sl.contract_prs())
    return n, n or 1, {}


@metric("loop.contract_prs_with_predicts", "count", 1, "count", "of those, with at least one valid predicts line")
def _(sl):
    ps = sl.contract_prs()
    return sum(1 for p in ps if "prediction" in kinds(sl, p)), len(ps) or 1, {}


@metric("loop.contract_prs_predicts_none", "count", 1, "count", "of those, with only predicts none")
def _(sl):
    ps = sl.contract_prs()
    return sum(1 for p in ps if kinds(sl, p) == {"none"}), len(ps) or 1, {}


@metric("loop.predicts_rejected", "count", 1, "count", "predicts lines the reader rejected")
def _(sl):
    ps = sl.contract_prs()
    return sum(1 for p in ps for x in sl.facts.predict_lines.get(p.number, []) if getattr(x, "kind", None) == "rejected"), len(ps) or 1, {}


def uncovered(sl) -> list:
    """Contract PRs merged in the slice with no predicts line at all: what loop.predicts_coverage misses."""
    return [p for p in sl.contract_prs() if not kinds(sl, p) & {"prediction", "none"}]


@metric("loop.predicts_coverage", "ratio", 3, "ratio", "contract PRs with any predicts line (a prediction or none) / contract PRs merged")
def _(sl):
    ps = sl.contract_prs()
    return ratio(len(ps) - len(uncovered(sl)), len(ps)), len(ps), {}
