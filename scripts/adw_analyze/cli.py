"""Flags, run order and exit codes. 0 ok · 1 a source cannot be read · 2 bad flag, config or existing
dated folder · 3 the reports dir is in a public or unverifiable GitHub checkout · 4 --scan found a hit."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone

from . import config
from .facts import Slice, build_facts
from .github import SourceError
from .metrics import REGISTRY, compute
from .predicts import read_predictions
from .report import Run, write_outputs
from .github import fetch_prs
from .verdicts import baseline_start, git_is_after, git_path_exists, git_watch_changed, judge, read_records
from .transcripts import ts_seconds

RETENTION_DAYS = 90  # cleanupPeriodDays (spec §5.6): nothing older exists to read


def parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="adw-analyze.py", description="Measure ADW runs and judge predicts lines.")
    p.add_argument("--reports", help="the private reports checkout (default: $ADW_ANALYSIS_DIR)")
    p.add_argument("--until", help="window end, YYYY-MM-DD UTC (default: now)")
    p.add_argument("--days", type=int, default=28, help="window length in days (default 28)")
    p.add_argument("--projects", default="~/.claude/projects", help="Claude Code transcripts dir")
    p.add_argument("--adw", help="adw checkout used for contract-sha ancestry (default: the contract repo's checkout)")
    p.add_argument("--scan", action="store_true", help="leak-scan the dated folder named by --date")
    p.add_argument("--date", help="with --scan: the dated folder to scan")
    p.add_argument("--check-config", action="store_true", help="stop after the guard and sources.json")
    return p.parse_args(argv)


def fail(code: int, msg: str) -> int:
    print(f"adw-analyze: {msg}", file=sys.stderr)
    return code


def stamp(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: list[str] | None = None) -> int:
    args = parse(sys.argv[1:] if argv is None else argv)
    try:
        reports = config.resolve_reports_dir(args.reports)
        config.check_reports_dir(reports)
        repos = config.load_sources(reports)
    except config.ConfigError as e:
        return fail(2, str(e))
    except config.PublicRepoError as e:
        return fail(3, str(e))
    if args.check_config:
        return 0
    if args.scan:
        from .scan import run_scan
        return run_scan(reports, repos, args)
    return analyze(reports, repos, args)


def analyze(reports: str, repos: list, args) -> int:
    if args.until:
        try:
            end = datetime.strptime(args.until, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return fail(2, f"--until must be YYYY-MM-DD, got {args.until}")
    else:
        end = datetime.now(timezone.utc).replace(microsecond=0)
    until = stamp(end)
    out = os.path.join(reports, until[:10])
    if os.path.exists(out):
        return fail(2, f"{out} exists; a dated report is never rewritten")
    contract = next((r for r in repos if r.role == "contract"), None)
    adw_dir = args.adw or (contract.checkout if contract else None)
    if not adw_dir or not os.path.isdir(adw_dir):
        return fail(2, "name the adw checkout with --adw or a contract repo checkout in sources.json")
    window = (stamp(end - timedelta(days=args.days)), until)
    prior = (stamp(end - timedelta(days=2 * args.days)), window[0])
    exists, is_after = git_path_exists(adw_dir), git_is_after(adw_dir)
    app_names = {r.name for r in repos if r.role == "app"}
    try:
        early = [x for r in repos if r.role == "contract" for p in fetch_prs(r, None)
                 for x in read_predictions(p, exists, app_names) if x.kind == "prediction"]
        facts = build_facts(repos, args.projects, until, lookback_since(until, args.days, early))
    except SourceError as e:
        return fail(1, str(e))
    lines = {p.number: read_predictions(p, exists, app_names) for p in facts.prs if facts.role_of(p.repo) == "contract"}
    facts.predict_lines = lines
    predictions = [x for xs in lines.values() for x in xs if x.kind == "prediction"]
    rejected = [x for xs in lines.values() for x in xs if x.kind == "rejected"]
    watch = git_watch_changed(repos)
    run = Run(until=until, window=window, prior=prior, facts=facts,
              win={m: compute(m, Slice(facts, *window)) for m in REGISTRY},
              pri={m: compute(m, Slice(facts, *prior)) for m in REGISTRY},
              predictions=predictions, verdicts=[judge(p, facts, predictions, is_after, watch) for p in predictions],
              records=read_records(reports), rejected=rejected, legacy=load_legacy(reports),
              sources_hash=sources_hash(reports))
    tmp = os.path.join(reports, f".{until[:10]}.tmp")
    shutil.rmtree(tmp, ignore_errors=True)
    try:
        write_outputs(tmp, run)
        os.rename(tmp, out)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print(out)
    return 0


def lookback_since(until: str, days: int, predictions: list) -> str:
    """Read back to the prior window and to every prediction's baseline start, never past retention."""
    end = ts_seconds(until)
    want = min([end - 2 * days * 86400] + [ts_seconds(baseline_start(p)) for p in predictions])
    floor = end - RETENTION_DAYS * 86400
    return stamp(datetime.fromtimestamp(max(want, floor), timezone.utc))


def load_legacy(reports: str) -> list:
    path = os.path.join(reports, "legacy-verdicts.json")
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def sources_hash(reports: str) -> str:
    with open(os.path.join(reports, "sources.json"), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:12]
