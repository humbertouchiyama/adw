# ADW self-improving loop — measure, predict, check, delete

Status: design, approved by the owner on 2026-10-27 after one critical review; §5.6 decided
2026-10-28. Date: 2026-10-27.

## 1. Problem

The owner improves the ADW contract from periodic run analyses. Three read-only recon passes
over adw and the two app repos that run it (sessions, PRs, the 2026-10-01 and 2026-10-22 analyses)
show:

- **The analysis is cheap; everything around it is not.** The 10-22 analysis took 24 min; the 10-01
  one 20 min. The days go elsewhere: the owner starts each one by hand
  (12 and 21 days apart), carries baselines from memory notes, and asks for a separate critical
  pass (17.5 h after the 10-22 report).
- **Nothing survives.** About 50 and 57 throwaway scripts per analysis lived in session
  scratchpads. The 10-22 reports were deleted and had to be recovered from transcripts. The
  only surviving reader, `scripts/adw-metrics.sh`, lives in an app repo, reads one evidence
  row, and is stale against today's bodies.
- **Numbers change between analyses.** Spend for the same window was restated by 15%
  (price table, output tokens, denominator). Owner wait at 68% of run time reproduces only
  with an unstated 12 h gap cap. Intent agent time 21 h → 7 h (parallel intents mixed). The
  10-22 "auto-compactions 7 → 65" is mostly the idle-compaction feature: 74 of 80
  main-thread auto compactions in one app repo are idle ones.
- **Shipped fixes are rarely judged against a stated target.** Of about 15 checked changes, at
  most three had a target set before shipping: #9 and #16 in their PRs, #5 in its session. Lanes
  disagreed on #12's items. No fix measured as failing was ever deleted: #15's enforcer drafts
  and #12's handoff decide pass are still on main.
- **The PR evidence block cannot be trusted alone.** In one app repo 70 of 403 blocks were never edited
  after the PR opened, and 20 of 71 `review 0/2` rows sit on PRs with `fix(review):` commits.
  In the other, 54 of 317. `owner-wait` counts only halts inside a PR's own loop, so `0m` is often
  right, yet 22 of 219 PRs in the first repo show over 30 min of owner gaps inside their build window.
- **Transcripts expired after 30 days.** Three weeks of one app repo (182 PRs) have none. Retention is now 90
  days (`cleanupPeriodDays` in the owner's user settings, 2026-10-28); see §5.6.

## 2. Goal

A loop the system runs, not the owner: **measure → predict → check → delete.** Success means:

- One command produces the full analysis. No baseline is carried by hand.
- The same code re-measures the previous window, so two reports compare number to number.
- Every contract PR merged after this lands states a prediction, and each prediction gets a
  verdict of record in the first report after its deadline.
- A failed verdict ends in a deletion the owner approves. **v1 lists it; v2 opens the PR**
  (§5.4).
- A dead loop is noticed within 10 days, without the owner looking.

## 3. Non-goals and anti-goals

- **No self-editing contract.** The agent never changes the contract on its own. Every change
  is a PR the owner merges. (Harness² lets the agent edit its harness mid-run; this design
  deliberately does not.)
- **No A/B re-runs of old tasks.** One ADW run costs from a few dollars to several hundred, and hours; has human gates and
  opens real PRs; n=1 per arm is noise.
- **No run database** in the §5.1 sense: no state a person maintains. See §4.
- Out of scope, separate PRs that consume this tool's output: hooks (the evidence-block check,
  the post-compaction re-read) and deleting today's known-failed fixes.
- **Anti-goal:** numbers people argue over. A disputed definition is fixed in the code and the
  old window is re-measured, never patched in a note.

## 4. Owner decisions (2026-10-27)

- **Reports are committed, dated files in a private repo.** adw is public; the app repos
  are private, and a report carries their spend, PR numbers and local paths. So
  the reports, the sources config and the legacy seed live in a new private repo (the owner's
  private reports repo), and the reader code stays in adw. Design §5.1 forbids a run
  database because files a person must keep current go stale and then mislead. A dated snapshot
  the reader writes and nobody edits does not have that failure. §5.1 gets that exception in
  writing (§7).
