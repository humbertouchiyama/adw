---
description: "Shared machinery for /code-review and /spec-review. Read by each skill at its Phase 1 — not invoked directly."
---

# Review Core

Shared machinery for `/code-review` and `/spec-review`. This file is **not a slash command** — it has no arguments and does nothing on its own. Both review skills **Read it at their Phase 1** and follow it (the `port-prototype-pr` → `references/` pattern).

**This file lives in the `adw` repository and is fetched, not copied** (adw-core §9). It is repo-agnostic: every value that could differ between repos is in the consuming repo's `repo-profile.md`. Every command,
path and gate it needs is declared per-repo in the consuming repo's `.claude/repo-profile.md`,
cited below as `repo-profile §N`. Read that file at Phase 1 too — it is not auto-included either.

`.claude/commands/*.md` are prompt templates with **no auto-include**, so the mechanism is an explicit Phase-1 `Read`, not silent transclusion. Each skill quotes the one-line rule for a behavior and links here (`→ review-core §N`) for the detail.

**Section anchors are frozen** — the two skills cite `review-core §1`…`§7` by number. Do not renumber. Add new sections at the end.

| § | Section | Owns |
|---|---|---|
| §1 | Setup & worktree lifecycle | fetch, idempotent worktree, symlink, commit/push convention, cleanup |
| §2 | Phase ledger contract | TaskCreate-per-phase discipline |
| §3 | Adjudication principle | the single apply/escalate/reject decision; §3.1 escalation bar |
| §4 | Smart verification | verification branches on changed layers |
| §5 | Escalation surface | report/terminal gate (default) vs `AskUserQuestion` (opt-in) |
| §6 | Calibration loop | `.agent/review-calibration.md` — the skills learn from overrides |
| §7 | Blast-radius safety stops | union stop-list; when to fall back to comment-only |
| §8 | Local ship policy | commit/push/merge consent; apply≠merge; stage-only default vs declared auto-ship |

---

## §1 — Setup & worktree lifecycle

Machinery for standing up an isolated review workspace, committing into it, and tearing it down. Both skills run this at Phase 1 (PR mode). **spec-review file mode has no worktree** — reads/edits operate against the current working tree; skip the worktree/symlink/cleanup steps and treat "the worktree" below as "the repo root".

### §1.1 — Worktree (idempotent)

Each skill sets its own `$WT` path (`code-review`: `.claude/worktrees/pr-<N>`; `spec-review`: `.claude/worktrees/spec-review-<N>`).

```bash
git fetch origin <headRefName>
if git worktree list | grep -q "$WT"; then
  git -C "$WT" reset --hard origin/<headRefName>
else
  git worktree add "$WT" origin/<headRefName>
fi
```

All reads/writes **of the review target** (the PR's or spec's own files) use `git -C "$WT"` or absolute paths inside `$WT`. **One exception:** `.agent/review-calibration.md` is shared reviewer state, not part of the reviewed diff — it is read from and written to the **main-repo working tree**, never `$WT` (§6.1). **Never `cd` into the worktree** — `cd` triggers permission prompts and doesn't persist across Bash calls. (A `cd` inside a subshell `( … )` for a verification command is fine — it doesn't persist.)

### §1.2 — Provision the worktree

**`repo-profile §4` owns the exact commands and every trap.** Run them, in the order that file
gives, before any gate. Never improvise this step: in a workspace-style repo a hand-rolled symlink
is the documented way to corrupt the MAIN checkout, and the failure is silent and lands in a
directory nobody looks at.

This block owns provisioning for **every** worktree the review/build contract stands up, including
`/adw-build`'s implementer worktree (Phase 2) and `/pr-ready`'s verify worktree (§4.3) — both point
here rather than carrying a copy.

Two properties hold in every repo, whatever `repo-profile §4` declares:

- **Provisioning runs from the MAIN checkout, never from `$WT`.** `$MAIN` sits on the base branch,
  so a PR that rewrites provisioning never provisions the checkout that grades it. That pin is what
  keeps the provisioning script off `/pr-ready` §4.2's gate-file list; break it and the script
  belongs on that list. Exercising `$WT`'s copy as a *functional test* is fine and often the point —
  just never as the provisioning the gates then run against.
