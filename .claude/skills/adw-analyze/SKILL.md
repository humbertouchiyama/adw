---
name: adw-analyze
description: Use when the owner asks to run the ADW run analysis now, check whether a contract fix worked, or see the latest verdicts on predicts lines — runs the weekly report by hand in the private reports repo.
---

# ADW analysis, by hand

The weekly launchd job runs this every Monday. Run it by hand when the owner asks for a report now.

1. From this repo, run `bash scripts/adw-analyze-weekly.sh run` in the background and wait for it
   to exit: the critical pass alone may take 30 minutes, longer than a foreground command may run.
   It refreshes a dedicated adw worktree to `origin/main`, runs `scripts/adw-analyze.py`, the
   critical pass, the leak scan, commits
   the dated folder to the private reports repo (`$ADW_ANALYSIS_DIR`), pushes, and opens an issue there.
   A second run on the same UTC date stops at the reader step and opens a "failed at reader" issue:
   a dated report is never rewritten. A dry run's folder is not a report: the next run replaces it.
2. Read the file on the `report:` line that step 1 prints. Show the owner the issue URL, the
   `## Verdicts` and `## Delete candidates` sections, and the critical pass findings.
3. A failed verdict is listed, never acted on here. Deleting the fix is a contract PR the owner
   approves (`reviewing-contract-prs`).

This repo is public; the reports repo is private. Never copy report lines, spend, app-repo PR numbers
or local paths into a commit, PR or issue in this repo.

To change what is measured, add the new definition to `scripts/adw_analyze/metrics.py` as a second
`@metric(...)` with the same name and the next `version=` (`version=2` makes the id end in `.v2`):
a definition change is a new id, so old verdicts stay comparable. Keep the old one registered until
every `predicts` line that names it has a verdict of record: a line naming an id that is gone is
rejected as an unknown metric and never judged.