- **No database.** ADW's live run state stays in git, PR bodies and labels. A local SQLite cache
  of per-session facts is deferred until runs get slow or data older than 90 days is needed.
- **Transcripts are kept 90 days** (2026-10-28; §5.6).
- Contract changes stay human-approved (§3).

## 5. Parts

### 5.1 The reader — `scripts/adw-analyze.py`

Computes everything; stores nothing except its two output files.

**Sources**, listed in `sources.json` at the root of the private reports repo: per repo, the
GitHub slug, the local checkout path, the transcript directory globs under
`~/.claude/projects/` (the main dir plus `--claude-worktrees-*` dirs, and each session's
`subagents/` folder), and the repo's **watch paths** (its repo-profile and gate scripts; §5.3
uses them). Today: adw and two app repos. The
reader finds the reports repo through `--reports <path>` or `ADW_ANALYSIS_DIR`, and refuses to
write inside a checkout whose GitHub repo is public.

**Trust order.** git and gh facts first, transcript facts second, PR-body self-report last.
Every self-reported field the report uses is printed with its mismatch rate against the
first two.

**Window.** A trailing 28-day window ending at `--until` (default: now). The run is weekly, so
consecutive windows overlap; weekly samples are too small to compare. Every run also
re-measures the 28 days before its window with the same code and prints both. *(Designer's
call.)*

**Rules learned from recon, all mandatory:**

| Rule | Why |
|---|---|
| Dedupe `message.usage` by `message.id`; price from one dated table in the code; 5-minute and 1-hour cache writes priced separately | the 15% spend restatement |
| Never use the harness `cost-state` record as cost | resets per process, up to 18 per file, ratio 0.72–1.61 to usage |
| Split compactions into context-limit and idle (a `Compacted while idle` notice within 10 s of the boundary) | the 7 → 65 misreading |
| Time sessions from user and assistant records only | a "Remote Control disconnected" record is stamped into every open session |
| Owner-wait gaps capped at 12 h, and the cap printed | the unstated cap |
| Attribute a session to an intent by branch or worktree strings, longest slug first, top slug only at ≥20 hits and ≥3× the runner-up; attribute a subagent by the worktree in its dispatching prompt, joined through `toolUseId` in its `.meta.json`; use harness `pr-link` records as the session anchor, minus the release PR of the starting branch | a lead time tripled by mixing parallel intents; one slug is a prefix of four others |
| A final PR inherits its units' commits: count its cycles after excluding the inherited `[adw …]` squash commits | double counting, without losing the final PR's own review loop |
| Find the evidence block by its `contract <sha>` row wherever it sits (fenced, unfenced, inside `<details>`); keep the raw string; parse numbers by regex | 233 shapes of the `gates` row; Portuguese notes |
| A `review N/2` row is checked against `fix(review):` commits, never against the presence of a review comment | a clean review posts a comment too (design §5.1) |
| A missing block or field is `no data`, never `0` | design §5.1 already says so |
| Background gate runs have no completion record for most subagents: report foreground gate time only, and list background gate time under NOT MEASURED | 116 of 538 found |
| Leave the analyzer's own sessions (cwd in the adw or reports checkout, or a run of the `adw-analyze` skill) out of every total and of the leak scan | it reads transcripts and would count and match itself |

**Metric set (schema v1).** Each metric has a stable, versioned id, a written definition, a
source, a minimum sample, and a **`predictable`** flag. Only rates, ratios and medians are
predictable; counts and totals (total $, PRs opened, prompts) move with how much work happened
and are reported but cannot be predicted. The builder fixes the exact ids; the set is:

- *Cost:* total $, by repo, main vs subagents, by model; $ per merged ADW PR; $ per intent
  (median, p90); Opus orchestrator share of spend.
- *Owner:* human prompts; interrupts; owner-wait hours (capped) per intent; halts while a PR was
  open.
- *Outcomes:* ADW PRs opened, merged, closed; ever-blocked %; `failed` %; fix cycles from
  `fix-attempt-N` commits; review rounds from `fix(review):` commits; reverts; follow-up fix
  PRs that name an earlier ADW PR (finals listing their own sub-PRs excluded).
