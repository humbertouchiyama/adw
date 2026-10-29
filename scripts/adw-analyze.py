#!/usr/bin/env python3
"""Measure ADW runs, judge each contract PR's predicts line, write a dated report (spec
docs/specs/2026-10-27-adw-self-improving-loop-design.md). The code is the adw_analyze package next
to this file; see adw_analyze/cli.py for flags and exit codes."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adw_analyze.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
