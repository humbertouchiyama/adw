---
description: "Code review PR against project conventions. Usage: /code-review <PR_NUMBER> [light|full|panel] [apply] [interactive]"
---

# Code Review

> **Phase 1 reads [`review-core.md`](review-core.md) and
> the consuming repo's `.claude/repo-profile.md` first.** This skill owns only its *unique* signal
> — arg parsing, the classification and scoring **procedure**, cloud-plugin invocation + gating,
> triage routing, the output contract. All shared machinery (setup/worktree, ledger, adjudication,
> verification, escalation, calibration, safety stops) lives in `review-core.md`; every repo-specific
> **value** — layer table, score rows, review emphasis, severity classes, rule tables, doc routing —
> lives in `repo-profile §13`–`§17`. This file quotes the one-line rule and links `→ review-core §N`
> or `→ repo-profile §N`.
>
> **This file lives in the `adw` repository and is fetched, not copied** (adw-core §9). It is repo-agnostic: every value that could differ between repos is in the consuming repo's `repo-profile.md`.

**Input**: `$ARGUMENTS` — first token is PR number; remaining tokens are optional flags in any order.

| Flag | Effect |
|---|---|
| (none) | auto-triage → light, full or panel (Phase 3) |
| `light` | force 1-agent path |
| `full` | force Anthropic plugin + project checks |
| `panel` | force the widest path — 3 parallel angled lanes (4a-panel) + the plugin + project checks, and the gated refutation pass (review-core §9). This is the human's "look harder at this one" lever; the auto-triage reaches it at score `>= 12` on its own |
| `apply` | terminal action becomes "fix → verify → **commit → push** → ask-merge" instead of "post review comment". **`apply` IS the commit+push consent** (code-review declares §8 auto-ship): §4 green → push to the PR branch, no further gate. Re-runs push again as new commits. **Merge stays gated on the word "merge"**; §7 stops still fall back to comment-only. |
| `interactive` | explicit signal that a human is watching → escalations surface via `AskUserQuestion` instead of the report/terminal gate (**review-core §5**). Never inferred from `apply`. |
| `since:<sha>` | scope the review to what changed **after** `<sha>` instead of the whole PR (Phase 2). For a re-review after fixes: `/pr-ready` §3 passes cycle 1's head SHA so cycle 2 grades only the fix. Caller-supplied only — a run never narrows its own scope. |

Examples: `/code-review 393`, `/code-review 393 full`, `/code-review 393 light apply`, `/code-review 393 apply interactive`.

**Context**: `repo-profile §15` states this repo's stack and what a review weights above style
polish; `§2` names its standards docs. Reviews focus on **convention adherence, correctness, and
cross-boundary contract sync** — what those mean concretely is `§15`'s to say, not this file's.

---

## Pipeline (data flow)

Each phase produces a typed output the next phase consumes. `apply` selects which terminal action Phase 7 runs, but Phase 7 itself always runs.

```
0 Dispatch    → run as a driver, or become one   (Phase 0)
1 Setup       → {pr, $WT, mode, apply, interactive, ledger}   (review-core §1, §2)
2 Scope       → {changedFiles[], stats, layers[]}
3 Path        → "light" | "full" | "panel"
4 Review      → findings[] {…, severity, originalSeverity}   (light: 1 lane / panel: 3 angled lanes / + gated plugin + 4.5 parse)
5 Project     → findings[] (appended)
6 Triage      → {toFix[], escalate[], conventionEdits[]}   (adjudication: review-core §3; calibration: §6)
7 Terminal    → comment posted | fixes committed + pushed + ask-merge (apply)   (§1.3, §4, §5, §7, §8)
8 Cleanup     → worktree removed   (review-core §1.4)
```

**No phase produces "advice that may or may not be acted on" — every output has a consumer.**

---

## Phase 0 — Driver dispatch

**This file plus `review-core.md` plus the consuming repo's `repo-profile.md` are ~100k bytes.**
Whatever window reads them carries them on every later turn and re-reads them in full after a
compaction. The review's own turns — reading the diff, adjudicating findings, drafting the comment —
land in that same window. On a measured review session the orchestrator side was **40% of the run's
price-weighted cost**, on the caller's tier. That is the single largest line in a review, and it is
avoidable: nothing in Phases 1–8 has to happen in the caller's window.

**So the first question is whether you are the driver.**

- **You were dispatched as a subagent by a caller that named this skill** (`/adw-build` §3.6's
  review driver, `/pr-ready` §3, or an explicit "run `/code-review` as a driver") → **you are the
  driver.** Skip to Phase 1 and run the whole pipeline here. Do not dispatch again; a driver that
  dispatches a driver is a loop.
- **Otherwise — a human or an orchestrator typed `/code-review <args>` in this session** →
  **dispatch one driver and stop.** Launch a single Agent (`subagent_type: general-purpose`,
  `model: sonnet`) with:

  > You are the review driver for `/code-review <the full argument string, verbatim>`.
  > Read `.claude/adw/cache/commands/code-review.md`, `.claude/adw/cache/commands/review-core.md`
  > and `.claude/repo-profile.md` **in full**, then run Phases 1–8 of code-review yourself. You are
  > the driver — do not dispatch another driver. Return **only** the Phase-7 terminal report,
  > verbatim, and nothing else: no preamble, no summary of your own, no recap of what you read.
  > The contract was fetched at `<CONTRACT_SHA>` with `fetch.sh` exit `<0|2>`; on exit 2 the report
  > must carry `⚠ contract from cache, not verified against origin (<sha>)`.
  > End the report with one `Phases:` line — `Phases: 1-8 complete`, or naming every phase that did
  > not run and why (`Phases: 1-8 complete except 5.3 skipped — PR body empty`).

  The caller then **prints the driver's report as its own final message**, unchanged. It does not
  re-derive, re-check or re-summarise any of it — doing so reloads into the caller's window exactly
  what the dispatch removed.

**Sonnet, deliberately.** The driver reads files and works a declared checklist; `adw-core §8` puts
that tier on sonnet. The one step that is not checklist work is the refutation pass, and
**review-core §9 dispatches that on opus from inside the driver** — nested dispatch is routine
(`Skill` and `Agent` calls from inside subagents are counted in the thousands across a machine's
transcripts). Tier the step, not the pipeline.

**`interactive` runs inline — never dispatch it.** `AskUserQuestion` blocks on a human, and a
subagent has no path to one; a dispatched `interactive` run would degrade to the §5 non-blocking
default silently, which is the opposite of what the flag asks for. When `interactive` is set, run
Phases 1–8 in this window.

**The merge gate belongs to the caller, always.** Under a dispatch the driver ends at its report.
The report's `Next:` line invites "merge", and the user replies to the **caller**, which by then has
no driver, no worktree and no state. So the caller owns 7a steps 6–7 — CI check, merge convention,
mergeability, `gh pr merge` — which need none of that state, and the report says so:
`merge gate is mine, not the driver's`.

**Two properties hold whatever the caller is.**