- **Conditional provisioning is setup, not a fix cycle.** `repo-profile §4` lists the diff-triggered
  blocks (a new dependency, a shared-package change). Each fault wears a test-failure disguise —
  an unresolved import reads as if the PR were broken. It is not the PR's defect.

### §1.3 — Commit + push convention (apply modes)

- **Stage exactly the files you touched** — never `git add .` / `git add -A` (worktree may hold stray symlinks or build output).
- **`.agent/review-calibration.md` is never staged alongside review fixes** — it is its own concern (§6).
- Commit with a Conventional-Commit subject and the trailer:
  ```
  Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
  ```
- `git -C "$WT" push origin HEAD:<headRefName>`.
- **Never `--no-verify`.** Pre-commit hook failure → fix the underlying issue, create a **new** commit (do NOT amend).
- Never force-merge, never bypass branch protection. A `--force-with-lease` rejection (parallel session pushed) is a safety stop (§7).

### §1.4 — Cleanup

```bash
if [ -z "$(git -C "$WT" status --porcelain)" ]; then
  git worktree remove "$WT" --force
else
  echo "WARN: $WT has uncommitted changes; not removing. Inspect manually."
fi
```

Removal failure → warn in terminal, don't block. **File mode: nothing to clean up.**

---

## §2 — Phase ledger contract

**Mandatory.** At Phase 1, create one `TaskCreate` per phase the skill declares. Mark each `in_progress` before starting, `completed` immediately after. The ledger is the contract that **the run is incomplete until every task is `completed`** — forgetting a phase requires forgetting to update its task, which is visible to the user. Each skill lists its own phase set.

---

## §3 — Adjudication principle

The one cognitive move both skills make on every finding. Named once here; every triage bucket in either skill is a **routing label under this principle**, not a separate philosophy.

> **Every finding is adjudicated to exactly one of:**
> - **apply** — clear engineering answer (a bug, a stale/wrong fact, a convention violation, a security-correct fix, a doc-consistency gap; one correct resolution) → fix it + verify (§4). In review-only mode, surface as a recommended fix — *state the decision*, don't claim it done.
> - **escalate** — a genuine product / UX / business / operational / architectural call the human must own (feature scope, a user-facing tradeoff, a prod-ops action, DB-rollout coordination, a recommended-default flip) → **one plain-language sentence of what must be decided + a recommended default**. Never a raw open question.
> - **reject** — not worth it / already covered / out of scope → a terse reason.
>
> **Default when unsure: escalate a *decision*, reject a *convention/lesson candidate*.** A plain Warning that is neither a genuine decision nor a convention candidate defaults to **apply** when the fix is small and correct, else **reject** — it is never, by itself, an escalation.

**Most findings that first look like "your call" resolve to *apply* once assessed** — only true decisions survive as escalations. Lead every report with what you decided; then list the (usually few) genuine escalations. Do not hand the user a raw list to adjudicate — the judgment is made *here*. **Neither skill presents findings as a chooser/menu** — an `AskUserQuestion` "which should I fix?" or a numbered "pick one" list IS a raw list; adjudicate each finding yourself and surface only genuine escalations via §5.

The bucket names each skill uses (code-review `toFix`/`escalate`/`reject`; spec-review `mechanicalFix`/`proseRewrite` + `escalate`; convention verdicts `Insert`/`Reject`) are routing labels under this principle. The phrases **"decide-or-escalate pass"**, **"self-assessed 6.2"**, and **"the lesson bar"** all resolve to this single principle by reference.