- *Evidence block:* coverage per row; mismatch rates (`review 0/2` vs `fix(review):` commits,
  never edited after open).
- *Friction:* permission denials per 1,000 tool calls, by source (structured
  `permissionDecision` plus the known text markers); tool errors per 1,000 calls by tool;
  compactions by kind; subagents peaking over 250k context.
- *Time:* intent lead time (first intent message → last merge), median and p90; foreground
  gate wall time by gate.
- *Design §8 and §9 inputs* (today read from `adw-metrics.sh`; no kill criterion may be
  dropped): progress-conditions `fired` vs `evaluated-not-consumed`; how often the fix cap and
  the review cap were reached; open `blocked` + `failed` PRs, their count and the oldest one's
  age. *(Designer's call.)*
- *The loop itself:* contract PRs merged in the window, how many carry a `predicts` line, how
  many say `none`, and how many lines the reader rejected.
- **NOT MEASURED**, printed every time: background gate time, owner-found device defects,
  escape rate, base-red truth on a repo with no CI, and any window before transcripts exist.

**Output.** `<reports repo>/<until-date>/report.md` (human) and `metrics.json` (aggregates,
schema version, window, price table, sources config hash, every `predicts` line read and the
verdicts computed). **Aggregates and PR numbers only: no transcript text, prompt text,
command text or file content ever reaches either file.** Transcripts have held a private key
twice.

### 5.2 The prediction line

Every adw PR that changes `commands/` or `scripts/` carries, in its body, one or more lines:

```
predicts  <metric-id> <direction> <amount> by <YYYY-MM-DD> for <file>[ §<section>] [repo <name>]
predicts  none — <reason>
```

`<direction>` is `down` or `up`; `<amount>` is a change against the baseline, either relative
(`20%`) or absolute in the metric's unit (`0.5`), or the word `to-zero`. Predictions are always
against the baseline, so a fix that changed nothing cannot pass because the baseline already
met a threshold. *(Designer's call, from the critical review.)*

`for` names the text the prediction covers, so a PR that bundles several fixes (#12 carried 16)
gets one line per fix, and a deletion removes only the fix that failed. The reader rejects an
unknown or non-predictable metric id, a `for` path that does not exist at the merge commit, or a
`by` date more than 49 days after the merge (§5.6), and counts the rejection (§5.1), so a typo surfaces at the next report. The rule lives in the
`reviewing-contract-prs` skill (its lane C question) and in a short "Changing the contract"
section added to README. A hook that enforces it belongs with the other hooks (§3).

**Legacy verdicts.** The 10-22 analysis already judged two fixes failed: #12's handoff decide
pass and #15's enforcer drafts. They sit in a small seed file in the reports repo and print in
every report under their own heading, **for information only**: no metric to re-judge, and no
deletion from them. Deleting them is the separate PR named in §3, done by a person.
Orchestrator-on-Sonnet is listed as "failed for a cause outside the contract": the 10-22
analysis traced it to the saved `/model opus` default overriding the rule, and the cost data
still supports the rule. *(Designer's call.)*

### 5.3 Verdicts

For each `predicts` line on a merged PR:

- **Before and after are split by contract version, not by clock.** An ADW run reads the
  contract once, at its start, and 17 intents ran 20 h or more, so wall-clock spans put runs on
  the wrong side of a merge. Each ADW PR records `contract <sha>`; it counts as *after* when the
  predicting PR's merge commit is an ancestor of that sha (`git merge-base --is-ancestor`), and
  *before* otherwise. Transcript-only metrics with no PR to carry a sha use the session's first
  `fetch.sh` result when present, else the clock. *(Designer's call, from the critical review.)*
- **Spans.** *After* is from the merge to the deadline. *Baseline* is the same length just
  before the merge, capped at 28 days.
- **Verdicts:**
  - **too early** — the deadline is ahead. The report shows the running value.
  - **worked** — at the deadline, the metric moved in the predicted direction by at least the
    predicted amount against the baseline, with at least the minimum sample on both sides.
  - **failed** — at the deadline, it did not, with at least the minimum sample on both sides.
  - **confounded** — another `predicts` line on the same metric and repo overlaps the span, or
    one of the repo's watch paths (§5.1) changed inside it. Printed with the cause; never a
    delete candidate. (An app-repo PR cut one gate from 17 to 3.75 min; a contract fix would have been
    credited with it.)
  - **no data** — the metric cannot be computed, or the sample is below the minimum.
- **Verdict of record.** The first committed `metrics.json` after the deadline records the
  verdict, and the `predicts` lines as read at that time. Later reports read that record and
  print it; if their own recompute differs (a definition fix, a price change, an edited PR
  body), they print the new value as **restated**, next to the record, and never replace it.
  Metric ids are versioned, so a definition change is a new id. *(Designer's call, from the
  critical review.)*

A later regression of a rule that worked is not a verdict: it shows as the metric moving between
windows, and the critical pass (§5.4) flags it.

### 5.4 The command — the `adw-analyze` skill

What the owner runs by hand, and what the weekly job runs (§5.5):

1. Run the reader; fail loudly on a source it cannot read.
2. **Critical pass** by a fresh subagent that gets the report and the raw local data, never the
   reader's reasoning. It challenges each number that moved more than 25% between the two
   windows, and every verdict. Its findings go into the report under their own heading. (The
   owner asked for this by hand every time.) **Its findings cite only metric ids, PR numbers and
   session ids: never a quote from a transcript, a prompt or a command.**
3. **Leak scan** of the final `report.md` and `metrics.json`: key and token patterns, plus no
   line of 40 characters or more that also appears in a scanned transcript. A hit stops the
   run before anything is committed. The scan is the reader's own `--scan` mode, so the §8 leak
   test covers it.
4. Commit the dated report to the reports repo's `main` and push. No report PR: an unmerged one
   would make the next run re-measure the same window, and nobody edits a report. *(Designer's
   call, from the critical review.)*
5. Open one issue in the reports repo with the report's top lines (verdicts reached, metrics
   that moved most, delete candidates, leak-scan result), so the owner is notified on GitHub.
6. **Delete candidates (v1).** Each **failed** verdict is listed with its predicting PR, its
   `for` text and the metric. The owner decides.

**Deletion PRs (v2).** Opening the deletion PR automatically is deferred: no `predicts` line
exists yet, so no verdict can arrive for weeks, and the step carries most of the risk. When it
is built it must: open the PR only from the verdict of record, keyed by a branch name, and skip
if a PR with that head exists in any state; fill the body from a fixed template the script
writes; run the leak scan plus a denylist (private PR numbers, `/Users/`, `$` values) over the
body and the diff before `gh pr create`; and run the `reviewing-contract-prs` review in the
main session after the PR exists, as that skill requires.

### 5.5 Schedule and the dead-man check

Transcripts are local files, so a cloud routine cannot read them. The run is local.

- **A shell wrapper, `scripts/adw-analyze-weekly.sh`, does every deterministic step:** set
  `PATH` to include `/opt/homebrew/bin` (launchd's does not), refresh a dedicated adw worktree
  to `origin/main`, pull the reports repo, run the reader, run the leak scan, commit and push,
  open the issue. No model is needed for any of it.
- **Only the critical pass uses a model:** `claude -p` with `--model sonnet` and an explicit
  `--allowedTools` list (reads, the reader's own commands, and writing the findings file). It
  never pushes or opens anything. The wrapper checks that the findings section exists and
  otherwise marks the report `critical pass: missing` and still commits it. *(Designer's call,
  from the critical review: an unattended `claude -p` cannot answer a prompt, so a denied push
  would fail silently.)*
- **launchd** runs the wrapper weekly, installed and removed by `--install` / `--uninstall`.
  The install is proven once with `launchctl kickstart` before it counts as done.
- **Dead-man check.** A GitHub Actions cron in the reports repo opens an issue when `main` has
  no report newer than 10 days. It runs in the cloud and needs nothing from the machine.

**Where it runs.** Only in adw. The command is a project skill, `.claude/skills/adw-analyze/`,
next to `reviewing-contract-prs`. It gets no loader stub: a stub would install it into every
consuming repo, where the only adw copy is the read-only fetch cache. *(Designer's call.)*

### 5.6 Transcript retention — 90 days (owner decision, 2026-10-28)

Measured 2026-10-28: about 42 GB free; transcripts take 6.1 GB, which is the last 30 days, and new
sessions add 1.0 to 1.8 GB a week (mean 1.35). At 90 days the folder levels off near 17 GB. A
year of raw transcripts would be about 70 GB and fill the disk in about seven months; gzip
shrinks them only 2.8×, so an archive was dropped.

90 days covers everything the reader needs: the window and the prior window (56 days), and every
verdict, because the reader rejects a `by` date more than 49 days after the merge (§5.2): a
28-day baseline plus 49 days is 77 days, which leaves room for a late run. Older numbers live on
in the committed `metrics.json` files. A restatement (§5.3) whose data has expired prints
`no data` and keeps the record.

## 6. Files

| Path | Change |
|---|---|
| `scripts/adw-analyze.py` | New. The reader (§5.1, §5.3) and its `--scan` mode (§5.4). |
| `scripts/test_adw_analyze.py` | New. Fixture transcripts and a fake `gh`, in the style of `test_adw_run_clean.py`. |
| `scripts/adw-analyze-weekly.sh` | New. The wrapper and its `--install` / `--uninstall` (§5.5). |
| `.claude/skills/adw-analyze/SKILL.md` | New. The command (§5.4). No loader stub. |
| Private repo `adw-analysis` | New. `sources.json`, the legacy seed, `<date>/` written by each run, and `.github/workflows/stale-report.yml` (the dead-man check). Created once, with the owner's go-ahead. |
| `docs/00-design.md` §5.1, §8, §9 | The reader row replaces `adw-metrics.sh`; the dated-snapshot exception (§7); §8 and §9 cite the new reader. |
| `.claude/skills/reviewing-contract-prs/SKILL.md` | The `predicts` rule in lane C's question. |
| `README.md` | Rows for the skill and the two scripts; a short "Changing the contract" section with the `predicts` rule. |

## 7. Design-doc amendment (text to add to §5.1)

> Dated analysis snapshots in the private reports repo are written by `scripts/adw-analyze.py`
> and never edited. They are the reader's output, not run state: nothing in them needs a person
> to keep it current, and a later run supersedes rather than updates them.

## 8. Testing

- Unit tests on fixtures for each rule in §5.1's table, plus: unknown and non-predictable
  metric ids rejected; a `by` date beyond 49 days rejected; the contract-sha split (a run that started before a merge and finished
  after it counts as before); `confounded` on an overlapping prediction and on a watch-path
  change; verdict boundaries (deadline today, sample one below the minimum on either side);
  verdict of record vs restated; `no data` vs `0`.
- **A leak test:** fixture transcripts carry a fake key and a marker line; the test fails if
  either reaches `report.md` or `metrics.json`, and `--scan` must catch both when planted.
- **Golden run:** run on the real 10-02..10-21 window and compare to the 10-22 analysis. Every
  gap over 10% is explained in the first report as a restatement with its cause.
- **Dry run** of the wrapper end to end against a scratch reports repo before the PR, then one
  `launchctl kickstart` of the installed job.

## 9. Left to the builder

Metric ids and their exact names, module layout inside the script, the report's layout, the
`launchd` day and time, and the minimum sample per metric (stated in the schema, defended in
one line each).

## 10. Risks

- **Transcript format drift.** The reader counts unknown record types and prints the count; a
  jump means a parser to fix, not a behaviour change.
- **Goodhart.** A prediction can name an easy metric. The critical pass judges whether the
  metric measures what the PR claimed to fix.
- **Unattended actions.** The weekly job pushes a report and opens an issue in the private
  repo. It never touches adw or an app repo, and never merges anything.
- **Private data in public adw.** adw is public. Only metric ids, amounts and verdicts may reach
  it (`predicts` lines). The reader's refusal to write into a public checkout and the leak scan
  are the two guards.
- **Disk.** 90-day retention levels off near 17 GB (§5.6).
