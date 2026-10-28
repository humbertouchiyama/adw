---
name: adw-analyze
description: Use when the owner asks to run the ADW run analysis now, check whether a contract fix worked, or see the latest verdicts on predicts lines — runs the weekly report by hand in the private reports repo.
---

# ADW analysis, by hand

The weekly launchd job runs this every Monday. Run it by hand when the owner asks for a report now.

1. From this repo, run `bash scripts/adw-analyze-weekly.sh run`. It refreshes a dedicated adw
   worktree to `origin/main`, runs `scripts/adw-analyze.py`, the critical pass, the leak scan, commits
   the dated folder to the private reports repo (`$ADW_ANALYSIS_DIR`), pushes, and opens an issue there.
   A second run on the same UTC date stops at the reader step and opens a "failed at reader" issue:
   a dated report is never rewritten.
2. Read `$ADW_ANALYSIS_DIR/<date>/report.md`. Show the owner the issue URL, the `## Verdicts` and
   `## Delete candidates` sections, and the critical pass findings.
3. A failed verdict is listed, never acted on here. Deleting the fix is a contract PR the owner
   approves (`reviewing-contract-prs`).

This repo is public; the reports repo is private. Never copy report lines, spend, app-repo PR numbers
or local paths into a commit, PR or issue in this repo.

To change what is measured, change `scripts/adw_analyze/metrics.py` and give the metric a new
version suffix (`.v2`): a definition change is a new id, so old verdicts stay comparable.
