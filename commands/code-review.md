---
description: "Code review PR against project conventions. Usage: /code-review <PR_NUMBER> [light|full] [apply] [interactive]"
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
| (none) | auto-triage → light or full |
| `light` | force 1-agent path |
| `full` | force Anthropic plugin + project checks |
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
1 Setup       → {pr, $WT, mode, apply, interactive, ledger}   (review-core §1, §2)
2 Scope       → {changedFiles[], stats, layers[]}
3 Path        → "light" | "full"
4 Review      → findings[]                        (light: inline / full: gated plugin + 4.5 parse)
5 Project     → findings[] (appended)
6 Triage      → {toFix[], escalate[], conventionEdits[]}   (adjudication: review-core §3; calibration: §6)
7 Terminal    → comment posted | fixes committed + pushed + ask-merge (apply)   (§1.3, §4, §5, §7, §8)
8 Cleanup     → worktree removed   (review-core §1.4)
```

**No phase produces "advice that may or may not be acted on" — every output has a consumer.**

---

## Phase 1 — Setup

1. **Read [`review-core.md`](review-core.md) and the consuming repo's `.claude/repo-profile.md`**
   end-to-end. The first governs the shared machinery this skill references by section; the second
   holds every repo-specific value it references as `repo-profile §N`. Neither is auto-included —
   `.claude/commands/*.md` are prompt templates with no transclusion, so an unread pointer is a rule
   loaded nowhere.

2. Parse `$ARGUMENTS`. Position 1 = PR number. All later tokens = flags (`light` | `full` | `apply` | `interactive` | `since:<sha>`), order-insensitive, case-insensitive. Conflict (`light` AND `full`) → error and stop. Duplicate of the same flag → no-op. Resolve `mode` (forced or auto), `apply` (bool), `interactive` (bool), `SCOPE_BASE` (`origin/<baseRefName>`, or `<sha>` when `since:` was given — Phase 2).

3. Fetch PR metadata:
   ```bash
   gh pr view <PR_NUMBER> --json headRefName,baseRefName,title,body,number,url,state,isDraft,headRefOid
   ```
   Eligibility gate — exit with terminal note if `state != OPEN` or `isDraft == true`. If a prior `### Code review` comment exists (`gh pr view <N> --json comments`) AND its body contains the current `headRefOid` short SHA → exit "already reviewed at this SHA"; otherwise warn-only (re-running on a new SHA is legitimate).

4. Store `headRefName`, `baseRefName`, `title`, `body`, `url`. Set `WT=.claude/worktrees/pr-<PR_NUMBER>`.

5. **Worktree + symlink deps → follow review-core §1.1–§1.2** (idempotent add / reset, `git -C "$WT"`, never `cd`).

6. **Phase ledger → follow review-core §2.** Create one TaskCreate per phase below; mark `in_progress` before, `completed` after:
   - `Phase 1 — Setup`
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

If `mode` was forced (`light` or `full`), use it. Otherwise score the diff against
**`repo-profile §14`**. Each row scores at most once.

**`>= 5` → full. `< 5` → light.** The threshold is the contract's, not the profile's — a profile
tunes which signals score and by how much, never where the bar sits.

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
Triage: score=<N> → <light|full>
  <point breakdown>
```

**Output**: `path = "light" | "full"`.

---

## Phase 4 — Review

Both branches produce a single typed output: `findings[] = [{file, line, description, severity}]`.

### 4a — Light path

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

### 4b — Full path

**Plugin gate (WS3).** The cloud plugin grades **app code** — on prose/docs it is pure noise. Fire it **only if `layers[]` is non-empty** (reviewable code present, Phase 2) **and `since:` was not given**:

- **`layers[]` empty** (docs / prose / skill-only diff that nonetheless scored `full` on size/`.claude` points, or was forced `full`) → **skip the plugin**, set `pluginRan = false`, `findings = []`, and log: `Full path, plugin skipped: docs/prose-only diff, no app code to grade.` Phase 5 project checks still run; Phase 7 must not assume a plugin comment exists.
- **`since:` given** (a delta pass — `/pr-ready` §3 cycle 2) → **skip the plugin and take the 4a light path instead**, set `pluginRan = false`, and log: `Full path, plugin skipped: delta pass (since:<sha>) — plugin cannot be scoped.` The plugin's only argument is a PR number: it always grades `base...HEAD`, so firing it here would re-review the whole PR and reinstate the non-convergence `since:` exists to remove — silently, because the tier says `full` and a plugin comment would duly appear. The light agent takes `$SCOPE_BASE` and is the correct instrument for a delta, which is small by construction.
- **`layers[]` non-empty and no `since:`** → invoke `Skill` tool `code-review:code-review` with args `<PR_NUMBER>`, set `pluginRan = true`. The plugin runs its multi-agent review and posts its own PR comment. Then run **4.5 — Parse plugin findings**.

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

**Intent coherence** (always — hand the agent the PR `title` + `body` from Phase 1):
- Does the diff actually do what the PR says? Flag only a real mismatch: the stated goal is
  half-implemented (promises X, ships part of X), the diff carries stray changes unrelated to the
  stated goal, or the approach plainly can't achieve the stated goal. This is a *coherence* read,
  not a style/bug pass — one finding per mismatch, severity `Warning`, `description` naming the
  intent gap. **Phase 6 adjudicates the routing** (a scope mismatch is a genuine "is this the
  intended scope?" escalation; a clear small omission is a toFix) — don't pre-route here. Skip
  silently — no finding, no note — when the diff plainly matches the PR body, or when the body is
  empty/`title`-only (nothing to check against).

**Everything else: hand the agent `repo-profile §16.4` verbatim.** That section is the repo's list
of per-trigger structural checks ("for a new endpoint…", "for a new migration…"), and it is not
restated here. Run the entries whose trigger the diff matches; report the rest as not applicable.

Intent coherence stays in this file rather than in the profile because it is a property of *pull
requests*, not of a stack — it reads the PR body against its own diff and needs no repo knowledge.

**Output**: `findings[]` extended with project-specific entries.

---


## Phase 6 — Triage + self-heal draft

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
4. **⏳ Your decision** — the ONLY bucket that needs the human: escalations that cleared the **§3.1 bar**, each **one plain sentence + a recommended default**, plus convention `Insert` drafts (never auto-landed — need sign-off).
5. **`Next:` line (LAST)** — **the single most important line in the report, placed last so it is what stays on screen.** One sentence naming the ONE thing the user does now, or that nothing is needed. It is a *directive*, not a summary. E.g. `Next: nothing — 3 fixes pushed, CI green. Say "merge" to ship.` / `Next: answer the 1 decision above, then re-run with apply.` / `Next: fixes pushed, but CI is red on <job> — not mine, look before merging.` If **⏳ Your decision** is empty and gates are green, `Next:` always resolves to a merge invite or `nothing`.

**Hard limits.**
- **The report IS the final message.** Not a block embedded in a summary — the header is the first line the user sees and the `Next:` line is the last. No preamble ("I've finished reviewing PR #742…"), no recap of what you did, no closing offer ("let me know if you'd like…"). Prose wrapped around the buckets is the verbosity, even when the buckets themselves are tight.
- **One line per item.** No sub-bullets, no nested detail, no evidence dumps. An item needing a paragraph to justify gets its paragraph in the PR comment or the triage log; the report gets its one line.
- **~15 lines total.** Longer than a screen has failed regardless of structure.
- **No diagnostics** — path/score, plugin state, layers, phase narration, findings counts, and the rejected list stay in the triage log. Never in the report.
- Every bucket prints its header even when empty (`— none`; *Your decision*: `— none`).
- The `Next:` line is the final line of the report; nothing follows it. The ONE thing allowed between the last bucket and the `Next:` line: a calibration line recorded this run (§6.4 requires the echo) as a single plain line — `Calibration recorded: <line> — delete if wrong` — nothing else.

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

   **⏳ Your decision** (<M>) — cleared the §3.1 bar; everything engineering-clear is in Done
   - file:line — one plain sentence of what to decide + recommended default
   - `[Insert → <target file>]` <one-line rule> — convention draft, needs your sign-off (not auto-landed)
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

## ⏳ Your decision (<n>)
- <file:line — one plain sentence + recommended default>
- `[Insert → <target>]` <one-line rule> — convention, needs sign-off
   |   — none

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
If — and only if — a calibration line was recorded this run (§6.4), print ONE plain line between the last bucket and the `Next:` line: `Calibration recorded: <line> — delete if wrong.` The `Next:` line stays the final line; nothing follows it.

---

## Phase 8 — Cleanup

**Follow review-core §1.4** (remove worktree if clean; warn and keep if dirty).
