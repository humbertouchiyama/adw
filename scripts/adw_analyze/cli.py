"""Flags, run order and exit codes. 0 ok · 1 a source cannot be read · 2 bad flag, config or existing
dated folder · 3 the reports dir is in a public or unverifiable GitHub checkout · 4 --scan found a hit."""
from __future__ import annotations

import argparse
import sys

from . import config


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


def main(argv: list[str] | None = None) -> int:
    args = parse(sys.argv[1:] if argv is None else argv)
    try:
        reports = config.resolve_reports_dir(args.reports)
        config.check_reports_dir(reports)
        config.load_sources(reports)
    except config.ConfigError as e:
        return fail(2, str(e))
    except config.PublicRepoError as e:
        return fail(3, str(e))
    if args.check_config:
        return 0
    return 0
