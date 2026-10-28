# adw self-improving loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A reader that measures ADW runs the same way every time, judges each contract PR's
`predicts` line against a baseline, and commits a dated report to a private repo every week
without the owner starting it.

**Architecture:** One stdlib Python package, `scripts/adw_analyze/`, behind a thin CLI
`scripts/adw-analyze.py`. It reads `~/.claude/projects` transcripts and `gh` GraphQL, holds
everything in memory, and writes only `<reports>/<date>/report.md`, `metrics.json` and
`issue.md`. A bash wrapper does the weekly run under launchd; `claude -p` is used only for the
critical pass. A GitHub Actions cron in the private repo catches a dead loop.

**Tech Stack:** Python 3 stdlib (`json`, `re`, `dataclasses`, `subprocess`, `unittest`), bash,
`gh`, `git`, `claude -p`, launchd, GitHub Actions.

**Spec:** `docs/specs/2026-10-27-adw-self-improving-loop-design.md`

## Global Constraints

- Stdlib only. Every module starts `from __future__ import annotations` and runs on Python 3.9
  (`/usr/bin/python3` is 3.9.6; the wrapper uses `/opt/homebrew/bin/python3`, 3.14).
- **No transcript text, prompt text, command text or file content in any output file.** Outputs
  carry aggregates, metric ids, PR numbers, session ids (first 8 chars) and `predicts` lines.
- `cleanupPeriodDays` is 90. The reader never needs data older than 77 days (spec §5.6).
- Window: trailing 28 days ending at `--until` (default now), plus the 28 days before it.
  All times UTC. The dated folder is the `--until` date in UTC.
- Prices (dated `2026-10-22`, $/Mtok in · out · cache read): opus 4 · 20 · 0.20; sonnet
  2 · 10 · 0.20; haiku 1 · 5 · 0.10. Cache write 5 m = 1.25 × in; 1 h = 2 × in.
- Owner-wait gaps are capped at 12 h, and the report prints the cap.
- Subagent context peak threshold: 250,000 tokens.
- `predicts` `by` date: at most 49 days after the merge.
- Verdict baseline: same length as merge → deadline, capped at 28 days, ending at the merge.
- Leak scan: a 40-character run of a transcript line (sampled every 20 chars) that appears
  in an output is a hit.
- Dead-man threshold: no report newer than 10 days.
- Exit codes of `adw-analyze.py`: 0 ok · 1 a source cannot be read · 2 bad flag, config or
  existing dated folder · 3 the reports dir is in a public or unverifiable GitHub checkout ·
  4 `--scan` found a hit.
- Commit messages follow the repo's style (`<area>: <what>`) and end with the attribution
  trailers the session gives.
- Tests run from `scripts/`: `cd scripts && python3 -m unittest -v <module>`.

## Review Focus

1. **A transcript that is still being written** ends in a half line, and older files hold
   non-JSON lines: skip, count in `bad_lines`, never crash (Task 2).
2. **`gh` fails mid-pagination** (rate limit, auth, network): exit 1 naming the repo; no dated
   folder is left behind (Task 4, Task 8).
3. **A second run on the same date** (manual run plus the weekly one): exit 2, the existing
   folder untouched (Task 8).
4. **A checkout path with a space** (`~/dev/Projects/AXC MED/AXCMedApp` exists): every `git`
   call passes paths as argv, never through a shell string (Task 1, Task 7).
5. **The weekly job fails at any step**: the owner gets a GitHub issue naming the step, not
   silence for 10 days (Task 10).

---

## File Structure