**This principle does NOT flatten spec-review's apply tiers.** In spec-review, **apply** stays two-tier: *mechanical* fixes land under `apply`; *prose* rewrites land only under `apply-all`. The conservative-by-default asymmetry is spec-review's own (it owns the implementation contract; the reviewer catches drift but doesn't flip a validated default). code-review has no such split — its `apply` fixes both.

### §3.1 — The escalation bar

**Both gates must hold, or it is not an escalation** — decide it yourself (*apply* or *reject*):

1. **Under-determined by the repo.** The answer needs a fact that exists only in the user's head — product intent, business tradeoff, ops timing, a user-facing behavior choice. If CLAUDE.md, the conventions docs, the spec, or the PR body answers it, it is *apply*. "I'd have to go read that doc" is not under-determined; go read it.
2. **Two defensible answers.** Two engineers with full repo knowledge could each *correctly* ship a different one. "I'm not sure which is cleaner" is not two defensible answers — it is one unfinished analysis: finish it, pick, and note the road not taken in the commit body.

Then, on what clears both gates, two resolution rules:

- **Cheap + reversible + you'd defend the default → just do it.** Report under Done with `— say "revert <x>" to undo`. The undo offer *is* the escalation; it costs the user a glance instead of a round-trip. (Applies only when you'd actually defend the default. If you wouldn't, you don't have one — that's a real escalation.)
- **Out of scope → reject, don't escalate.** A better idea for a follow-up is `reject: out of scope — file it`, not a decision handed back.

**Volume is a signal.** Most reviews escalate **zero** findings. More than ~2 almost always means the bar wasn't applied — re-adjudicate before reporting; the excess are `apply`s and `reject`s wearing a question mark. (This never licenses suppressing a `Blocking` finding — §6.6 binds.)

**The tell:** you are about to restate a finding with "should I…?" appended. If anyone who read the diff would answer it the same way, you already know the answer — write the fix, not the question.

**Convention / lesson candidates are a stricter sub-case.** A pattern worth documenting in a standards doc or `.agent/lessons.md` earns **apply** (an `Insert` verdict) only if it clears ALL of: *generic* · *detectable or review-teachable* · *recurrence-likely* · *not already covered* (grep the target doc first) · *worth its weight* · *not pure preference*. Miss one → **reject**, naming the failed criterion. On the fence → **reject** (a missed convention costs one repeated review comment; a bad one silently mis-flags correct code forever). **Learning-doc edits are never auto-applied even in an apply mode** — they steer every future PR/port and need human sign-off; surface `Insert` drafts + a terse `Reject` list for the user to land. (Calibration lines are the one reviewer-side exception — see §6.)

---

## §4 — Smart verification

Verification **branches on the layers actually changed** (from the skill's scope/classification phase), never a fixed suite. Never emit a fake green.

**`repo-profile §6` is the layer map and `repo-profile §5` is the command for each gate.** Read them;
do not restate either here. `§6` also declares the review-side invocation of any audit-style gate
(the review worktree is a detached, unstaged checkout, so a diff-scoped audit would inspect nothing).

Four properties hold in every repo, whatever those sections declare:

- **The map is computed from the diff, never judged.** A gate the diff reaches is not optional
  because it looks unrelated to the change. **Mixed diff** → run every layer present.
- **A gate that inspected nothing is not a pass.** Where a gate can be handed an empty scope,
  `repo-profile §5` states how to opt in explicitly. Reaching for that opt-in to turn a real code
  change green reinstates the exact lie the exit code exists to close.
- Each gate must pass with **zero errors** before any push. Any failure → safety stop (§7); never
  push partially-passing remediation.
- **Docs-only is a first-class outcome.** A docs/prose/skill-only PR reports
  `verification: N/A — docs-only` and passes; it must never fabricate a green line for gates that
  never ran. `repo-profile §2` declares which paths are non-code, and `§6` declares which layers do
  **not** fall under that exemption despite carrying no compiler.

---

## §5 — Escalation surface

How genuine **escalate** findings (§3) reach the human. Branches on run context, **defaulting to the non-blocking path**.

- **Default** (and whenever the context is unknown) → the **report section / terminal gate** the skills use today (a "Needs your decision" block; a `type '…'` merge gate). Never blocks — safe for async, scheduled, `review-and-merge`, and sub-agent runs.
- **Only on a positive interactive signal** → surface each genuine escalation as an `AskUserQuestion` option set, **recommended default first-listed**. The signal is an **explicit `interactive` flag** the skill parses in its arguments — **never inferred from `apply` / `apply-all`** (those say nothing about whether a human is watching), never guessed from anything else.

**Why opt-in, not inferred.** `AskUserQuestion` **blocks on user input**. In an async / CI / scheduled / sub-agent run it would hang the pipeline forever. There is no reliable interactive-vs-async signal intrinsic to a slash command, so this branch fires **only** on the explicit `interactive` flag; absent it, the run always takes the non-blocking default. When in doubt, non-blocking.

Convention/lesson `Insert` verdicts and calibration echoes (§6) are **reported, never surfaced as blocking prompts** — they are drafts for the user to land, not decisions gating the run.

---

## §6 — Calibration loop

Make the skills **learn from the user's overrides** instead of re-litigating the same escalation every run. A distinct channel from `.agent/lessons.md` (which records *code* patterns) — this records *review judgment* (how aggressively to escalate a finding class).

### §6.1 — The file

`.agent/review-calibration.md` — append-only, one line per override.

- **Read + write target: the main-repo working tree** (`$MAIN_REPO/.agent/review-calibration.md`) — the **same** path for the triage read (§6.3) and the append; **never `$WT`** (a worktree copy is the stale PR-branch checkout and is force-removed at cleanup §1.4 → the line would be read stale or lost). Resolve the main repo **robustly**, not as `$PWD` (the skill is often invoked from a worktree — CLAUDE.md §8):
  ```bash
  MAIN_REPO=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")
  ```
  `--git-common-dir` resolves to the **main** repo's `.git` from any linked worktree, so this is correct regardless of cwd. **Quote every expansion** (`"$MAIN_REPO/.agent/review-calibration.md"`) — this repo's path contains a space.
  > **Do NOT parse `git worktree list` with `awk '{print $2}'`.** Field-splitting truncates any path containing a space: a porcelain line like `worktree /Users/…/My Projects/the-repo` yields `/Users/…/My` — a path that does not exist. `$MAIN_REPO` then points nowhere and **§6.3's read silently returns empty**, so the calibration loop no-ops: every recorded line is ignored and the same class is re-escalated forever, with no error to notice. This is not hypothetical — it disabled the loop while two `apply`-direction lines (PR#739, PR#742) sat recorded and unread. If you must parse the porcelain, strip the prefix instead of splitting fields: `git worktree list --porcelain | head -1 | sed 's/^worktree //'`.
- **Its own concern:** never `git add`-ed alongside a review's staged fixes (§1.3). It reaches shared history **only** through the explicit commit gate below.

Line format:
```
<apply|escalate|reject> | <finding class> | <why the boundary should move> | <review ref>
```

### §6.2 — When a line is captured

When the user **overrides an adjudication**:
- reverses / rejects an auto-applied fix → `escalate | <class> | user did not want this auto-applied | <ref>`
- calls an escalation obvious ("just do it") → `apply | <class> | clear answer, stop escalating | <ref>`
- approves / rejects a convention or lesson verdict → tune that bar (`apply`/`reject` on the candidate class).

### §6.3 — Reading it at triage

At the skill's triage phase, **read `$MAIN_REPO/.agent/review-calibration.md`** (the main-repo path from §6.1 — **not** `$WT`, which holds a stale PR-branch copy). When a finding matches a recorded class, **bias the adjudication accordingly** and note `per calibration: …` in the log and report. A recorded line must visibly change the next run's adjudication for that class.

### §6.4 — Capture mode: automatic + echoed

The skill **infers** the override from the user's reply and appends the line **itself** — it does NOT wait for an explicit "remember this". **Every write is echoed in the report** — e.g. `Calibration recorded: apply | 404-vs-403 | 403 is correct, stop asking | PR#661` — so a mis-inferred line is one visible edit the user can delete. **A calibration line is never silently written.**

### §6.5 — Why auto-write is safe here (the sign-off bar, reconciled)

`.agent/lessons.md` and standards docs require human sign-off because they are *team-shipped code patterns* — once merged they steer every future implementation. Calibration is different in kind: it is *reviewer-side judgment*, it never mutates code or standards docs, and it is self-correcting (echoed, one deletable line, carries a review ref). So auto-write automates only the **drafting**, not the **persistence**: the line lands in the working tree automatically + echoed, but — exactly like a lesson — it reaches shared history only under the **explicit commit gate** (the user commits `.agent/review-calibration.md` themselves; the skill never commits it). The human sign-off moves from "author the line" to "confirm the commit"; only the transcription is automated.

### §6.6 — Hard guard (binds always)

An auto-drafted **`apply`-direction** line (escalate→apply, "stop escalating") may bias only **non-blast-radius** classes and **never suppresses a `Blocking` finding** — those always escalate/apply-and-verify regardless of calibration. Auditability alone is not prevention (a skimmed report hides a suppression), so this is a rule, not just a log line. See §7 for blast-radius paths.

---

## §7 — Blast-radius safety stops

The **union** of both skills' high-blast-radius path lists. When applied remediation touched any of these, **fall back to comment-only** — do not push or merge — and document the stop reason in the report. (Each skill imposes the whole union; a path oriented to the other skill is a harmless safety net when this skill never touches it, and a correct stop on the rare occasion it does.)

**Stop and fall back to comment-only when applied remediation touched any path in
`repo-profile §8`.** That section is the per-repo list; it is not restated here. Two entries are
universal and every profile carries them, because they are properties of the pipeline rather than of
the stack:

- **`.claude/commands/*.md`, `.claude/skills/**`, `.claude/*.md`** — every future agent run, this
  file included. The root glob is what covers `repo-profile.md` itself, the per-repo gate and
  environment-fault contract read at runtime — same blast radius as a command file, and outside this
  list until PR #1175 pushed to it under no stop.
- **`.github/workflows/**` (or the repo's CI definition)** — ships to an environment. No gate reads
  these files, and the two failure modes are releasing broken code and stopping every release, both
  landing after review is over. `/code-review` Phase 3 scores this class **+5**, above every other
  entry; a class argued to be the highest risk in the repo must not be the one that still
  auto-pushes.

The learning docs `repo-profile §2` names are also stops: edits are surfaced for sign-off, never
auto-landed (§3). A review-calibration append is drafting only (§6, auto-write + echo); it is never
included in a review's staged commit and never pushed as part of remediation.

**Also stop (independent of paths touched)** — these stop the *push* (fall back to comment-only), **except** a bullet that says otherwise: CI-failing stops only the *merge* (the remediation still commits + pushes; see 7a's two-tier split):
- Any `Blocking` finding could not be fixed automatically.
- A verification gate failed (§4). **This is the gate that guards the push** — never push remediation that doesn't build/lint/test clean locally.
- Browser verification was required and the skip was **not declared** (an *undeclared* gap). A **declared** inability to run a browser is NOT a stop: apply + unit-verify, then stage or push as the §8 policy dictates, and make human visual QA a **required pre-merge gate** (§8 merge consent) — browser-unavailability gates the merge, never the apply/stage/push.
- **CI checks failing — a *merge* stop, not a push stop.** Remote CI grades the PR's existing head; it says nothing about remediation that passed §4 locally, and the fixes may be what repairs it. Under a declared auto-ship policy (§8), red CI never blocks the commit+push — it blocks the merge gate, and the report's `Next:` line names the failing job.
- `--force-with-lease` rejected (parallel session pushed).

---

## §8 — Local ship policy (commit / push / merge consent)

An apply flag authorizes **editing the worktree**. Whether it also authorizes commit + push is the **local ship policy** (project config / CLAUDE.md / user memory / the invoking instructions / the skill's own declared policy). **Merge is never covered by any apply flag** — it always needs the explicit word.

- **Default: stage-only (fail-safe)** — binds any skill that does not declare its own policy. After apply + verify (§4), **stage the touched files and STOP.** The staged diff is the deliverable; the human ships. Surface commit / push / merge via the §5 surface (default: terminal gate; `interactive`: `AskUserQuestion`) and report `Action: applied + staged — awaiting your commit/push/merge consent`; never a fabricated "pushed"/"merged".
  - A generic affirmation ("do it", "go ahead", "yes") is **not** commit/push/merge consent — it authorizes only the single act just named.
- **Declared auto-ship policy** — a skill may declare that its apply flag *is* the commit+push consent, because the user typed a word that names the deliverable ("apply the fixes to the PR"). Then, after verify (§4) passes green: commit + push per §1.3, no gate. **`/code-review` declares this** (code-review.md, `apply` row). **`/spec-review` does not** — it stays stage-only.
  - **Push-consent ≠ merge-consent.** Auto-ship ends at `push`. The §5 merge gate still runs.
  - **§7 still binds.** A blast-radius path or a failed gate falls back to comment-only — an auto-ship policy never overrides a safety stop.
  - **Re-runs push again.** A second `apply` on the same PR is a **new** commit + push (never amend, §1.3) — iterating is expected, not an anomaly.
- **Merge needs explicit merge consent, always:** the word "merge" / "merge it" in the terminal gate, or selecting the Merge option under `interactive`. Nothing weaker counts — not `apply`, not "do it", not "go ahead".

No apply flag ever implies merge. Every Phase-7 commit/push/merge step is read **through this section**.