- **The driver is a window, not a reviewer.** It runs the same phases with the same rules and the
  same safety stops. Nothing about `apply`, §7's stops or §8's ship policy changes because the
  pipeline moved — `apply` still authorizes commit+push from inside the driver.
- **The phase ledger cannot survive the dispatch, so the report replaces it.** `review-core §2`
  makes the ledger mandatory because it is *visible to the user*; a ledger created inside a driver is
  visible to nobody, and across this machine's subagent transcripts `TaskCreate` and `TodoWrite` are
  called **zero** times against hundreds of `Agent` and `Skill` calls. The driver's `Phases:` line is
  the only ledger that reaches the human, so it is required, not optional.
- **A dispatch that fails is not a silent light run.** If the Agent call is unavailable or returns
  nothing usable, run Phases 1–8 in this window and say so on the report: `driver dispatch
  unavailable — ran inline`. Never report a review that did not happen.

---

## Phase 1 — Setup

1. **Read [`review-core.md`](review-core.md) and the consuming repo's `.claude/repo-profile.md`**
   end-to-end. The first governs the shared machinery this skill references by section; the second
   holds every repo-specific value it references as `repo-profile §N`. Neither is auto-included —
   `.claude/commands/*.md` are prompt templates with no transclusion, so an unread pointer is a rule
   loaded nowhere.

2. Parse `$ARGUMENTS`. Position 1 = PR number. All later tokens = flags (`light` | `full` | `panel` | `apply` | `interactive` | `since:<sha>`), order-insensitive, case-insensitive. Conflict (more than one of `light` / `full` / `panel`) → error and stop. Duplicate of the same flag → no-op. Resolve `mode` (forced or auto), `apply` (bool), `interactive` (bool), `SCOPE_BASE` (`origin/<baseRefName>`, or `<sha>` when `since:` was given — Phase 2).

3. Fetch PR metadata:
   ```bash
   gh pr view <PR_NUMBER> --json headRefName,baseRefName,title,body,number,url,state,isDraft,headRefOid
   ```
   Eligibility gate — exit with terminal note if `state != OPEN` or `isDraft == true`. If a prior `### Code review` comment exists (`gh pr view <N> --json comments`) AND its body contains the current `headRefOid` short SHA → exit "already reviewed at this SHA"; otherwise warn-only (re-running on a new SHA is legitimate).

4. Store `headRefName`, `baseRefName`, `title`, `body`, `url`. Set `WT=.claude/worktrees/pr-<PR_NUMBER>`.

5. **Worktree + symlink deps → follow review-core §1.1–§1.2** (idempotent add / reset, `git -C "$WT"`, never `cd`).

6. **Phase ledger → follow review-core §2.** Create one TaskCreate per phase below; mark `in_progress` before, `completed` after:
   - `Phase 1 — Setup`  *(Phase 0 precedes the ledger. **The driver creates it; a caller that dispatched one does not** — it runs no phases. review-core §2's "mandatory" binds whoever runs Phases 1–8, and the driver's `Phases:` line is what carries the result out to the human, since a ledger inside a subagent reaches nobody.)*
   - `Phase 2 — Scope`
   - `Phase 3 — Path`
   - `Phase 4 — Review`
   - `Phase 5 — Project checks`
   - `Phase 6 — Triage + self-heal draft`
   - `Phase 7 — Terminal action` (subject: `Phase 7 — Apply remediation` if `apply` set)
   - `Phase 8 — Cleanup`

---

## Phase 2 — Scope

**Default — the whole PR.** `$SCOPE_BASE` is `origin/<baseRefName>`:

```bash
git -C "$WT" diff $SCOPE_BASE...HEAD --name-only
git -C "$WT" diff $SCOPE_BASE...HEAD --stat | tail -1
```

**With `since:<sha>` — the delta only.** `$SCOPE_BASE` becomes `<sha>`, so the review grades
what changed *after* that commit instead of re-grading the whole PR. Everything downstream that computes from the diff
(layers, path score, the 4a agent's diff command, Phase 5's changed-file list) reads
`$SCOPE_BASE`. The **one** thing that cannot is the 4b cloud plugin — its only argument is
a PR number and it always grades `base...HEAD` — so a `since:` pass takes the 4a light path
regardless of tier (4b states the branch). Anything added downstream must be checked
against `$SCOPE_BASE` explicitly; "reads the diff" is not the same as "can be scoped".

Two rules make the narrowing safe:

- **Files, not hunks.** Whatever the diff reports as changed, the reviewer reads those
  files' **complete current contents** — Phase 4a step 3b already requires this for
  handlers/services; under `since:` it binds for **every** changed file. A fix can break
  code it did not edit (PR #751's H2: two locally-correct hunks ~30 lines apart, the second
  made unreachable by the first). Hunk-scoped reading is what misses that class.