| Path | Responsibility |
|---|---|
| `scripts/adw-analyze.py` | CLI only: put `scripts/` on `sys.path`, call `adw_analyze.cli.main()`. |
| `scripts/adw_analyze/cli.py` | Flags, run order, exit codes. |
| `scripts/adw_analyze/config.py` | `sources.json`, the reports-dir guard. |
| `scripts/adw_analyze/pricing.py` | The dated price table and `message_cost`. |
| `scripts/adw_analyze/transcripts.py` | One JSONL file → `SessionFacts`. Module docstring carries design §5.1's two definitions (`review N/2` = applied rounds; `progress-conditions` is hyphenated). |
| `scripts/adw_analyze/attribute.py` | Session and subagent → repo and intent slug. |
| `scripts/adw_analyze/github.py` | `gh` GraphQL → `PR` objects; evidence-block parse. |
| `scripts/adw_analyze/facts.py` | `Facts`, `Intent`, `Slice`: the joined, sliceable data. |
| `scripts/adw_analyze/metrics.py` | The registry (ids, flags, minimum samples) and `compute`. |
| `scripts/adw_analyze/predicts.py` | Parse and validate `predicts` lines. |
| `scripts/adw_analyze/verdicts.py` | Contract-sha split, spans, verdicts, record vs restated. |
| `scripts/adw_analyze/report.py` | `report.md`, `metrics.json`, `issue.md`. |
| `scripts/adw_analyze/scan.py` | `--scan`: secret patterns and transcript overlap. |
| `scripts/adw_analyze/testkit.py` | Test-only builders: records, sessions, a fake `gh`. |
| `scripts/test_adw_analyze_<module>.py` | One test file per module. |
| `scripts/test_adw_analyze.py` | End-to-end CLI and the leak test (the spec's test file). |
| `scripts/adw-analyze-weekly.sh` | The weekly wrapper, `--install`, `--uninstall`, `--dry-run`. |
| `scripts/test_adw_analyze_weekly.py` | The wrapper against fake `gh`, `claude`, `launchctl`. |
| `.claude/skills/adw-analyze/SKILL.md` | The command the owner runs by hand. |
| `.claude/skills/adw-analyze/critical-pass.md` | The prompt the critical pass gets. |
| Private repo `adw-analysis` | `sources.json`, `legacy-verdicts.json`, `.github/workflows/stale-report.yml`, `<date>/`. |

The spec names one script and one test file; splitting them into a package is this plan's
call (spec §9 leaves the module layout to the builder).

---

### Task 1: Package skeleton, config and the reports-dir guard

**Files:**
- Create: `scripts/adw-analyze.py`, `scripts/adw_analyze/__init__.py`, `scripts/adw_analyze/cli.py`, `scripts/adw_analyze/config.py`, `scripts/adw_analyze/testkit.py`
- Test: `scripts/test_adw_analyze_config.py`

**Interfaces:**
- Produces:
  - `Repo` dataclass: `name: str, slug: str, checkout: str, base: str, transcripts: list[str]` (globs relative to the projects dir), `watch: list[str], gates: dict[str, str]` (gate name → regex), `role: str` (`"contract"` for adw, `"app"` otherwise).
  - `load_sources(reports_dir: str) -> list[Repo]`; raises `ConfigError` on a missing file, unknown key or a repo with no `slug`.
  - `resolve_reports_dir(flag: str | None) -> str` (flag, else `$ADW_ANALYSIS_DIR`, else `ConfigError`).
  - `check_reports_dir(path: str) -> None`; raises `PublicRepoError`.
  - `testkit.FakeGh(tmp)`: writes `tmp/bin/gh`; `.set(visibility=..., prs=..., open_prs=..., files=...)`; `.calls() -> list[list[str]]`; `.env() -> dict` with `PATH` and `FAKE_GH_DATA`.
  - `cli.main(argv: list[str]) -> int`.

`sources.json` shape (schema 1):

```json
{"schema": 1, "repos": [
  {"name": "AXCMedApp", "slug": "AXCMED/AXCMedApp", "role": "app",
   "checkout": "/Users/…/AXCMedApp", "base": "develop",
   "transcripts": ["-Users-…-AXCMedApp", "-Users-…-AXCMedApp--claude-worktrees-*"],
   "watch": ["repo-profile.md", "scripts/gate*.sh"],
   "gates": {"gate 4": "testDebugUnitTest|allTests"}}]}
```

The guard: walk up from `path` to the nearest `.git`. No checkout, or a checkout with no
GitHub remote → allowed (scratch dirs, tests). A GitHub remote → `gh repo view <owner/name>
--json visibility -q .visibility`; `PRIVATE` or `INTERNAL` passes; `PUBLIC`, an error, or
anything else raises `PublicRepoError`.

- [ ] **Step 1: Write the failing tests**

```python
class Guard(Base):
    def test_public_checkout_is_refused(self):        # remote github.com/humbertouchiyama/adw, fake gh says PUBLIC
        self.assertEqual(self.run_cli("--reports", self.repo), 3)
    def test_gh_error_is_refused(self):                # fake gh exits 1 → 3
    def test_private_checkout_passes(self):            # PRIVATE → check_reports_dir returns None
    def test_dir_without_remote_passes(self):          # plain tmp dir and a git init with no remote
    def test_path_with_a_space(self):                  # reports dir "AXC MED/reports" passes the guard
class Sources(Base):
    def test_loads_repos(self):                        # two repos, fields round-trip, role defaults to "app"
    def test_missing_file_and_unknown_key_exit_2(self):
    def test_env_var_names_the_dir(self):              # ADW_ANALYSIS_DIR used when --reports is absent
```

- [ ] **Step 2: Run them, expect failures** — `cd scripts && python3 -m unittest -v test_adw_analyze_config` → errors: no module `adw_analyze`.
- [ ] **Step 3: Implement `config.py`, `cli.main` (flags `--reports`, `--until`, `--days`, `--projects`, `--adw`, `--scan`, `--date`; only the guard and config wired so far), the CLI shim and `testkit.FakeGh`.** The fake `gh` answers `repo view`, `api graphql` (Task 4), `issue create` (Task 10) from `FAKE_GH_DATA` and appends each argv to `FAKE_GH_LOG`; `FAKE_GH_FAIL=<subcommand>` makes that subcommand exit 1.
- [ ] **Step 4: Run them, expect PASS.**
- [ ] **Step 5: Commit** — `adw-analyze: package skeleton, sources config, reports-dir guard`.

---

### Task 2: Price table and transcript parser

**Files:**
- Create: `scripts/adw_analyze/pricing.py`, `scripts/adw_analyze/transcripts.py`
- Modify: `scripts/adw_analyze/testkit.py` (record builders)
- Test: `scripts/test_adw_analyze_transcripts.py`

**Interfaces:**
- Consumes: none.
- Produces:
  - `pricing.PRICES_AS_OF = "2026-10-22"`; `pricing.family(model: str) -> str | None`; `pricing.message_cost(u: Usage) -> float`.
  - `Usage` dataclass: `model, ts, input, output, cache_read, cache_write_5m, cache_write_1h` (ints).
  - `SessionFacts` dataclass: `path, project_dir, session_id, agent_id (None on a main thread), tool_use_id, parent_agent_id` (from `.meta.json`), `cwd` (most common), `branches: Counter, first_ts, last_ts, turn_ts: list[str], usage: dict[str, Usage]` (by message id), `compactions: list[tuple[str, str]]` (`limit`/`idle`/`manual`), `tool_calls: Counter, tool_errors: Counter, denials: Counter, human_prompts: list[tuple[str, str | None]]` (ts, previous assistant ts), `interrupts: list[str], pr_links: list[int], captures: Counter` (slug strings, Task 3), `dispatches: dict[str, Counter]` (Agent tool_use id → captures in its prompt), `gate_calls: list[tuple[str, str, float]]` (gate, ts, seconds), `background_gate_calls: int, ran_analyzer: bool, peak_context: int, unknown_types: Counter, bad_lines: int`; property `cost: float`.
  - `read_session(path: str, gates: dict[str, str]) -> SessionFacts`.
  - `testkit`: `assistant(ts, msg_id, model="claude-opus-5-5", usage=None, tools=())`, `tool_use(id, name, **input)`, `user_prompt(ts, text="go")`, `tool_result(ts, tool_use_id, text="", is_error=False)`, `system(ts, subtype, **fields)`, `write_session(projects, project, sid, records) -> str`, `write_subagent(projects, project, sid, agent_id, records, tool_use_id, parent_agent_id=None) -> str`.

Rules this task pins (spec §5.1 table):
- Usage: dedupe by `message.id`, keep the record with the largest `output_tokens`. 5 m and 1 h
  writes from `usage.cache_creation.ephemeral_5m_input_tokens` / `…_1h_…`; when both are 0, all
  of `cache_creation_input_tokens` is 5 m. Model `<synthetic>` is skipped.
- `cost-state` records are counted in `unknown_types` and never read.
- Compaction: `system` / `compact_boundary`; `compactMetadata.trigger == "manual"` → `manual`;
  otherwise `idle` if any record containing `Compacted while idle` lies within 10 s of the
  boundary, else `limit`.
- `first_ts`, `last_ts`, `turn_ts`: `user` and `assistant` records only.
- Human prompt: `user` record with `origin.kind == "human"` or `promptSource == "typed"`, not
  `isMeta`, no `tool_result` block.
- Interrupt: user text containing `[Request interrupted by user`.
- Denials, by source: `permissionDecision.decision == "reject"` →
  `permissionDecision:<source>`; error tool results containing `doesn't want to proceed` →
  `user_rejected`, `denied by the Claude Code auto mode` → `auto_mode_classifier`,
  `classifier gave no verdict` → `classifier_no_verdict`, `built-in Claude Code safety` →
  `builtin_safety`, `hook error` with `Block`/`BLOCK` → `hook_block`.
- Tool calls: unique `tool_use` ids. Tool errors: `tool_result.is_error`, keyed by tool name.
- Gate call: a `Bash` tool_use whose command matches a `gates` regex; foreground → seconds =
  its tool_result record ts − its tool_use record ts; `run_in_background` → counted only.
- `ran_analyzer`: a Bash command containing `adw-analyze.py`, or a human prompt starting
  `/adw-analyze`.
- Unparseable line → `bad_lines += 1`, continue.
- Captures (stored as strings, never text): regexes `\.claude/worktrees/([A-Za-z0-9._-]+)`,
  `\badw/([a-z0-9][a-z0-9.-]+)`, `\[adw ([a-z0-9][a-z0-9.-]+)`,
  `/adw(?:-init|-build|-resume|-close|-smoke)?\s+([a-z0-9][a-z0-9-]+)`, applied to `gitBranch`,
  `cwd`, Bash commands, Agent prompts and human prompts.

- [ ] **Step 1: Write the failing tests**

```python
def test_prices(self):              # opus: 1M in → 4.0; 1M out → 20.0; 1M cache read → 0.20; 1M 5m write → 5.0; 1M 1h write → 8.0; sonnet 1M out → 10.0
def test_usage_deduped_by_message_id(self):   # two records id "m1", output 50 then 100 → one Usage, output 100
def test_unknown_model_costs_zero_and_is_counted(self)
def test_compaction_kinds(self):    # auto at 10:00:00 + "Compacted while idle" at 10:00:05 → idle; auto at 11:00 alone → limit; manual → manual
def test_timing_ignores_other_records(self):  # user 10:00, assistant 10:30, system "Remote Control disconnected" 15:00 → last_ts 10:30
def test_human_prompts_and_interrupts(self):  # typed prompt counted with previous assistant ts; tool_result and isMeta not counted
def test_denial_sources(self):      # one of each marker → six keys, counts 1
def test_gate_calls(self):          # foreground ./gradlew testDebugUnitTest, result 90 s later → ("gate 4", ts, 90.0); background → background_gate_calls 1
def test_bad_lines(self):           # a half line at the end → bad_lines 1, other facts intact
def test_subagent_meta(self):       # write_subagent → agent_id, tool_use_id, parent_agent_id read from .meta.json
def test_no_text_kept(self):        # a prompt "SECRET-MARKER-123 …" → the string appears nowhere in dataclasses.asdict(facts)
```

- [ ] **Step 2: Run, expect failures.**
- [ ] **Step 3: Implement `pricing.py` and `read_session`.** One pass per file; keep only the fields above.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** — `adw-analyze: price table and transcript parser`.

---

### Task 3: Attribution

**Files:**
- Create: `scripts/adw_analyze/attribute.py`
- Test: `scripts/test_adw_analyze_attribute.py`

**Interfaces:**
- Consumes: `SessionFacts` (Task 2).
- Produces:
  - `normalize(capture: str, known: set[str]) -> str | None`.
  - `attribute_session(s: SessionFacts, known: set[str], adw_pr_slugs: dict[int, str]) -> str | None`.
  - `attribute_all(sessions: list[SessionFacts], known: set[str], adw_pr_slugs: dict[int, str]) -> dict[str, str | None]` keyed by `path`.

Rules:
- `normalize`: strip a leading `adw-close-`, `adw-`, `adw/`, `pr-ready-`; strip a trailing
  `-u\d+(\+u\d+)*` or `-close-v\d+`; exact known slug → it; else the longest known slug `k`
  with `capture.startswith(k + "-")`; else `None`.
- Main thread: if its `pr_links` name `[adw …]` PRs of exactly one slug → that slug (PR links to
  non-ADW PRs, such as the starting branch's release PR, are ignored). Otherwise count
  normalized captures; the top slug wins only with ≥ 20 hits and ≥ 3 × the runner-up.
- Subagent: the normalized captures of its dispatching prompt (`dispatches[tool_use_id]` in
  the parent, found through `parent_agent_id`, else the main thread); a unique top slug with
  ≥ 1 hit wins; else it inherits its parent's slug.

- [ ] **Step 1: Write the failing tests**

```python
def test_longest_slug_first(self):   # known {"native-painel","native-painel-shift-form"}; 25 × "adw/native-painel-shift-form" → "native-painel-shift-form"
def test_unit_and_close_names(self): # "adw-native-painel-u03", "adw-close-native-painel", "pr-ready-native-painel-close-v2" → "native-painel"
def test_threshold_19_hits_is_none(self)
def test_ratio_below_3x_is_none(self):  # 30 vs 12 → None
def test_pr_link_overrides_counts(self): # pr_links [41] where 41 is "[adw x u01]", captures say y × 40 → "x"
def test_release_pr_link_ignored(self):  # pr_links [7] where 7 is not an ADW PR → falls back to counts
def test_subagent_from_dispatch_prompt(self)    # worktree adw-native-painel-u03 in the prompt → "native-painel"
def test_subagent_inherits_parent(self)         # no capture in prompt → parent's slug; depth 2 resolves through parent_agent_id
```

- [ ] **Step 2: Run, expect failures.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** — `adw-analyze: attribute sessions and subagents to intents`.

---

### Task 4: GitHub facts and the evidence block

**Files:**
- Create: `scripts/adw_analyze/github.py`
- Modify: `scripts/adw_analyze/testkit.py` (`FakeGh` GraphQL pages)
- Test: `scripts/test_adw_analyze_github.py`

**Interfaces:**
- Consumes: `Repo` (Task 1).
- Produces:
  - `Commit(oid: str, headline: str, date: str, inherited: bool)`.
  - `PR` dataclass: `repo, number, title, slug, unit` (`None` = final PR), `adw: bool, state, created, merged, closed, last_edited, base, head, merge_sha, labels_now: set, labels_ever: set, commits: list[Commit], files: list[str], body: str` (memory only), `block: dict[str, str] | None, block_count: int`; properties `fix_cycles: int` (max N of `fix-attempt-N` in own commits, 0 if none), `review_fix_commits: int`, `contract_sha: str | None`.
  - `fetch_prs(repo: Repo, since: str) -> list[PR]` (created ≥ `since`); `fetch_open_prs(repo: Repo) -> list[PR]`. Both raise `SourceError(repo.name, reason)` on any `gh` failure.
  - `parse_block(body: str) -> tuple[dict[str, str] | None, int]`.
  - `ROWS = ("contract","tier","cycles","phases","owner-wait","asks","gates","mutation","artifact","open-findings","smoke")`.
  - Row readers: `minutes(text) -> float | None`; `cycles(text) -> dict` with `fix`, `fix_cap`, `review`, `review_cap`, `progress` (`"none" | "fired" | "not consumed" | None`).

GraphQL, one paginated query per repo, `orderBy CREATED_AT DESC`, `first: 40`, stop at the
first PR created before `since`. Fields: `number title body state createdAt mergedAt closedAt
lastEditedAt baseRefName headRefName mergeCommit{oid} labels(first:20){nodes{name}}
timelineItems(first:50,itemTypes:[LABELED_EVENT]){nodes{... on LabeledEvent{label{name}}}}
commits(first:100){nodes{commit{oid messageHeadline committedDate}}}`; for the `contract`
role add `files(first:100){nodes{path}}`. `fetch_open_prs` uses `states: OPEN`, no `since`.

Rules:
- ADW PR: title matches `^\[adw ([^\]\s]+)(?: ([^\]]+))?\]`. A commit is `inherited` when its
  headline starts `[adw `.
- `parse_block`: find every line matching `^\s*`?contract`?\s+([0-9a-f]{7,40})\b` anywhere
  (fenced, unfenced, inside `<details>`). From the first one, read up to 15 lines; each line
  `^\s*`?(<row>)`?\s+(.*)$` for a row not yet seen is kept raw; stop at a fence line.
  `block_count` = number of `contract` lines. No `contract` line → `(None, 0)`.
- `minutes`: sum of `(\d+(?:\.\d+)?)\s*(h|m)\b`; no match → `None` (so `unmeasured` is no data).
- `cycles`: `fix (\d+)/(\d+)`, `review(?: v\d+)? (\d+)/(\d+)`; `progress-conditions none
  fired` → `none`; text containing `not consumed` → `not consumed`; containing `fired` →
  `fired`.

- [ ] **Step 1: Write the failing tests**

```python
def test_block_fenced_unfenced_details(self)   # same rows found in all three shapes
def test_block_raw_strings_kept(self)          # gates row with Portuguese notes kept verbatim
def test_two_blocks_counted(self)              # block_count 2, first block used
def test_no_contract_row_is_none(self)
def test_minutes(self)                          # "1h 5m" → 65.0; "0m" → 0.0; "unmeasured (Docker)" → None
def test_cycles(self)                           # "fix 1/3 · review v2 2/2      progress-conditions none fired" → fix 1, fix_cap 3, review 2, review_cap 2, progress "none"
def test_final_pr_excludes_inherited(self)      # final PR with "[adw s u01] …" and "fix-attempt-2: x" own → fix_cycles 2, inherited excluded
def test_fetch_paginates_and_stops_at_since(self)  # fake gh: 2 pages, stops before the older one
def test_gh_failure_raises_source_error(self)   # FAKE_GH_FAIL=api → SourceError("AXCMedApp", …)
def test_labels_ever(self)                      # LABELED_EVENT blocked, label removed since → in labels_ever, not labels_now
```

- [ ] **Step 2: Run, expect failures.**
- [ ] **Step 3: Implement.** `gh api graphql -f query=… -F owner=… -F name=… [-F cursor=…]`, argv lists only.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** — `adw-analyze: GitHub facts and evidence-block parse`.

---

### Task 5: Facts, slices and the metric registry

**Files:**
- Create: `scripts/adw_analyze/facts.py`, `scripts/adw_analyze/metrics.py`
- Test: `scripts/test_adw_analyze_metrics.py`

**Interfaces:**
- Consumes: `SessionFacts`, `attribute_all`, `PR`.
- Produces:
  - `Intent(repo, slug, prs: list[PR], sessions: list[SessionFacts], first_prompt: str | None, last_merge: str | None, contract_sha: str | None)` with `cost`, `owner_wait_h`, `run_h`, `lead_h`.
  - `Facts(until, repos, sessions, prs, open_prs, intents, excluded_sessions: int)`; `build_facts(repos, projects_dir, until, since) -> Facts`. Sessions with `ran_analyzer` are dropped and counted; `contract`-role repos contribute PRs only, never sessions.
  - `Slice(facts, start, end, side: tuple[str, str] | None = None, is_after: Callable[[str, str], bool | None] | None = None)` with `prs(field="created")`, `sessions()`, `intents()`. `side = ("after"|"before", merge_sha)`; `is_after(merge_sha, contract_sha)` is required when `side` is set (Task 7 supplies the git one; tests pass a dict lookup).
  - `Metric(id, group, kind, predictable, min_n, unit, definition)`; `REGISTRY: dict[str, Metric]`.
  - `MetricValue(value: float | None, n: int, status: "ok" | "no data" | "below minimum", breakdown: dict[str, float])`.
  - `compute(metric_id: str, sl: Slice) -> MetricValue`.

A session belongs to a slice by `first_ts`; with a `side`, by its intent's contract sha, and by
the clock when it has none. (Spec §5.3 also names the session's first `fetch.sh` result; an
attributed session already carries its intent's sha, so this plan drops that source.) A PR belongs by the named time field and its own `contract_sha`.
`kind ∈ {count, total, rate, ratio, median, quantile}`; only `rate`, `ratio`, `median` are
predictable. A field missing from a PR body is excluded from that metric's `n`, never read
as 0.

The registry, schema v1 (ids end `.v1`; a definition change is a new id):

| id | kind · pred · min_n | definition |
|---|---|---|
| `cost.total_usd` | total · no · — | $ of app sessions; breakdown repo, main/sub, model family |
| `cost.usd_per_merged_pr` | ratio · yes · 10 PRs | total $ / ADW PRs merged |
| `cost.usd_per_intent_median` | median · yes · 8 intents | intent $ over intents with a merged PR |
| `cost.usd_per_intent_p90` | quantile · no · 8 | same, p90 |
| `cost.subagent_share` | ratio · yes · 10 sessions | subagent $ / total $ |
| `cost.opus_main_share` | ratio · yes · 10 sessions | Opus main-thread $ / total $ |
| `owner.prompts` | count · no · — | human prompts |
| `owner.interrupts` | count · no · — | interrupts |
| `owner.prompts_per_intent_median` | median · yes · 8 | |
| `owner.wait_hours_per_intent_median` | median · yes · 8 | Σ min(gap, 12 h), gap = prompt − previous assistant record |
| `owner.wait_share` | ratio · yes · 8 | Σ wait / Σ main-session span, over intents |
| `owner.halts_per_merged_pr` | ratio · yes · 10 | prompts while one of the intent's ADW PRs was open / merged PRs |
| `outcome.prs_opened` / `prs_merged` / `prs_closed` | count · no · — | ADW PRs |
| `outcome.ever_blocked_rate` | rate · yes · 20 | `blocked` in `labels_ever` / opened |
| `outcome.failed_rate` | rate · yes · 20 | `failed` in `labels_ever` / opened |
| `outcome.fix_cycles_per_pr` | rate · yes · 20 | mean `fix_cycles` over merged |
| `outcome.review_fix_commits_per_pr` | rate · yes · 20 | mean `review_fix_commits` over merged |
| `outcome.reverts` | count · no · — | PRs titled `Revert "[adw` |
| `outcome.followup_fix_rate` | rate · yes · 20 | non-ADW PRs matching `(?i)\bfix` that cite `#N` of an earlier merged ADW PR / merged ADW PRs |
| `evidence.block_missing_rate` | rate · yes · 20 | opened ADW PRs with no block |
| `evidence.coverage.<row>` (each `ROWS` entry) | rate · yes · 20 | blocks carrying the row |
| `evidence.review0_with_fixreview_rate` | rate · yes · 20 | `review 0/N` rows on PRs with `fix(review):` commits / parsed review rows |
| `evidence.never_edited_rate` | rate · yes · 20 | blocks whose PR `last_edited` is null or equals `created` |
| `friction.denials_per_1k_calls` | rate · yes · 1000 calls | breakdown by source |
| `friction.tool_errors_per_1k_calls` | rate · yes · 1000 calls | breakdown by tool |
| `friction.compactions_limit` / `_idle` / `_manual` | count · no · — | main threads |
| `friction.limit_compactions_per_intent` | ratio · yes · 8 | |
| `friction.subagents_over_250k_rate` | rate · yes · 50 subagents | |
| `time.intent_lead_hours_median` | median · yes · 8 | first human prompt → last merge, intents whose last PR merged in the slice |
| `time.intent_lead_hours_p90` | quantile · no · 8 | |
| `time.gate_fg_hours` | total · no · — | foreground gate seconds / 3600; breakdown by gate |
| `time.gate_fg_hours_per_merged_pr` | ratio · yes · 10 | |
| `design.progress_fired` / `design.progress_not_consumed` / `design.instrumented_units` | count · no · — | from `cycles` rows; units without the row are not instrumented |
| `design.fix_cap_reached` / `design.review_cap_reached` | count · no · — | N == cap |
| `design.open_blocked_failed` / `design.oldest_blocked_failed_days` | count · no · — | `open_prs` with `blocked` or `failed` now, as of `until` |
| `loop.contract_prs_merged` / `_with_predicts` / `_predicts_none` / `loop.predicts_rejected` | count · no · — | adw PRs touching `commands/` or `scripts/` (Task 6 fills the last three) |
| `loop.predicts_coverage` | ratio · yes · 3 | with a line (any kind) / contract PRs merged |

- [ ] **Step 1: Write the failing tests** — one fixture `Facts` built from `testkit` (two intents, three PRs, five sessions). Assertions pin values, for example:

```python
def test_usd_per_merged_pr(self)          # $30 of sessions, 2 merged → 15.0, n 2, status "below minimum" (min 10)
def test_owner_wait_cap(self)             # gaps 30 m and 20 h → 12.5 h for the intent
def test_missing_field_is_no_data(self)   # no PR carries owner-wait → value None, status "no data"
def test_unattributed_session_counts_in_cost_only(self)
def test_side_split(self)                 # is_after maps sha A → True, B → False: PRs split accordingly; a session of an intent with sha A lands in "after"
def test_only_rates_ratios_medians_predictable(self)  # every REGISTRY entry: predictable == (kind in {"rate","ratio","median"})
def test_progress_buckets(self)           # rows "none fired", "P3 fired", "P2 evaluated, not consumed" → fired 1, not_consumed 1, instrumented 3
```

- [ ] **Step 2: Run, expect failures.**
- [ ] **Step 3: Implement `facts.py` and `metrics.py`.** Each metric is a small function registered under its id.
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** — `adw-analyze: facts, slices and metric registry v1`.

---

### Task 6: The `predicts` line

**Files:**
- Create: `scripts/adw_analyze/predicts.py`
- Test: `scripts/test_adw_analyze_predicts.py`

**Interfaces:**
- Consumes: `PR` (contract role), `REGISTRY`.
- Produces:
  - `Prediction(pr: int, key: str, line: str, metric: str, direction: "down" | "up", amount: float, unit: "pct" | "abs" | "zero", by: str, for_path: str, section: str | None, repo: str | None, merged: str, merge_sha: str)`; `key = f"{pr}:{sha1(line)[:8]}"`.
  - `NoPrediction(pr: int, reason: str)`; `Rejected(pr: int, line: str, reason: str)`.
  - `read_predictions(pr: PR, path_exists: Callable[[str, str], bool]) -> list[Prediction | NoPrediction | Rejected]`.

Grammar (spec §5.2), one per line, leading whitespace allowed:

```
predicts  <metric-id> <down|up> <N%|N|to-zero> by <YYYY-MM-DD> for <path>[ §<section>] [repo <name>]
predicts  none — <reason>
```

Rejection reasons, exact strings: `unknown metric`, `metric not predictable`, `bad grammar`,
`path not at merge commit`, `deadline over 49 days`, `deadline before merge`. `path_exists(sha,
path)` is `git -C <adw> cat-file -e <sha>:<path>` (Task 7 wires it).

- [ ] **Step 1: Write the failing tests**

```python
def test_relative(self)        # "predicts  friction.denials_per_1k_calls.v1 down 30% by 2026-12-01 for commands/adw-build.md §3.4" → amount 30.0, unit "pct", section "3.4"
def test_absolute_and_zero_and_repo(self)
def test_none_line(self)
def test_each_rejection(self)  # one line per reason above → Rejected with that reason
def test_two_lines_two_predictions(self)  # #12-style bundle → two keys, different
```

- [ ] **Step 2: Run, expect failures.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** — `adw-analyze: parse and validate predicts lines`.

---

### Task 7: Verdicts

**Files:**
- Create: `scripts/adw_analyze/verdicts.py`
- Test: `scripts/test_adw_analyze_verdicts.py`

**Interfaces:**
- Consumes: `Facts`, `Slice`, `compute`, `Prediction`.
- Produces:
  - `git_is_after(adw_dir: str) -> Callable[[str, str], bool | None]`: `git -C <adw_dir> merge-base --is-ancestor <merge_sha> <contract_sha>`; exit 0 → True, 1 → False, else None (unknown sha; excluded and counted).
  - `git_path_exists(adw_dir) -> Callable[[str, str], bool]`.
  - `Verdict(key, verdict: "too early" | "worked" | "failed" | "confounded" | "no data", baseline: MetricValue, after: MetricValue, cause: str | None)`.
  - `judge(p: Prediction, facts: Facts, all_predictions: list[Prediction], is_after, watch_changed: Callable[[str, str, str], bool]) -> Verdict`.
  - `git_watch_changed(repos: list[Repo]) -> Callable[[str | None, str, str], bool]` (repo name or `None` for all app repos, start, end): `git -C <checkout> log --format=%H origin/<base> --since=<start> --until=<end> -- <watch…>` non-empty.
  - `read_records(reports_dir: str) -> dict[str, dict]`: the verdict of record per key, from the earliest dated `metrics.json` whose date is after the deadline and that holds the key.

Rules:
- Spans: after = `[merge, by]`, side `after`; baseline = `[merge − min(by − merge, 28 d), merge)`, side `before`.
- `until < by` → `too early` (the report shows the running after-value).
- Either side `status != "ok"` → `no data`.
- `confounded` first, with its cause: another prediction on the same metric and repo whose
  `[merge, by]` overlaps either span (`overlaps #<pr>`), or `watch_changed` true over
  `[baseline start, by]` (`watch path changed in <repo>`).
- Change = after − baseline. `pct`: `|change| / baseline × 100 ≥ amount` in the predicted
  direction (baseline 0 → `no data`); `abs`: `|change| ≥ amount` in the direction; `zero`:
  after == 0. Met → `worked`, else `failed`.

- [ ] **Step 1: Write the failing tests** (scratch adw repo with commits A → B → C; prediction merged at B)

```python
def test_run_started_before_merge_counts_before(self)  # PR finished after the merge, contract sha A → baseline side
def test_unknown_sha_excluded(self)
def test_worked_and_failed_by_pct(self)                # baseline 10.0 / after 6.0, predicts down 30% → worked; down 50% → failed
def test_already_low_baseline_cannot_pass(self)        # baseline 0.5, after 0.5, predicts down 10% → failed
def test_deadline_today_is_judged(self)                # until == by → judged, not too early
def test_one_below_minimum_is_no_data(self)            # 19 PRs on one side, min 20
def test_confounded_by_overlap_and_by_watch_path(self)
def test_record_vs_restated(self)                      # reports dir holds 2026-12-02/metrics.json with "failed"; new compute "worked" → record failed, restated worked
def test_path_with_space(self)                         # adw dir "a b/adw" works
```

- [ ] **Step 2: Run, expect failures.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** — `adw-analyze: verdicts, contract-sha split, record vs restated`.

---

### Task 8: Report, metrics.json, issue.md and the end-to-end run

**Files:**
- Create: `scripts/adw_analyze/report.py`
- Modify: `scripts/adw_analyze/cli.py` (full run order)
- Test: `scripts/test_adw_analyze.py`

**Interfaces:**
- Consumes: all of the above.
- Produces:
  - `write_outputs(out_dir: str, facts, window: dict[str, MetricValue], prior: dict[str, MetricValue], predictions, verdicts, records, rejected, legacy: list[dict], sources_hash: str) -> None`.
  - `metrics.json` top-level keys: `schema` (1), `until`, `window` `[start, end]`, `prior` `[start, end]`, `prices` (`as_of` + table), `owner_wait_cap_h` (12), `sources_hash`, `metrics` (`id → {window, prior, n_window, n_prior, status_window, status_prior, breakdown}`), `predictions` (key → line, pr, metric, by), `verdicts` (key → `{verdict, of_record: bool, record: str | null, restated: str | null, cause}`), `rejected`, `not_measured` (list), `excluded_sessions`, `bad_lines`, `unknown_types`.
  - `report.md` sections in order: title and window line; `## Verdicts`; `## Delete candidates`; `## Metrics` (table: id · window · prior · change · n); `## Self-report trust` (evidence mismatch rates); `## The loop`; `## Legacy verdicts (information only)`; `## Rejected predicts lines`; `## NOT MEASURED`; `## Critical pass` with the single line `critical pass: pending`.
  - `issue.md`: verdicts reached this run, the five predictable metrics that moved most (by |relative change|, status ok both sides), delete candidates, and the line `leak scan: pending`.
  - CLI run order: guard → load sources → fail if `<reports>/<date>/` exists (exit 2) → read transcripts and app-repo `gh` data for `since = until − 77 d`, and the `contract` repo's PRs with no `since` (exit 1 on `SourceError` or a source with no files) → compute window, prior, predictions, verdicts → write to `<reports>/.<date>.tmp/` → rename to `<date>/`.

`NOT MEASURED` prints every run: background gate time (with the background gate-call count),
owner-found device defects, escape rate, base-red truth on a repo with no CI, any window before
transcripts exist (with the earliest transcript date found).

`legacy-verdicts.json` (reports repo root): `[{"pr": 12, "for": "…", "verdict": "failed",
"note": "…"}]`, printed as is.

- [ ] **Step 1: Write the failing tests**

```python
def test_end_to_end(self)               # fixtures for one app repo + adw contract PR with a predicts line → exit 0; <date>/report.md has every section heading; metrics.json schema 1 and every REGISTRY id
def test_same_date_twice_exits_2(self)  # second run → 2, first folder unchanged (mtime and bytes)
def test_gh_failure_leaves_nothing(self)   # FAKE_GH_FAIL=api → exit 1, no <date>/ and no .tmp dir
def test_missing_transcripts_exit_1(self)  # a glob that matches nothing → 1, names the repo
def test_analyzer_sessions_excluded(self)  # a session running adw-analyze.py → excluded_sessions 1, not in cost
def test_no_data_prints_no_data(self)       # report shows "no data", never "0", for an empty field
```

- [ ] **Step 2: Run, expect failures.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** — `adw-analyze: dated report, metrics.json and issue summary`.

---

### Task 9: The leak scan

**Files:**
- Create: `scripts/adw_analyze/scan.py`
- Modify: `scripts/adw_analyze/cli.py` (`--scan --date`)
- Test: `scripts/test_adw_analyze.py` (`Leak` class)

**Interfaces:**
- Consumes: `load_sources`, `transcripts` globbing.
- Produces: `scan(out_dir: str, transcript_paths: list[str]) -> list[Hit]`; `Hit(file: str, line: int, kind: "secret" | "transcript")`. CLI `--scan --date D` scans `<reports>/D/` and exits 4 on any hit, printing `file:line kind` only, never the matched text.

Rules:
- Files scanned: every file in the dated folder.
- Secret patterns: `-----BEGIN [A-Z ]*PRIVATE KEY-----`, `"private_key":`, `AKIA[0-9A-Z]{16}`,
  `gh[pousr]_[A-Za-z0-9]{36,}`, `github_pat_[A-Za-z0-9_]{40,}`, `AIza[0-9A-Za-z_-]{35}`,
  `xox[abprs]-[A-Za-z0-9-]{10,}`, `sk-ant-[A-Za-z0-9_-]{20,}`, `sk-[A-Za-z0-9]{32,}`,
  `eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}`.
- Transcript overlap: index every 40-char window of the outputs (whitespace collapsed). For
  each string value in each `user`/`assistant` record of the app transcripts in the window,
  split on newlines, collapse whitespace, and look up the 40-char windows at offsets 0, 20,
  40, … of every line of ≥ 40 chars. Lines that are `predicts` lines are skipped on both sides.
- Transcripts of the analyzer's own sessions and of `contract`-role repos are not scanned.

- [ ] **Step 1: Write the failing tests**

```python
def test_reader_never_emits_text(self)      # fixtures hold "-----BEGIN PRIVATE KEY-----" and a 60-char marker line; full run; neither appears in any output
def test_scan_catches_planted_key(self)     # append the key to report.md → exit 4, hit kind "secret", stdout has no key text
def test_scan_catches_planted_quote(self)   # append a sentence quoting the marker line's middle 60 chars → exit 4, kind "transcript"
def test_clean_report_passes(self)          # exit 0
```

- [ ] **Step 2: Run, expect failures.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect PASS** — then the whole suite: `cd scripts && python3 -m unittest -v` → all OK.
- [ ] **Step 5: Commit** — `adw-analyze: leak scan`.

---

### Task 10: The weekly wrapper

**Files:**
- Create: `scripts/adw-analyze-weekly.sh`, `.claude/skills/adw-analyze/critical-pass.md`
- Test: `scripts/test_adw_analyze_weekly.py`

**Interfaces:**
- Consumes: `adw-analyze.py` exit codes; `report.md` line `critical pass: pending`; `issue.md` line `leak scan: pending`.
- Produces: `adw-analyze-weekly.sh [run | --dry-run | --install | --uninstall]`.

Environment, with defaults:

| Variable | Default |
|---|---|
| `ADW_ANALYSIS_DIR` | `$HOME/dev/Projects/adw-analysis` |
| `ADW_REPO` | `$HOME/dev/Projects/adw` |
| `ADW_WEEKLY_WORKTREE` | `$HOME/dev/Projects/adw-weekly` |
| `ADW_WEEKLY_PATH` | `/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin` (becomes `PATH`) |
| `ADW_ANALYSIS_SLUG` | read from `git -C $ADW_ANALYSIS_DIR remote get-url origin` |

`run`, in order, `set -euo pipefail`, every failure trapped:
1. Create the worktree if missing (`git -C "$ADW_REPO" worktree add --detach "$WT" origin/main`), then `git -C "$WT" fetch origin` and `git -C "$WT" checkout --detach origin/main`; re-exec the refreshed copy once (`ADW_WEEKLY_REEXEC=1`).
2. `git -C "$ADW_ANALYSIS_DIR" pull --ff-only`.
3. `python3 "$WT/scripts/adw-analyze.py" --reports "$ADW_ANALYSIS_DIR" --adw "$WT"`; `D` = today UTC.
4. Critical pass, cwd `$ADW_ANALYSIS_DIR`: `claude -p "<critical-pass.md with D substituted>" --model sonnet --permission-mode dontAsk --add-dir "$HOME/.claude/projects" --allowedTools Read Grep Glob "Edit($ADW_ANALYSIS_DIR/$D/critical-pass.md)"`. If `$D/critical-pass.md` exists and is non-empty, it replaces the `critical pass: pending` line; otherwise that line becomes `critical pass: missing`. A failed `claude` does not stop the run.
5. `python3 … --scan --date "$D"`. Exit 4 → delete `$D/`, open the failure issue, exit 1.
6. Replace `leak scan: pending` with `leak scan: clean`; `git add "$D"`, commit `report $D`, push.
7. `gh issue create -R "$SLUG" --title "ADW analysis $D" --body-file "$D/issue.md"`.

On any failed step: `gh issue create -R "$SLUG" --title "ADW analysis $D failed at <step>" --body "<exit code; see ~/Library/Logs/adw-analyze-weekly.log>"`, then exit 1.
`--dry-run`: steps 1–6 without push, and steps 7 and the failure issue printed instead of run.
`--install`: write `~/Library/LaunchAgents/dev.adw.analyze-weekly.plist` (Program `/bin/bash`
`$WT/scripts/adw-analyze-weekly.sh run`; `StartCalendarInterval` Weekday 1, Hour 7, Minute 0
local; stdout and stderr to `~/Library/Logs/adw-analyze-weekly.log`; `EnvironmentVariables`
with the five variables above), then `launchctl bootstrap gui/$(id -u) <plist>`.
`--uninstall`: `launchctl bootout gui/$(id -u)/dev.adw.analyze-weekly`, delete the plist.

`critical-pass.md` tells the subagent: read `<D>/report.md` and `<D>/metrics.json`; challenge every
metric that moved more than 25 % between windows and every verdict, using the transcripts and
`gh` data; write findings to `<D>/critical-pass.md`, one per line, citing only metric ids, PR
numbers and 8-char session ids, never a quote from a transcript, prompt or command.

- [ ] **Step 1: Write the failing tests** (fake `gh`, `claude`, `launchctl`, `python3` stub via `ADW_WEEKLY_PATH`; scratch git repos with a bare remote for the reports repo)

```python
def test_happy_path_commits_pushes_and_opens_issue(self)
def test_missing_critical_pass_is_marked_and_still_committed(self)
def test_scan_hit_deletes_folder_and_opens_failure_issue(self)   # stub reader exits 4 on --scan
def test_reader_failure_opens_failure_issue(self)                 # stub exits 1 → issue title "... failed at reader"
def test_dry_run_pushes_nothing(self)                             # bare remote unchanged, gh issue not called
def test_install_and_uninstall(self)                              # HOME=tmp; plist written with Weekday 1; launchctl bootstrap/bootout called
```

- [ ] **Step 2: Run, expect failures.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** — `adw-analyze: weekly wrapper, launchd install, critical pass`.

---

### Task 11: The skill and the docs

**Files:**
- Create: `.claude/skills/adw-analyze/SKILL.md`
- Modify: `docs/00-design.md:782`, `docs/00-design.md:798-816`, `docs/00-design.md:997`, `docs/00-design.md:1024`; `.claude/skills/reviewing-contract-prs/SKILL.md:97` (lane C); `README.md` (rows, "Changing the contract")

**Interfaces:**
- Consumes: the wrapper (Task 10).

Content to write:
- `SKILL.md`: frontmatter `name: adw-analyze`, description "Run the ADW analysis now: the weekly report, critical pass, leak scan, commit and issue, in the private reports repo." Steps: run `bash scripts/adw-analyze-weekly.sh run` from this repo; show the issue URL and the verdicts section; never paste report lines from other repos into this public repo. No loader stub.
- Design §5.1 row 782: reader is `scripts/adw-analyze.py`; it reads every `[adw …]` PR body and the session transcripts, writes a dated report to the private reports repo, and closes with `NOT MEASURED`. Paragraph 798: rename the script, keep both definitions, add the spec §7 amendment text verbatim. §8 line 997 and §9 line 1024: cite `scripts/adw-analyze.py` and the metric ids `design.progress_fired.v1`, `design.fix_cap_reached.v1`, `design.review_cap_reached.v1`.
- Lane C: add question (6): "If the diff touches `commands/` or `scripts/`, does the body carry `predicts` lines in README's grammar, one per fix it bundles, or `predicts  none — <reason>`? A missing or malformed line is a Warning."
- README: rows for `scripts/adw-analyze.py`, `scripts/adw-analyze-weekly.sh`, `.claude/skills/adw-analyze/`; under "Changing the contract", the grammar block from spec §5.2 and two sentences: every PR that changes `commands/` or `scripts/` carries it; the weekly report judges it after its deadline. The private repo is named only as "the owner's private reports repo".

- [ ] **Step 1: Write the files.**
- [ ] **Step 2: Run the anchor checker** — `python3 .claude/skills/reviewing-contract-prs/check-anchors.py` → no NEW broken anchors.
- [ ] **Step 3: Leak check of the public diff** — `git diff origin/main -- . | grep -nE 'AXCMED|/Users/|\$[0-9]'` → only lines that are already on `origin/main`, or none.
- [ ] **Step 4: Commit** — `adw-analyze: skill, design §5.1/§8/§9, lane C predicts rule, README`.

---

### Task 12: The private reports repo — needs the owner's go-ahead

**Files (in the new repo `~/dev/Projects/adw-analysis`):** `sources.json`, `legacy-verdicts.json`, `.github/workflows/stale-report.yml`, `README.md` (two lines: what this is, never make it public).

- [ ] **Step 1: Ask the owner** to approve `gh repo create humbertouchiyama/adw-analysis --private --clone`. Stop until they answer.
- [ ] **Step 2: Write `sources.json`.** Find each app repo's checkout (`git -C <dir> remote get-url origin` over `~/dev/Projects/AXC MED/*` and `~/dev/Projects/plantoes/*`) and every matching transcript dir (`ls ~/.claude/projects | grep -i <repo>`; today both `-…-AXC-MED-<repo>` and `-…-plantoes-<repo>` exist; list both). `base`: AXCMedApp `develop`; Plantoes-app from its repo profile. `watch`: `git ls-files | grep -E 'repo-profile|scripts/(gate|audit)'`. `gates`: the gate commands named in each repo profile's §5 table. adw: role `contract`, `transcripts: []`.
- [ ] **Step 3: Write `legacy-verdicts.json`**: #12 handoff decide pass `failed` (16 of 22 handoffs still stopped, 10-22 analysis); #15 enforcer drafts `failed` (nothing landed); orchestrator-on-Sonnet `failed for a cause outside the contract` (saved `/model opus` default).
- [ ] **Step 4: Write `stale-report.yml`**: `on: schedule: - cron: "0 12 * * *"` and `workflow_dispatch`; `permissions: issues: write, contents: read`; find the newest folder matching `^20[0-9]{2}-[0-9]{2}-[0-9]{2}$`; if none, or older than 10 days, and no open issue titled `No ADW analysis report for 10 days`, create it with `gh issue create` (`GH_TOKEN: ${{ github.token }}`).
- [ ] **Step 5: Commit and push**; run the workflow once with `gh workflow run stale-report.yml` and check `gh run list` shows success (no report yet → it opens the issue; close it after the first report).

---

### Task 13: Golden run, dry run, install, PR

- [ ] **Step 1: Golden run** into a scratch reports dir: `python3 scripts/adw-analyze.py --reports <scratch> --until 2026-10-22 --days 20 --adw .` (copy `sources.json` there first). Compare with the 10-22 analysis (`project-run-analysis-2026-10-22` memory): $3,907 total; $15.2 per merged PR; ever-blocked 22.5 %; denials 258 (3.10 / 1k); orchestrator auto compactions 65 (expect most of them idle now); implementers and authors over 250k 92; gate wall 183 h (expect lower: foreground only); owner wait 68 % with the 12 h cap. Write every gap over 10 % with its cause to `~/dev/Projects/adw-analysis/golden-2026-10-22.md` and commit it there.
- [ ] **Step 2: Fix any defect the golden run shows**, with a test first, then rerun Step 1.
- [ ] **Step 3: Dry run** — `ADW_ANALYSIS_DIR=<scratch clone of the reports repo> bash scripts/adw-analyze-weekly.sh --dry-run` → a dated folder with the critical pass filled or marked `missing`, `leak scan: clean`, nothing pushed.
- [ ] **Step 4: Whole suite** — `cd scripts && python3 -m unittest -v` → OK.
- [ ] **Step 5: Scrub the public diff.** The spec and this plan cite app-repo spend, PR counts and
  local paths. adw is public: replace dollar amounts and app PR numbers with their rule, and
  local paths with `$HOME/…`, unless the owner chooses otherwise. Rerun Task 11 Step 3's grep.
- [ ] **Step 6: Push the branch and open the adw PR** (owner approves the push). Body: what it adds, the test result line, the golden-run summary without private numbers (say "within 10 % except N metrics, explained in the private repo"), and `predicts  none — this PR builds the measurement; nothing to predict yet`. Run `/reviewing-contract-prs <N>`.
- [ ] **Step 7: After the merge** — create the worktree, `bash scripts/adw-analyze-weekly.sh --install`, then `launchctl kickstart -k gui/$(id -u)/dev.adw.analyze-weekly`; check the log, the pushed folder and the issue.