- **Never self-selected.** `since:` is passed in by a caller that knows what it already
  reviewed (`/pr-ready` §3 hands it cycle 1's head SHA). A run may not narrow its own scope
  because the diff looked repetitive — a first pass is always the full PR.

Why this exists: an unscoped second pass re-reviews code the first pass already cleared,
and because an LLM pass over identical code returns a different sample of findings, "still
finding things" measures reviewer variance rather than PR instability. The delta shrinks
each cycle; the full diff does not, so only the narrowed form can converge.

Classify changed files by layer **per `repo-profile §13`** — its table maps pattern → layer →
standards doc, and its ignore list says what produces no layer. Do not restate either here.

**`layers[]` is empty ⟺ the diff has no reviewable code** (docs / `.claude` / `.agent`-only, or
nothing but ignored files). Phase 4 and Phase 7 both branch on this, so the emptiness is a computed
result, never a judgement.

**Output**: `changedFiles[]`, `stats` (lines added/removed), `layers[]` (set of touched code-layer names).

---

## Phase 3 — Path

If `mode` was forced (`light`, `full` or `panel`), use it. Otherwise score the diff against
**`repo-profile §14`**. Each row scores at most once.

**`>= 12` → panel. `5`–`11` → full. `< 5` → light.** Three disjoint ranges — evaluate them in this
order and stop at the first match; every score lands in exactly one. The thresholds are the
contract's, not the profile's — a profile tunes which signals score and by how much, never where
the bars sit.
`panel` is a *strict superset* of `full`: everything `full` does still runs, and Phase 4a is the one
thing that changes shape.

> **Why a third rung, and why 12.** Two rungs gave a 3-file handler change and an 89-file,
> 7,000-line change the same instrument: one agent, reading the whole diff serially, hunting
> everything at once. Measured across 133 Phase-4a lanes on one consuming repo, that agent's median
> cost was **$2.07** — but **9% of lanes cost ≥$8, median $18.31, up to $98.32**, and the expensive
> ones are exactly the large diffs. On that tail, splitting the lane three ways is **cheaper** than
> not splitting it, and it finishes in roughly half the wall clock because the three run in
> parallel. On a median PR the split would *add* cost, which is what the threshold is for. `12` put
> 22% of one repo's recent merges above the bar; re-measure on yours and tune the number, never the
> rung count.

> **A `full` score does NOT imply reviewable code exists.** A docs / `.claude` / `.agent`-only PR
> can score into `full` on `.claude` + size points alone (`.claude/commands/` `+3` **plus**
> `>500 lines` `+2` = 5) while `layers[]` stays empty. (`.claude/commands/` `+3` on its own is
> `< 5` → light; it takes the size rows to reach `full`.) Phase 4 gates the plugin on `layers[]`,
> not on `path`.

> **Every profile has one class that no gate reads, and `§14` scores it above the bar unaided.**
> Which class that is differs per repo — `§14` names it and says why. The invariant: a file class
> whose defects are invisible to every compiler, linter and audit must not depend on the diff also
> happening to be large to earn a full review, because that class is typically a handful of lines.
> Its matching `§13` layer row is not optional — without a layer, `layers[]` stays empty, Phase 4b
> skips the plugin as "docs/prose-only diff, no app code to grade", and the score buys nothing.

Log decision:
```
Triage: score=<N> → <light|full|panel>
  <point breakdown>
```

**Output**: `path = "light" | "full" | "panel"`, and **`panelRan = false`** — initialised here, on
every path, because Phase 4b and Phase 6.0 both read it unconditionally and only 4a-panel ever sets
it true.

---

## Phase 4 — Review

Both branches produce a single typed output:
`findings[] = [{file, line, description, severity, originalSeverity}]`.

`originalSeverity` is set equal to `severity` when the finding is created and **never rewritten**.
Only `severity` moves — a `repo-profile §15` upgrade at 4.5, a review-core §9 `OVERSTATED`
downgrade. `review-core §6.6` reads `originalSeverity`, so a finding that was ever `Blocking` keeps
its protection from calibration suppression no matter what later reclassified it.

### 4a — Light path (1 lane)

**On `path == "panel"` and no `since:`, go to 4a-panel below** — its three lanes run **instead of**
this single lane and **alongside** 4b's plugin, which still fires. Nothing else changes. Under
`full` this single lane does not run at all unless 4b falls back to it, so `panel` adds three lanes
rather than replacing one. Under `since:` this lane runs whatever the tier says (4b's delta
bullet): a delta is small by construction and three lanes over it is three agents reading the same
small thing.

Launch 1 Agent (`subagent_type: general-purpose`, `model: sonnet`):

> Review PR #<number> on `<headRefName>` (base: `<baseRefName>`).
> Worktree: `$WT`.
>
> Context: `<paste repo-profile §15's stack context verbatim>`. Weight
> `<paste §15's "weight above style polish" list verbatim>` above style polish.
>
> 1. Read diff: `git -C $WT diff <SCOPE_BASE>...HEAD` (Phase 2 — the PR base by default, or the `since:` SHA on a delta pass; substitute the resolved value)
> 2. Read every standards doc `repo-profile §2` names, from the worktree root.
> 3. Check: bugs, logic errors, convention violations, and every emphasis item §15 listed.
> 3b. **Composition check — read whole files, not only hunks.** `<paste §15's composition-check paragraph verbatim>` Defects *between* hunks are invisible to a hunk-scoped read.
> 4. Ignore: pre-existing code, style nitpicks, missing tests in code that has none today. **Do NOT assume any gate will catch something on your behalf — establish what actually ran before you skip anything.** `repo-profile §9` is the CI coverage table: it says which events trigger a hosted run, which gates that run executes, and which §6-obligated gates it never touches. In a repo with no CI, or on a PR whose shape §9 excludes, `gh pr checks` reports **no checks — absent, not red**, and re-deriving type or lint errors is the only evidence that will exist. Where a run does exist, confirm it actually executed: `gh run view <id> --json jobs` — a gated-off job reports `skipped` with an empty `steps` array, which looks like a failure and is neither.
> 5. Return findings as a single fenced JSON block (` ```json `): `[{"file": "...", "line": 42, "description": "...", "severity": "Blocking"}]`. Severity ∈ `Blocking|Warning` — apply `repo-profile §15`'s Blocking severity classes, the silent-data-corruption entries included. No prose outside the block — only the JSON array.
> 6. Empty list → return `` ```json\n[]\n``` ``.

The parent skill extracts the fenced JSON block via `awk '/^```json$/,/^```$/'` (or equivalent) and parses it into `findings[]`.

Light path **does not post a PR comment**. Comment (if any) is posted by Phase 7.

### 4a-panel — Panel path (3 lanes, parallel)

Used when `path == "panel"` and no `since:` (Phase 3). It **adds** three lanes alongside 4b's plugin;
it does not replace anything under `full`, where 4a never ran. Set `panelRan = true` before
dispatching, so 4b's fallback can see it.

**A panel is only as deep as what it is obliged to check.** A lane asked to "hunt failures" produces a
category sweep unless something tells it *which* failure to hunt. Two inputs do that, and the first is
mandatory:

#### Step 1 — Match the structural checks (mechanical, mandatory)

Take **every `repo-profile §16.4` check** and test its trigger against the diff — each check names
its own trigger ("for a replace-array endpoint", "for a model-output write path", …). Every check
whose trigger matches is **assigned to the lane that owns the matching files** (per `§19`) and pasted
into that lane's prompt verbatim. **A matched check is an obligation, not a hint**: the lane must
return a verdict on it. **Phase 5.3 still runs the full `§16.4` list on every tier, `panel` included —
that is the floor and it never narrows (see 5.3).** This assignment is the added depth on top of it:
each matched check also gets an owner reading whole files, instead of one agent sharing its attention
across all of them.

This step is what turns a `§15` severity class into a detection. A severity line only upgrades a
finding that something already produced; with no detector behind it, it has nothing to upgrade.
**`repo-profile §15` classes are expected to name the `§16` row or `§16.4` check that detects them**,
and a class that names none is a convention finding (Phase 6.2), not a class the panel can enforce.

#### Step 2 — Read the diff, then derive the questions (bounded)

The driver reads `git -C "$WT" diff $SCOPE_BASE...HEAD --stat` and the **diff hunks of the six
non-test source files with the most added lines** — not whole files; the lanes read those. From that,
write **3–5 numbered questions per lane** that each hypothesise one specific failure in *this* diff,
naming the file and the input. "Can a row inserted by the background path between mount and Save be
deleted by the PUT in `handlers/x.ts`?" is a question. "Check for bugs" is not. The questions
**supplement** the Step-1 checks; they never replace one.

**Never put a suspicion's answer in a question.** "Check whether X is broken — it probably is,
because Y" returns Y and reads as confirmation, while the lane's independent work proves nothing.

#### Step 3 — Dispatch

**Launch 3 Agents in ONE message** (`subagent_type: general-purpose`, `model: sonnet`) so they run
in parallel.

| Angle | Owns | Reads |
|---|---|---|
| **A — correctness & data integrity** | every changed file in the layer with the most added lines, plus its tests | that subsystem end to end |
| **B — authorization, persistence, concurrency** | the `layers[]` entries `repo-profile §19` maps to this angle | those files plus the convention docs `§2` names |
| **C — architecture, coupling, scope** | the whole diff, `git -C "$WT" log $SCOPE_BASE..HEAD --oneline`, and the PR `title` + `body` | structure, not hunks |

**Every `layers[]` entry must reach a lane that READS it.** Angle C reads structure, not hunks, so it
is not a reading owner. Compute the assignment, then check the cover: **any layer claimed by neither
A nor B goes to A**, whatever its size. Without that rule a frontend layer in a mixed diff is owned by
nobody who reads it, and `§15`'s frontend items (`ui_standards`, TanStack keys, SSE cleanup) reach no
lane — silently, because each lane's own scope looks complete. Same reason `§15`'s emphasis list is
pasted **whole** into every lane instead of filtered to "the items that apply to your layers": that
filter is a judgement made before anyone has read the code, and it drops precisely the items whose
layer was mis-assigned.

**`repo-profile §19` owns the layer→angle map and this repo's per-angle file patterns** — the table
above deliberately names no layers, because a copy here would be a drift pair with the profile and
no gate on either side. Where a repo carries no `§19`, derive: angle A takes the largest-added-lines
layer, angle B takes every `layers[]` entry `§13` maps to a backend/auth/schema standards doc, angle
C takes everything — **and carry `repo-profile §19 absent — lanes derived` into Phase 7's `👍 OK`
bucket**, so a missing map is visible rather than silently approximated.

Hand each agent this prompt, substituting its own row:

> You are reviewing PR #<number> on `<headRefName>` (base: `<baseRefName>`), in the worktree `$WT`.
> Context: `<paste repo-profile §15's stack context verbatim>`.
>
> **YOUR ANGLE — <angle name>.** You own: `<the owned file list>`. Other lanes own
> `<the other two angles, named>`; follow a call chain into their files when you need to, but do not
> review them. **Do not re-run grep-shaped or lint-shaped checks** — a separate pass greps the diff
> for those. Everything that needs *reading and reasoning* on your files is yours, including:
> `<paste repo-profile §15's "weight above style polish" list IN FULL — do not pre-filter it>`.
>
> **Structural checks assigned to you — each needs a verdict:**
> `<paste each matched §16.4 check verbatim, or "none matched">`
>
> **Questions for this diff:**
> `<paste this lane's 3–5 derived questions>`
>
> 1. `git -C $WT diff <SCOPE_BASE>...HEAD --stat`, then read the **whole current contents** of every
>    file you own — not hunks. Two locally-correct hunks in one file can break each other.
> 2. Read the standards docs `repo-profile §2` names, from the worktree root.
> 3. **Hunt a reachable failing input.** For each risk, name an input or sequence a real user or
>    client can produce, and follow it to the consequence. A risk you cannot reach is not a finding.
> 4. **Do NOT assume a gate covers anything.** `repo-profile §9` is the CI table; "no checks" is
>    absent, not green.
>
> Output, in this order and nothing else:
> A. `VERDICT:` one line — `<the angle's verdict vocabulary>` — plus 3–5 sentences a non-specialist
>    can follow. Pick one and defend it.
> B. `CHECKS:` one line per assigned structural check — `holds` · `violated: <file:line>` ·
>    `not reachable here: <why>`. Every assigned check gets a line. None assigned → `none`.
> C. `WHAT IT DOES WELL:` up to 4 bullets, each naming a file.
> D. `FINDINGS:` a single fenced ```json block — `[{"file","line","description","severity"}]`,
>    severity ∈ `Blocking|Warning` per `repo-profile §15`'s Blocking classes. Every `violated` check
>    is also a finding here. Empty array if none. No prose outside the block.
> E. `SCOPE:` diff regions the PR body never accounts for, or `none`. (Angle C only.)
>
> Cite `file:line` for every claim. Do not pad. Do not run gates.

**Verdict vocabularies** (three values, no middle): A — `safe to ship unreviewed` / `risky but
bounded` / `should not ship as is`. B — `sound` / `has a gap` / `unsafe`. C — `good` / `acceptable` /
`should be better`.

#### Step 4 — Parse

- Extract each lane's fenced JSON and concatenate into `findings[]`. **Dedupe on `(file, line,
  rule-class)` with the HIGHER severity winning** — the same rule Phase 5.2 states for its own
  dedupe. The lanes overlap at the edges by design, so this is exactly the case it exists for: in
  concatenation order, angle A's `Warning` on a line would otherwise silently drop angle B's
  `Blocking` on the same line.
- **An assigned check with no `CHECKS:` line is `unanswered`**, and each one prints in Phase 7 as
  `<check> assigned to lane <X>, no verdict returned`. An obligation that can be skipped silently is
  not an obligation.
- Keep every lane's `VERDICT:` line and every `not reachable here` verdict — **review-core §9 attacks
  them**. A verdict nothing reads is decoration.
- Angle C's `SCOPE:` block becomes one `Warning` naming the unaccounted regions, or nothing.
- **Record the matching itself**, and carry it into Phase 7's `👍 OK` bucket as
  `§16.4: <N> of <M> checks matched and assigned, <K> answered`. Without it a driver that matched
  **zero** checks — because Step 1 was skipped, or the triggers were read carelessly — produces a
  report byte-identical to a diff that legitimately matched none, and the step that the whole panel
  design rests on cannot red. The unanswered-verdict line below only covers checks already assigned,
  so it cannot see a match that never happened. Same reason the `§19 absent` line exists.

The panel **does not post a PR comment** — Phase 7 does.

### 4b — Full path

**Plugin gate (WS3).** The cloud plugin grades **app code** — on prose/docs it is pure noise. Fire it **only if `layers[]` is non-empty** (reviewable code present, Phase 2) **and `since:` was not given**:

- **`layers[]` empty** (docs / prose / skill-only diff that nonetheless scored `full` on size/`.claude` points, or was forced `full`) → **skip the plugin, and run the 4a light lane instead**, set `pluginRan = false`, and log: `Full path, plugin skipped: no app code — diff graded by the 4a lane.` Phase 5 project checks still run; Phase 7 must not assume a plugin comment exists.

  > **Why not `findings = []`.** The plugin is right to skip prose — it grades app code and adds only
  > noise to a markdown file. But skipping the plugin is not the same as skipping the review, and
  > treating them as one inverted coverage on exactly the files with the widest blast radius: a
  > *small* contract edit scores below `full` and takes the light path, whose diff agent has no
  > `layers[]` gate, so it was read; a *large* one scored into `full` on the size rows and was read by
  > nothing. The bigger the change to what every future agent run obeys, the less of it was reviewed.
  > The 4a lane reads files and judges them against the standards docs, which is what a prose diff
  > needs.
- **`since:` given** (a delta pass — `/pr-ready` §3 cycle 2) → **skip the plugin and take the 4a light path instead**, set `pluginRan = false`, and log: `Full path, plugin skipped: delta pass (since:<sha>) — plugin cannot be scoped.` The plugin's only argument is a PR number: it always grades `base...HEAD`, so firing it here would re-review the whole PR and reinstate the non-convergence `since:` exists to remove — silently, because the tier says `full` and a plugin comment would duly appear. The light agent takes `$SCOPE_BASE` and is the correct instrument for a delta, which is small by construction. **`since:` also collapses `panel` to the single 4a lane** for the same reason: three angled lanes over a delta of a few hundred lines is three agents reading the same small thing.
- **`layers[]` non-empty and no `since:`** → invoke `Skill` tool `code-review:code-review` with args `<PR_NUMBER>`, set `pluginRan = true`. The plugin runs its multi-agent review and posts its own PR comment. Then run **4.5 — Parse plugin findings**.
- **The invocation is unavailable, errors, or returns without a new `### Code review` comment
  appearing** → set `pluginRan = false` and log
  `Full path, plugin unavailable — falling back to <4a | already-run panel>`. Then, **only if
  `panelRan == false`**, run the 4a lane so the diff is still graded by something; when
  `panelRan == true` the three lanes have already graded it and a second dispatch is six sonnet
  agents for one diff, masked by the dedupe — the layer-cover rule above is what makes that safe,
  since every layer has already reached a reading lane. Carry `plugin unavailable — diff graded by <N> local
  lane(s)` into Phase 7's `👍 OK` bucket.

> **Availability is established, never asserted.** The check is mechanical and it is the *attempt* —
> invoke, then re-read the PR's comments (4.5's `gh pr view` call) and see whether a new one landed.
> A run may not state that the plugin is absent, installed, or working without having tried it this
> run. This matters because the failure is silent in exactly the wrong direction: without the
> fallback bullet a missing plugin lands in the `layers[] non-empty` branch, `findings` stays empty
> because nothing graded the diff, and Phase 7 still prints the tier as `full`. The report then
> claims a multi-agent review that never happened. Observed on a real 7,000-line PR, three cycles
> running.

### 4.5 — Parse plugin findings (only when `pluginRan`)

```bash
gh pr view <PR_NUMBER> --json comments \
  --jq '.comments | map(select(.body | startswith("### Code review"))) | .[-1].body'
```

Parse the comment body (format is stable):
- Lead: `Found N issue(s):` — singular for N=1, plural otherwise (or `No issues found.`)
- Each issue: numbered list item `N. <description>` + blank line + permalink `https://github.com/.../blob/<sha>/<file>#L<a>-L<b>`.
- Emit each item as `{file, line, description, severity}` (line = `lineStart` from the permalink range; range end discarded).
- Default `severity: "Warning"`. Upgrade to `"Blocking"` per **`repo-profile §15`**'s Blocking
  severity classes — that list is the repo's, and it is not restated here.

  > Every profile's list closes with its own **silent data corruption** entries — the class that
  > reaches no crash reporter and no gate. Only `Blocking` is protected from calibration suppression
  > (`review-core.md` §6.6) and from unilateral rejection by the fixer, so a severity list that omits
  > a repo's worst historical class silently de-prioritises exactly what review exists to catch. If
  > you find such a class missing from `§15`, that is a convention finding (Phase 6.2), not a
  > reason to grade it `Warning` here.

Plugin posted "No issues found" → `findings: []`.

**Output (both branches)**: `findings[]` + `pluginRan` (bool).

---

## Phase 5 — Project-specific checks

Plugin / light agent covers general quality. This phase appends project-specific findings to the same array.

### 5.1 — Audit gate

```bash
git -C "$WT" status --short  # sanity
```

**`repo-profile §5` declares whether this repo has an audit-style gate, and the exact review-side
invocation if so.** Run it as written. Each failure → a finding with severity `Blocking`: an audit
encodes absolute rules, not preferences.

**Where `§5` says the repo has none, say so** — `audit: none in this repo` — and rely on §5.2's
rule tables, which are then the entire automated-convention surface. Never report a green for a
gate that does not exist.

### 5.2 — Convention checks (single sub-agent)

Spawn 1 Haiku agent. Hand it: worktree path, `changedFiles[]`, and **`repo-profile §16.1`–`§16.3`
verbatim** — the repo's rule tables. The agent runs each check against changed files only and
returns findings `{file, line, description, severity}` where severity ∈ `Blocking|Warning`.

Append to `findings[]`. **Dedupe across all sources** (audit first, then light agent + plugin parse
+ this phase): drop later entries where `(file, line, rule-class)` collides with an earlier entry.
**Audit goes first, and on a collision the HIGHER severity wins** — audit findings are always
`Blocking`, so a light-agent `Warning` on the same line would otherwise suppress a `Blocking`
silently. Rule-class for Phase 5 entries = the rule number from `§16`; for upstream entries, infer
from the description.

The tables live in `repo-profile §16.1`–`§16.3`, grouped by layer. Do not restate them here and do
not invent rows: a rule the profile does not carry is a **convention finding** (Phase 6.2), not a
finding you grade on the spot.

### 5.3 — Structural checks (sub-agent verification, not grep)

Spawn 1 Sonnet agent to verify cross-file and syntactic rules that a grep cannot express.

**Intent coherence** (always — hand the agent the PR `title` + `body` from Phase 1, **and** the
output of `git -C "$WT" log $SCOPE_BASE..HEAD --oneline` and `git -C "$WT" diff $SCOPE_BASE...HEAD --stat`):
- Does the diff actually do what the PR says? Flag only a real mismatch: the stated goal is
  half-implemented (promises X, ships part of X), the diff carries stray changes unrelated to the
  stated goal, or the approach plainly can't achieve the stated goal. This is a *coherence* read,
  not a style/bug pass — one finding per mismatch, severity `Warning`, `description` naming the
  intent gap. **Phase 6 adjudicates the routing** (a scope mismatch is a genuine "is this the
  intended scope?" escalation; a clear small omission is a toFix) — don't pre-route here.
- **Account for every commit.** Return one verdict per commit — `accounted` or
  `unaccounted-by-the-body`. A commit whose subject names work the body never mentions is
  `unaccounted`, **however well-argued the body is**. Report the unaccounted set as ONE `Warning`
  naming them, not one finding per commit.
- Skip the *mismatch* half silently — no finding, no note — when the diff plainly matches the body,
  or when the body is empty/`title`-only. **The per-commit accounting never skips**: an empty body
  means every commit is unaccounted, which is itself the finding.

> **Why the commit list, and why "however well-argued".** The old instruction was "skip silently
> when the diff plainly matches the PR body", against a body the author wrote to argue the PR is
> correct. Agreeing is cheaper than checking, and the check could only ever notice a
> *contradiction* — it was structurally unable to notice an *omission*, because an omission looks
> exactly like a body that matches. A commit list either covers a commit or it does not, which is
> the same question with a mechanical answer. Observed: a 17-commit PR whose ~2,300-word body never
> mentioned 14 of them, including the largest single addition in the diff.

**Everything else: hand the agent `repo-profile §16.4` verbatim — on EVERY tier, `panel` included.**
That section is the repo's list of per-trigger structural checks ("for a new endpoint…", "for a new
migration…"), and it is not restated here. Run the entries whose trigger the diff matches; report the
rest as not applicable.

> **`panel` does not move this step, it doubles it — deliberately.** 4a-panel Step 1 also matches
> `§16.4` triggers and assigns each match to the lane that owns those files, so on a panel run a
> matched check is answered twice: once by a lane reading whole files (depth), once here (floor).
> **This phase is the floor and it never narrows.** 4a-panel's matching is a judgement about which
> lane owns which files, and a judged match that misses leaves the check unrun — which would make
> `panel` *narrower* than `full` for `§16.4`, the inverse of the strict-superset property Phase 3
> claims. The duplicate costs one Sonnet pass; dropping the floor costs the detection the whole
> panel design rests on. If the two disagree, the finding stands: report both and dedupe on
> `(file, line, rule-class)` with the higher severity winning.

Intent coherence stays in this file rather than in the profile because it is a property of *pull
requests*, not of a stack — it reads the PR body against its own diff and needs no repo knowledge.

**Output**: `findings[]` extended with project-specific entries.

---


## Phase 6 — Triage + self-heal draft

### 6.0 — Refutation (gated) → review-core §9

**Run it when `panelRan == true`** — computed, never judged, and gated on the *lanes having run*
rather than on `path`, because a `since:` delta collapses `panel` to one lane without clearing
`path` and must not pay for a refuter. Follow **review-core §9**: dispatch **one agent on the top tier in `adw-core §8`'s tier
table — never the driver's own tier** (two when `Blocking` > 4) with the bare claims — never the
lanes' reasoning — apply the verdicts (`REFUTED` → not applied, still reported; `OVERSTATED` →
re-severitise while keeping the original severity pinned for §6.6; `CONFIRMED` → unchanged), and
fold any new findings it surfaced into `findings[]` before triaging — including every **refuted
negative**, which is a violation a lane claimed was absent and is graded by `repo-profile §15` like
any other finding, not filed under coverage. **A downgrade rewrites `severity` only**; §6.6 keeps
reading `originalSeverity`. With no `Blocking`, the claims
are the lanes' verdicts and their `holds` / `not reachable here` checks (§9). Log one line per
verdict. `panelRan == false` → skip silently.

Findings array is now complete. **Read `.agent/review-calibration.md` from the main-repo working tree (review-core §6.1/§6.3 — resolve `$MAIN_REPO`, never `$WT`) before triaging** — when a finding matches a recorded class, bias the adjudication accordingly and note `per calibration: …` in the log. The hard guard binds (§6.6): an `apply`-direction calibration line never suppresses a `Blocking` finding or a blast-radius class.

### 6.1 — Action triage

**Adjudicate every finding per review-core §3** (apply / escalate / reject). code-review's routing labels:

| Bucket | Criteria |
|---|---|
| **toFix** (§3 *apply*) | All Blocking findings |
| **toFix** (§3 *apply*) | Warnings where the fix is small (≤2 files unrelated to the original feature) AND value is real — an audit catch, or any `repo-profile §16` row whose fix is a line or two with an obvious insertion point |
| **escalate** (§3 *escalate*) | Only what clears the **§3.1 bar** — *both* gates (under-determined by the repo · two defensible answers), and neither resolution rule disposes of it (cheap+reversible → do it with an undo offer; out of scope → reject). Typically zero per review; >2 means the bar wasn't applied — re-adjudicate |
| **reject** (§3 *reject*) | Not worth it / already covered — terse reason |

**The decide-or-escalate pass IS review-core §3, applied over the triage output** (not a separate step): before any finding stays an escalation, run it through the **§3.1 bar** — fail either gate, or fall to either resolution rule, and it is a `toFix` (applied in `apply` mode subject to the §7 stops; surfaced as a recommended fix in review-only mode) or a `reject`. Most "your call" items resolve to `toFix`.

**Specifically, these are NOT escalations — decide them:** which of two correct fixes is cleaner (pick one, note the other in the commit); whether a Warning is worth fixing (apply if small, reject if not); whether a convention you can read in one of `repo-profile §2`'s standards docs applies (read it); whether to fix something cheap and reversible (fix it, and say `— say "revert <x>" to undo`); whether a nice-to-have belongs here (reject: "out of scope — file it").

**Never present findings as a chooser/menu** — an `AskUserQuestion` "which should I fix?" or a numbered "pick one" list IS handing the user a raw list (§3). Adjudicate each finding yourself. A pure-Warning / zero-Blocking result normally means *apply the real ones, reject the rest* — not *ask which to apply*. Escalate ONLY genuine product/UX/business/operational calls, and only via the §5 surface (`AskUserQuestion` solely under `interactive`).

Log decision per finding:
```
Triage:
  [toFix]     <file>:<line> — <the §16 rule it violates> → <the fix>
  [escalate]  <file>:<line> — <what must be decided> (recommend: <default>)
```

### 6.2 — Convention update draft (§3 convention/lesson sub-case)

Look across `findings[]` for a pattern worth documenting. A candidate exists when **either** a generic anti-pattern repeats across the diff, **or** a single-instance anti-pattern is generic enough that recurrence is likely (grep-detectable, applies to any future handler/component).

**Adjudicate each candidate per the review-core §3 convention/lesson bar** — surface a **verdict + recommendation**, never a raw suggestion:

1. **Pick the target doc per `repo-profile §17`** — it maps the finding's surface to the doc that owns the rule. A repo with one numbered lessons list routes almost everything there; a repo with per-domain standards docs splits by layer. §17 says which this is.
2. **Grep the target doc first.** Already covered → `[Reject]`, cite the existing entry. Never restate an existing rule.
3. **Argue both sides against the §3 bar** (generic · detectable/teachable · recurrence-likely · not-covered · worth-its-weight · not-preference). Miss one → `[Reject]`, naming the failed criterion. On the fence → default `[Reject]`.
4. **Compose only the winners** — for an `Insert`, draft the entry (short rule + ✅/❌ snippet + ref, matching the target file's verbosity).

Output each as a one-line verdict:
- `[Insert → <target file>]` <one-line rule> — <the ≤1-line rationale that cleared the bar>. *(draft entry below)*
- `[Reject]` <pattern> — <failed criterion>.

**Never auto-apply, even with `apply`** (review-core §3 — learning-doc edits need human sign-off; §7 lists these paths as blast-radius stops). Surface `Insert` drafts + a terse `Reject` list; the user approves an `Insert` to land it.

**Output**: `{toFix[], escalate[], conventionEdits[]}`.

---

## Phase 7 — Terminal action (branched on `apply`)

Phase 7 always runs.

### Output contract (every Phase-7 surface)

**The reader has 5 seconds.** The buckets tell them what happened; the closing `Next:` line — the last thing on screen — tells them what to do. Structure, in this exact order:

1. **Header** — `PR #<N>: <title> (<url>)`. One line.
2. **✅ Done** — concrete actions taken this run (fixes committed + pushed, comment posted, PR merged). In review-only mode (no `apply`) this bucket is titled **🔧 To fix** instead, and lists the clear-answer findings (every Blocking + high-ROI Warning) as `file:line — fix`.
3. **👍 OK** — reviewed and green, no action. **One line by default** — the §4 verification result. Add a named surface only when a reader would be surprised it passed; never enumerate what you checked.
   - **A gate that did not run is not an `👍 OK` line.** Where `repo-profile §6` obligated a gate for
     this diff and it could not run — no daemon, no database, no browser — it goes under **⏳ Your
     decision** as its own line (`<gate> not run: <why> — obligated by §6 for this diff`) **and it
     appears in the `Next:` line**. `👍 OK` means *reviewed and green*; filing a gate that never
     executed there inverts the one caveat the reader most needs.
   - **CI always prints, in one of two forms, never silence**: `CI: <job> green` / `CI: <job> RED` /
     `CI: not requested — <why, per repo-profile §9>`. An absent CI run is not a failure and not a
     pass; it is a coverage fact, and omitting it lets green local gates read as full coverage.
   - These two lines are **exempt from the one-line-per-item and ~15-line limits below**. That
     pressure is what pushes them into prose under the buckets, where nothing is read.
4. **⏳ Your decision** — the ONLY bucket that needs the human: escalations that cleared the **§3.1 bar**, each **one plain sentence + a recommended default**, plus convention `Insert` drafts (never auto-landed — need sign-off).
   - **Coverage gaps go in their own labelled sub-block and are NOT counted in `<M>`**: an unrun
     obligated gate, a `§16.4` check assigned to a lane that returned no verdict, and a refuted
     `Blocking`. They are mechanically generated and cleared no §3.1 bar, so counting them there
     inflates the number §3.1 reads as evidence the bar was skipped (*">2 almost always means the
     bar wasn't applied"*) — on a mixed diff obligating three unrunnable gates, the count alone
     would push a reviewer to drop real escalations. Label it `— coverage` and keep `<M>` for
     genuine decisions.
5. **`Next:` line (LAST)** — **the single most important line in the report, placed last so it is what stays on screen.** One sentence naming the ONE thing the user does now, or that nothing is needed. It is a *directive*, not a summary. E.g. `Next: nothing — 3 fixes pushed, CI green. Say "merge" to ship.` / `Next: answer the 1 decision above, then re-run with apply.` / `Next: fixes pushed, but CI is red on <job> — not mine, look before merging.` If **⏳ Your decision** is empty and gates are green, `Next:` always resolves to a merge invite or `nothing`.

**Hard limits.**
- **The report IS the final message.** Not a block embedded in a summary — the header is the first line the user sees and the `Next:` line is the last. No preamble ("I've finished reviewing PR #742…"), no recap of what you did, no closing offer ("let me know if you'd like…"). Prose wrapped around the buckets is the verbosity, even when the buckets themselves are tight.
- **One line per item.** No sub-bullets, no nested detail, no evidence dumps. An item needing a paragraph to justify gets its paragraph in the PR comment or the triage log; the report gets its one line.
- **~15 lines total.** Longer than a screen has failed regardless of structure.
- **No diagnostics** — path/score, plugin state, layers, phase narration, findings counts, and the rejected list stay in the triage log. Never in the report.
- Every bucket prints its header even when empty (`— none`; *Your decision*: `— none`).
- The `Next:` line is the final line of the report; nothing follows it. **Two** things are allowed between the last bucket and the `Next:` line, each one plain line: a calibration line recorded this run (§6.4 requires the echo) — `Calibration recorded: <line> — delete if wrong` — and, when the run was dispatched into a driver (Phase 0), the `Phases:` line that replaces the ledger — `Phases: 1-8 complete`, or naming every phase that did not run and why. Nothing else.

### 7a — `apply` set

**`apply` is the commit+push consent → review-core §8 declared auto-ship.** Step 4 (commit + push) runs automatically once §4 verification is green — no gate, no "shall I push?" (step 5's comment follows it). **The merge (steps 6–7) is NOT covered**: only the explicit word "merge" (or the Merge option under `interactive`) authorizes it. A declared no-browser skip routes visual QA to the human and blocks only the merge, never the apply/commit/push. A §7 safety stop overrides all of this → fall back to comment-only (7b) and say why.

1. **Apply fixes** in `$WT`. **If `toFix` is empty** (a clean PR run with `apply`): skip steps 1–5 (an empty index would make `git commit` error), and go straight to the merge gate (steps 6–7); if any §7 blast-radius path or unresolved escalation is in play, fall back to the review-comment path (7b) instead. For each `toFix`: edit, then re-run the relevant Phase 5 detection to confirm the violation is gone. If a fix balloons in scope, re-adjudicate it to *escalate* and note why.

2. **Verify → review-core §4** (smart verification — branches on `layers[]`). Run from inside the worktree; each gate must pass with zero errors before push. **A docs / `.claude` / `.agent`-only remediation reports `verification: N/A — docs-only` (§4) — never a fabricated green.** Any failure → safety stop (§7).

3. **Browser smoke (UI changes only) → review-core §4.** If `toFix` touched `src/`, click the affected flow, or (when no browser is available) declare the skip and add "human visual QA required" to the merge gate — never let the missing browser block the apply/commit/push.

4. **Commit + push → review-core §1.3.** Stage exactly the touched files, commit, `git -C "$WT" push origin HEAD:<headRefName>`. **Unconditional once step 2 is green** — `apply` already authorized it (§8).
   ```
   fix(review): apply code-review remediation

   Address blocking findings + high-ROI warnings from /code-review.
   See PR comment for full triage.

   Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
   ```
   **Re-runs are normal.** A later `/code-review <N> apply` on the same PR produces a **new** commit + push — never amend, never force-push (§1.3). Before pushing, re-check `headRefOid` against the SHA read in Phase 1; a mismatch means the branch moved under you → re-fetch and rebase (`--force-with-lease` rejection = safety stop, §7).

5. **Post review comment** (new comment, not edit) — the §Output-contract buckets:
   ```
   ### Code review — remediation

   **✅ Done** (<N>) — pushed as <short-sha>
   - file:line — what changed

   **👍 OK**
   - Verified: <§4 result — one field per obligated gate, named as `repo-profile §5` names it, OR "N/A — docs-only, no code gates apply">
   - CI: <job green | job RED | not requested — why, per repo-profile §9>

   **⏳ Your decision** (<M>) — cleared the §3.1 bar; everything engineering-clear is in Done
   - file:line — one plain sentence of what to decide + recommended default
   - `[Insert → <target file>]` <one-line rule> — convention draft, needs your sign-off (not auto-landed)

   **⏳ Coverage** — mechanically generated, NOT counted in <M>
   - <gate> not run: <why> — obligated by repo-profile §6 for this diff
   - <§16.4 check> assigned to lane <X>, no verdict returned
   - refuted: <file:line> <claim> — <named guard / why unreachable>
   ```
   Then, **only if** a calibration line was recorded this run (§6.4), append one final line to that comment body: `Calibration recorded: <echoed line> — delete from .agent/review-calibration.md if wrong.` — omit it entirely otherwise.

6. **Pre-merge checks.** These gate the **merge only** — the remediation is already pushed (step 4).
   - CI: `gh pr checks <N>` — failing → **merge stop, not a push stop** (§7): keep the push, skip the merge gate, and make the failing job the report's `Next:` line.
     **Read `repo-profile §9` before interpreting the result.** "no checks reported" means CI was *not requested* or does not exist — **not** *failed* — and is never a merge stop. §9 also names any standing condition that reds a run for reasons that are not the code, and how to confirm it (`gh run view <id> --json jobs`, not the rollup).
   - Merge convention: `repo-profile §3` declares it. Confirm against the base's own history rather than trusting either — `git -C "$WT" log --format='%P' origin/<baseRefName> | head -5` (the PR's actual base, never a hardcoded branch name): 1 SHA/line = squash (`--squash`); 2 SHAs = merge (`--merge`).
   - Mergeability: `gh pr view <N> --json mergeable,mergeStateStatus`.
     - `MERGEABLE` + `CLEAN` → proceed.
     - `UNKNOWN` → GitHub is still computing mergeability. Re-query with a **non-foreground** wait (the harness Monitor/until pattern) — never a foreground `sleep` loop (blocked in some environments) — until it resolves or a bounded number of attempts pass; if still `UNKNOWN`, soft-stop and ask to re-run the merge once GitHub settles.
     - `CONFLICTING` → likely upstream squash. Rebase + `--force-with-lease`; conflict or lease rejection → safety stop.

7. **Confirm + merge → escalation surface per review-core §5.** The merge confirmation is an escalation of the "ship it?" decision — and **it is the report's `Next:` line, not a second block.** Do not print a separate "Ready to merge" panel restating what the buckets already show; that duplication is the verbosity the Output contract exists to kill.
   - **Default (no `interactive`)** → the `Next:` line carries the whole gate, in one sentence, naming any caveat: `Next: nothing — <N> fixes pushed, gates green. Say "merge" to squash into <base>.` / `Next: say "merge" to ship (visual QA not run — no browser; eyeball <flow> first).`
   - **`interactive` set** → surface via `AskUserQuestion` (recommended default first-listed).
   On confirm: `gh pr merge <PR_NUMBER> $MERGE_FLAG --delete-branch`. Never force-merge, never bypass branch protection.

**Safety stops (apply branch) → review-core §7.** Two tiers:
- **Stops the push** (fall back to "post review comment + leave PR open", nothing committed): unfixable Blocking, failed §4 verification, undeclared skipped browser check, blast-radius path touched, `--force-with-lease` rejected.
- **Stops only the merge** (the remediation still commits + pushes): failing remote CI, declared browser skip, an unresolved escalation.

Document the stop reason in the Remediation comment **and** in the report's `Next:` line.

### 7b — `apply` not set

Inputs: `toFix[]`, `escalate[]`, `conventionEdits[]` (all surfaced in the comment — neither push nor merge runs). **Escalations follow review-core §5** (default: the "Your decision" block below; `interactive`: `AskUserQuestion`).

**Light path** — post review comment (the §Output-contract buckets; review-only ⟹ first bucket is **🔧 To fix**):
```bash
gh pr comment <PR_NUMBER> --body "$(cat <<'EOF'
### Code review

**🔧 To fix** (<n>) — clear-answer findings; re-run with `apply` to apply
- **[Blocking]** file:line — finding — convention ref
- **[Warning]** file:line — suggestion

**👍 OK**
- Checked <the repo-profile §2 standards docs>, <the §5 audit gate, or "no audit gate in this repo">, the §16 rule tables, and the §16.4 structural checks.

**⏳ Your decision** (<n>) — genuine product/operational calls only
- file:line — one plain sentence of what to decide + recommended default
- `[Insert → <target file>]` <one-line rule> (convention, needs sign-off)  ·  `[Reject]` <pattern> — <failed criterion>

**⏳ Coverage** — mechanically generated, not counted in (<n>)
- <gate> not run: <why> — obligated by repo-profile §6  ·  <§16.4 check> unanswered  ·  refuted: <file:line> — <guard>

Generated with [Claude Code](https://claude.ai/code)
EOF
)"
```

No findings → collapse to the OK + empty-decision buckets: `### Code review` / `**👍 OK** — no issues. Checked <the same list as above>.` / `**⏳ Your decision** — none.`

**Full path** — branch on `pluginRan` (Phase 4b):
- **`pluginRan == true`** — plugin already commented. Post a follow-up **only if** Phase 5 found additional project-specific issues OR a convention update is being suggested OR there are escalations — same buckets, dropping any that are empty:
  ```
  ### Code review (project supplement)

  **🔧 To fix** (<n>) — <additional Phase 5 findings; re-run with `apply`>
  **⏳ Your decision** (<n>) — <escalations (plain sentence + recommended default) + convention Insert drafts>
  **⏳ Coverage** — <unrun obligated gates · unanswered §16.4 checks · refuted Blockings — not counted in (<n>)>

  Generated with [Claude Code](https://claude.ai/code)
  ```
  Phase 5 clean + no convention updates + no escalations → no comment (plugin's review stands).
- **`pluginRan == false`** (docs/prose-only diff that scored `full`, plugin skipped in 4b) — **there is no plugin comment.** Post the project-checks comment as the **primary** review (the Light-path template above), noting `Plugin skipped: no app code to grade.` Do not reference a nonexistent plugin comment.

### Terminal report (both branches)

Always print to terminal in the §Output-contract shape — header, then the three buckets, then the closing `Next:` line as the final line (each bucket header always prints, even empty). One line per item, ~15 lines total, no diagnostics, no prose outside the buckets:
```
PR #<N>: <title> (<url>)

## ✅ Done (<n>)      ← review-only mode: "## 🔧 To fix (<n>) — re-run with `apply`"
- <file:line — what changed, and that it's pushed>   |   — none

## 👍 OK
- Verified: <§4 result>
- CI: <job green | RED | not requested — why (repo-profile §9)>

## ⏳ Your decision (<n>)
- <file:line — one plain sentence + recommended default>
- `[Insert → <target>]` <one-line rule> — convention, needs sign-off
   |   — none

## ⏳ Your decision — coverage (not counted above)
- <gate> not run: <why> — obligated by repo-profile §6
- <§16.4 check> assigned to lane <X>, no verdict returned
- refuted: <file:line> <claim> — <named guard / why unreachable>
   |   — none

Phases: 1-8 complete
Next: <the ONE thing the user does now — or "nothing" + why>
```
Worked example (the common case — clean apply run):
```
PR #742: <title> (https://github.com/…/742)

## ✅ Done (2)
- <file>:<line> — <what changed> · pushed (a1b2c3d)
- <file>:<line> — <what changed> · pushed (a1b2c3d)

## 👍 OK
- Verified: <one field per obligated gate — this repo's names, from repo-profile §5> · browser skipped (no display)

## ⏳ Your decision (0)
- none

Next: say "merge" to ship — 2 fixes pushed, gates green; visual QA not run (no browser), eyeball the <flow> first.
```
Between the last bucket and the `Next:` line, print — each as ONE plain line, in this order, omitting either when it does not apply:
```
Phases: 1-8 complete                                  ← driver runs only (Phase 0); name any phase that did not run and why
Calibration recorded: <line> — delete if wrong        ← only if §6.4 recorded one this run
```
The `Next:` line stays the final line; nothing follows it.

---

## Phase 8 — Cleanup

**Follow review-core §1.4** (remove worktree if clean; warn and keep if dirty).
