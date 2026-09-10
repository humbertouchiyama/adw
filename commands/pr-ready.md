---
name: pr-ready
description: Independently verify that an open PR is actually ready to merge — review cycles, a gate re-run in a fresh checkout by an agent that did not write the code, and fetched review evidence. Verdict is ready | blocked.
argument-hint: <PR> [apply] [interactive]
---

# PR Ready — `ready` is earned, never asserted

**This file lives in the `adw` repository and is fetched, not copied** (adw-core §9). It is repo-agnostic: every value that could differ between repos is in the consuming repo's `repo-profile.md`. Every command,
path, gate and CI fact it needs is declared per-repo in
the consuming repo's `.claude/repo-profile.md`, cited below as `repo-profile §N`. Read that file at
§1 alongside `review-core.md` — neither is auto-included.

**Input**: `$ARGUMENTS` — first token a PR number; the rest are flags.

| Flag | Effect |
|---|---|
| (none) | run the review **report-only** (`/code-review` posts findings, applies nothing), then the independence pass and the evidence gate. Nothing is pushed. |
| `apply` | `/code-review <N> <tier> apply` — findings are fixed and pushed (that flag is `/code-review`'s declared auto-ship policy, `review-core.md` §8). **Never merge consent.** |
| `interactive` | escalations surface via `AskUserQuestion` instead of the terminal gate (`review-core.md` §5). Never inferred from `apply`. |

Examples: `/pr-ready 838` · `/pr-ready 838 apply` · `/pr-ready 839 apply interactive`.

**This command never merges.** Merge needs the explicit word, every time (`review-core.md` §8).

---

## When to reach for this — and when `/code-review` is the better tool

**This is an audit, not a pipeline.** It does not loop until a PR is clean: §3 caps it at
two cycles and §7 ends in a *report*. A user who wants review → fix → verify → merge wants
`/code-review <N> apply`, which ends in a merge invite. Say so rather than letting the
misread stand — it is the natural reading of the name.

**§4.3 is only redundant where CI already ran the same gates — read `repo-profile §9` before
assuming it did.** That section is the per-repo coverage table: which events trigger a hosted run,
which gates it executes, and which of the `review-core.md` §4 obligations it never touches. It is
also authoritative over this file — if it disagrees with the repo's CI definition, the CI file wins
and `repo-profile §9` is what gets corrected.

Three things no CI covers in any repo, and they are the whole argument for this command:

| | in CI? |
|---|---|
| review posted *after* the last code commit (§5) | no |
| verified-SHA == merged-tree (§6) | no |
| the gate-file tripwire's A/B control (§4.2) | no |

So: reach for `/pr-ready` when `repo-profile §9` says this PR's shape gets no hosted run (an
opt-in that was not opted into, a base branch outside the trigger list, a draft), when the diff
reaches a gate CI never runs, or when a session built the PR unattended and the SHA discipline is
the point. Where CI genuinely covered every §4-obligated gate at the pushed SHA, `/code-review <N>
apply` plus a glance at `gh pr checks` is the cheaper and equally honest path — but check §9 first,
because "no checks" reads as **absent, not red**, and absent is the default in more repos than not.

---

## What this owns — and what it does not

`/code-review` already reviews, applies, and **verifies its own fixes** (`review-core.md`
§4 — layer-branched gates, docs-only outcome, never a fake green). This command exists
for the one thing a reviewer structurally cannot do to itself: **check the result from
outside**.

| Concern | Owner |
|---|---|
| Finding defects, adjudicating, applying fixes, pushing | `/code-review` (`review-core.md` §3, §8) |
| Which gates a diff obligates | `review-core.md` §4 — by reference, never restated here |
| Worktree setup, symlinks, `pack:shared`, cleanup | `review-core.md` §1 |
| **Fresh checkout at the pushed head, gate files restored from base** | **here, §4** |
| **A verifier agent that did not write or fix the code** | **here, §4** |
| **Review evidence, fetched rather than asserted** | **here, §5** |
| **The void rule — a later commit un-earns `ready`** | **here, §6** |
| Mutation checks, depth ladders, artifact ratios, chain/sub-PR merges, run clocks | `/adw-build` — pipeline control, not PR verification |

The split rule, once, so future edits classify mechanically: **loop body lives here; loop
control lives in the caller.** Anything that needs to know *why this PR exists* (a unit
id, a declared `verify` command, a depth, a cycle budget, a chain position) is control
and does not belong in this file.

---

## Phases

Create one `TaskCreate` per phase (`review-core.md` §2): `Setup` · `Tier` · `Review` ·
`Independence` · `Evidence` · `Verdict` · `Cleanup`.

### §1 Setup

**Read [`review-core.md`](review-core.md) and the consuming repo's `.claude/repo-profile.md`
end-to-end first.** Every `review-core.md §N` and `repo-profile §N` below is a pointer into a file
that is **not** auto-included — `.claude/commands/*.md` are prompt templates with no transclusion,
so an unread pointer is a rule loaded nowhere.

```bash
MAIN="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"
git fetch origin
gh pr view <N> --json number,state,isDraft,baseRefName,headRefName,headRefOid,title,url
```

`--git-common-dir`, not `--show-toplevel`: invoked from inside a linked worktree the
latter returns *that worktree's* root, so `$VWT` would nest at
`…/worktrees/<wt>/.claude/worktrees/…` and dirty the host worktree against
`review-core.md` §1.4's cleanup check. Same idiom, same reason, as §6.1 there. Quote every
expansion — a checkout path containing a space is not hypothetical.

Fetch here, not only at §4.1 — §2 scores a diff against `origin/<headRefName>`, and a
stale ref would tier the wrong change.

State must be `OPEN`. Draft → proceed but say so on the verdict line (a draft can be
verified; it just cannot be merged). Closed/merged → stop.

Three derived values everything below uses:

- `BASE` — default `origin/<baseRefName>`. **Callers may override it** (`/adw-build`
  passes a merge-base for sub-PRs); an overridden `BASE` is echoed on the verdict line.
- `PASS` — `v1` for the first independence pass, `v2` for the next, and so on. Every pass
  gets its own worktree so a re-pass never collides with a live one.
- `REF` — the worktree-name token, default `<N>`. **Callers may override it**, and the ADW
  caller must: `/adw-build` §3.4 verifies *before* §3.5 opens the PR, so at `v1` there is
  no `<N>` to name a path with. It passes its unit token (`<slug>-uNN`). §4.3 and §8 both
  key on `$REF` — one symbol, so the sweep can always match what the checkout created.
  Hardcoding `<N>` here is what stranded three worktrees across three runs (retro
  2026-08-01): the name was improvised per run while §8's glob still said `<N>`, and a
  cleanup glob that matches nothing fails silently.

**These three, and `MAIN`/`VSHA`, are substituted as LITERALS at EVERY use below — every
section, fenced block and inline command alike, with no list of covered sections to fall
out of.** The scope is deliberately universal rather than enumerated: the first draft of
this rule named "§4.3, §5, §6, §7 and §8" and the two §1-consuming commands in §2 and §4.2
fell straight through the gap, which is the same failure the rule exists to close, one
level up.

Shell variables do not survive between Bash tool calls, and each section is a separate
call: left live, `$MAIN` expands empty and `git -C ""` errors, an empty `$VSHA` silently
re-points a `log -1`/`rev-parse`/`diff` at `HEAD`, and an empty `$REF` makes §8's pattern
`pr-ready--`, which matches nothing and passes. Every one of those failures is silent or
mis-measures the thing the section exists to measure. A `# $X from §N` comment records
provenance; it does **not** discharge this rule.

`review-core.md` §7 (blast-radius safety stops) binds this command as it binds the others.

### §2 Tier

Compute `<tier>` (`light` | `full`) yourself from `/code-review`'s own Phase 3 scoring
table, applied to the **code** diff only — score
`git diff --stat $BASE...origin/<headRefName> -- <repo-profile §2 artifact exclusion pathspec>`.

Specs and plans under the profile's spec/plan dirs are covered at init, not by a code reviewer —
D3 critical-passes design, spec **and** the separate plan file; D2 critical-passes its one
artifact whole, the spec including its `## Implementation` section; D0/D1 have no critical pass
at all and rest on the approval gate plus the
mutation gate (adw-core §3).
Left in, a single committed plan can cross the >500-line `full` bar on its own
and buy a 6-agent pass over documents nobody asked to review.

### §3 Review

`/code-review <N> <tier>` — plus `apply` when the flag was given.

**Max 2 cycles, and cycle 2 is scoped to the delta.** Hand it `since:<sha>` — the head SHA
cycle 1 reviewed — so cycle 2 grades *what the fixes changed*, never the whole PR again.
`code-review.md` Phase 2 owns the scoping and defaults to the full base diff; it narrows
only when handed `since:`.

Re-reviewing the whole PR is not merely wasteful, it **cannot converge**. An LLM pass over
identical code returns a different sample of findings, so the stop condition below would
measure reviewer variance rather than PR stability — and a healthy PR gets stamped
`blocked` because pass 2 happened to notice a different nitpick. Scoped to the delta the
surface shrinks each cycle, which is the property that makes the rule terminate at all.

**Cycle 1 is never scoped** — it must see the whole PR. And a delta scope is *files*, not
hunks: cycle 2 reads the complete current contents of every file the fix touched, because a
fix can break code it did not edit (the composition trap, `CLAUDE.md` — two locally-correct
hunks ~30 lines apart, the second made unreachable by the first).

**A second cycle that still yields applied findings means the PR has not converged**: it is
**not** `ready`. Run §4 anyway (the last push must still be gate-verified), then report
`blocked` listing the unconverged findings. An applied push that nothing re-reviewed has
not earned `review clean`.

A finding clearing the escalation bar (`review-core.md` §3.1 — both gates, neither
resolution rule disposes) → `blocked`, with the question and a recommended default.

### §4 Independence pass

Judges anchor on confident closing language — no configuration beat AUROC 0.65 at
detecting false success. So this pass never asks for an opinion; it re-executes.

Everything below runs against the **pushed** head, never a local branch: `/code-review
apply` pushes to origin, and a local branch that was never pulled does not advance.

**§4.1 — Resolve the verified head.**

```bash
git fetch origin
VSHA=$(git rev-parse origin/<headRefName>)
```

**§4.2 — Gate-file tripwire.** `git diff --name-only $BASE...$VSHA` against
**`repo-profile §7`** — the per-repo list of every file a gate command reads. Any hit → the verdict
is **`blocked`**, whatever colour the gates return: a PR that edits its own gates cannot earn a
green under them. But never blocked-silent, and never on one data point — run §4.3's **gates**
twice, in the SAME `$VWT`:

```bash
# run A first — the worktree as checked out at $VSHA, restore line skipped
# then, in place:
git -C "$VWT" checkout "$BASE" -- <every repo-profile §7 file>   # → run B
```

One worktree, one provisioning, one `pack:shared`; only the gate commands re-execute. Do
not stand up a second `$VWT` — §8's sweep is keyed on `$REF`-`$PASS` and a second path
under the same `PASS` is a leak it will not match. Order matters: A **before** B, because
the restore is one-way and re-checking out `$VSHA`'s copies to undo it is a step that can
silently half-fail.


| run | gate files in `$VWT` | the question it answers |
|---|---|---|
| **A — as shipped** | the PR's own | does it pass under the gates it *proposes*? |
| **B — as graded today** | restored from `$BASE` (§4.3's restore line, unmodified) | does it pass under the gates it *inherited*? |

**Two greens is the informative result**, not a formality: the gate edit changed no
outcome, so the `blocked` that follows is a **signature request, not a defect report** —
say exactly that in the report. A disagreement is the smoking gun the tripwire exists to
find, and it names itself: A green / B red ⇒ the PR *needs* its gate change to pass (read
the change on its merits); A red / B green ⇒ the gate change *breaks* the PR. Report which,
never just "mixed".

Superseded rule, deliberately: this used to run A alone, reasoning that restoring files the
PR legitimately edits "would test a hybrid that exists nowhere." True and beside the point —
B is not a candidate for merge, it is a **control**. Run A alone and the tripwire reports
that a risk category was *entered*, never whether it *materialised*, which is why every hit
produced the same unappealable verdict regardless of the evidence beneath it.

**Run B can be incoherent** — a PR adding a dependency does not install against base's
`package.json`, and a PR that renames a config target does not resolve it. When B fails to
*install or build* (as distinct from failing a gate), report `run B not applicable:
<reason>` and stand on A alone. Never present that as two greens.

Attach the evidence as
`clean-checkout evidence — NOT verifier-green (gate files changed: <list>)`, one table per
run. A red there is not a fix cycle; a green there is not `ready`. §7 requires a named next
action, so this branch carries, when A and B agree green, `default: the gate edit changed
no outcome — this needs your signature, not a fix; say "merge" if the rest of the report is
clean`, and otherwise a one-line statement of which run disagreed and what that implies.

**The list lives in `repo-profile §7`, never here.** It is derived by enumerating every file the
repo's gate commands read, so it is extended together with the gate sets that read it
(`review-core.md` §4 → `repo-profile §5`/`§6`). Four rules govern how that list is built, and they
hold in every repo:

**Never enter a directory — name the files.** A directory entry blocks every PR that adds an
unrelated file under it, and `blocked` is unappealable, so the cost lands on PRs the rule was never
aimed at. A blanket `scripts/` entry blocked PR #922 for adding a provisioning script no gate
command runs. Keep the entries file-scoped and let a file added later be excluded by default, until
it earns a place by being read by a gate command.

**A test file is a gate's subject, never its harness** — otherwise every source test would belong on
the list too.

**A config's setup/teardown target is itself a gate file** — the config merely names it, the target
is what actually runs. Listing the config and omitting its target is the subtlest form of the hole,
because the pair looks complete. PR #894 rewrote an integration `afterEach` — the file deciding what
every integration test sees between cases — and matched no entry; it tripped only because it also
touched a config that was listed.

**Resolve the target, do not grep for `setupFiles`.** The key is named differently per runner and
sometimes not named at all: `setupFiles`, `globalTeardown`, a *project* dependency named in another
project's `dependencies`, TS project `references`, and a **script body** (a build script whose
output every type gate consumes). Open each config you add and follow every path it points at, and
re-walk the closure when you add a config — not on a schedule. Three passes of this rule were needed
to land it in the first repo that carried it, which is the argument for walking the whole list
rather than the entry in front of you.

**A file the verify harness runs from the BASE checkout is not a gate file.** §4.3 provisions `$VWT`
using the **main checkout's** provisioning script (`review-core.md` §1.2 pins it there), and `$MAIN`
sits on base — so a PR rewriting provisioning never provisions its own verification and cannot bias
its own gates. That pinning is what earns the script its place off the list, and it is load-bearing:
point provisioning at `$VWT`'s copy and a provisioner that resolved a workspace package to MAIN's
tree would compile **base's** code and return green for a broken PR. Keep §4.3 base-pinned, or put
the script on the list — the two move together.

**§4.3 — Fresh checkout, fresh verifier.**

```bash
VWT="$MAIN/.claude/worktrees/pr-ready-$REF-$PASS"   # $MAIN, $REF, $PASS from §1 — as LITERALS (§1)
git worktree add --detach "$VWT" "$VSHA"            # $VSHA from §4.1 — as a LITERAL
git -C "$VWT" checkout "$BASE" -- <every repo-profile §7 file>   # no §4.2 hit: always, one run.
                                                                 # §4.2 hit: this IS run B; run A omits it
```

`--detach` is required — the head branch may be checked out elsewhere, and a branch-form
`worktree add` refuses. The path prefix is `pr-ready-`, never `pr-<N>`: that one belongs to
`/code-review` and may be live in the same session. `$REF`, never a literal `<N>` — §1
explains why, and §8's sweep only works if both sides spell the same symbol.

Provision per `review-core.md` §1.2, which delegates the commands to `repo-profile §4` — the
unconditional block **and** every diff-triggered one. Skipping them kills dependency-adding and
shared-package PRs with unresolved-import errors before a real gate ever runs, and that fault reads
as if the PR were broken.

**Run the provisioning script from `$MAIN`, never from `$VWT`.** `$MAIN` is on base, so the
PR's own copy never provisions the checkout that grades it. This is the pin §4.2 relies on
to keep the provisioning script off the tripwire list; break it and the script becomes a gate
file. Exercising `$VWT`'s copy as a *functional test* is fine and often the point — just never as
the provisioning that the gates then run against.

Then dispatch a **fresh verifier subagent** that re-runs every gate
`review-core.md` §4 obligates for this diff (`repo-profile §6` maps them), inside `$VWT`.

- **Pin it to `model: sonnet`.** The verifier re-executes and relays; it never judges. An
  unpinned dispatch inherits the session's most expensive tier for a job that is exit
  codes and output tails.
- **A subagent, never inline.** Inline mixes the verdict into a transcript that also holds
  the author's and the reviewer's claims — the first step toward interpreting instead of
  relaying.
- **The report is a per-gate evidence table** — one row per obligated gate: command · exit
  code · output tail. A report missing a row for an obligated gate is a **red**, never a
  green. Prose-only "all green" is exactly the confident-closing-language this pass exists
  to kill; without the table nothing distinguishes a full pass from a quiet subset.

Any red → the PR is `blocked` with the failing gate's output and
`default: fix <gate> on <headRefName>, then re-run /pr-ready <N>`. All green → the state is
earned, pending §5.

Remove `$VWT` (`git worktree remove --force`) as soon as its verdict is recorded.

### §5 Review evidence — fetched, never asserted

Before printing `ready` or `review clean`, require review activity dated after the last
commit that touched **production code** — anything outside the non-code paths
`repo-profile §2` declares:

```bash
# the ':!…' pathspecs are repo-profile §2's non-code paths, one per exclusion
CODE_TS=$(TZ=UTC git -C "$MAIN" log -1 --format=%cd \
  --date=format-local:%Y-%m-%dT%H:%M:%SZ "$VSHA" \
  -- . ':!*.md' ':!docs/**' ':!.claude/**' ':!.agent/**')
gh pr view <N> --json comments,reviews --jq \
  "[(.comments[]?, .reviews[]?) | select((.createdAt // .submittedAt) > \"$CODE_TS\")] | length"
```

**Substitute `MAIN` and `VSHA` as LITERALS**, exactly as §6/§7/§8 do — both were set in
earlier sections (§1, §4.1) and shell variables do not survive between Bash tool calls.
Left live, `$MAIN` expands empty and `git -C ""` errors, while an empty `$VSHA` silently
re-points the `log -1` at `HEAD`; either way `CODE_TS` is wrong and the gate stops
measuring what it claims to.

`$MAIN`, not `$VWT`: §4.3 already removed the verify worktree, and `$VSHA` is reachable
from the main checkout because §4.1's `git fetch origin` put the object in the shared
store. Any live checkout of this repo works; a removed one does not.

`0` → **not** `ready`; print `blocked` with
`default: the review never posted against this head — run /code-review <N> <tier> apply,
then re-run /pr-ready <N>`.

Three mechanical facts this snippet depends on, each verified against `gh` and `git`
rather than assumed:

- A review object carries `submittedAt` and its `createdAt` is **null** — without the `//`
  fallback every review is silently dropped and only issue comments count.
- `%cI` emits the committer's local offset while `gh` returns UTC `Z`. jq's `>` on strings
  is lexicographic, so unnormalised, a UTC−3 commit reads ~3h early and passes a review
  that predates the code.
- Keyed on **timestamp, not comment shape**, deliberately: `/code-review` has branches
  that post no project comment at all (Phase 7 — plugin clean, no convention updates, no
  escalations), so a header match would block precisely the cleanest reviews.

Dating on the code head rather than `$VSHA` is what keeps this consistent with §6: a
docs-only amendment moves the head, no review post-dates it, and keyed on `$VSHA` the PR
would block for a re-review §6 explicitly exempts. A PR with no production code at all
yields the base commit's stamp and passes on the existing review — correct, there is
nothing for a code review to have missed.

This is a **floor, not a proof**: an unrelated human comment satisfies it. It is built
against the failure that actually happened, which was not forgery — a run skipped the
review on three PRs, said so in its report, and shipped them as `ready` when the note drew
no objection. Flagging a deviation is not permission to take it, and a rule the runner can
decline and then narrate past is not a gate. **The fetch is not declinable.**

### §6 The void rule

**`ready` is a property of `$VSHA`, never of the PR.** Any commit that lands on the head
branch after the state is earned — owner-feedback amendments included, whatever produced
them — voids it:

- re-run §4 against the new head with the next `PASS` id, **always**;
- plus one `/code-review` cycle **when the delta touches production code**. Docs-only →
  re-verify alone.

Until both pass, no surface may print `review clean` or `ready` for a head the review
never saw.

**Read the two bullets as a matrix, not a ladder.** The docs-only exemption is scoped to
the *review* bullet and to nothing else. The re-verify bullet says `always` and has no
exemption at any depth:

| delta since `$VSHA` | re-run §4 | `/code-review` cycle |
|---|---|---|
| production code | yes | yes |
| docs-only | **yes** | no |

Verified in the field, so it is not hypothetical: a run earned `ready` at one SHA, pushed a
docs-only commit, and closed with *"`<sha>` is docs-only, so the verification above still
stands for every executable line"* — reading the review exemption onto the re-verify. The
merged tree was one no pass had ever checked out (retro 2026-08-01, `module-toggles`). The
sentence is seductive because it is *almost* true: the executable lines are indeed
unchanged. What is unverified is not the lines, it is **the tree** — and the tree is what
merges.

**So the check is mechanical, and §7 prints its result:**

```bash
git fetch origin
[ "<the VSHA literal>" = "$(git rev-parse origin/<headRefName>)" ] || echo "VOID — head moved past the verified sha"
```

Non-empty output → the state is void: run the next `PASS`, or print `blocked`. Never
reason about *what* the delta contains as grounds for skipping the re-run — that reasoning
is the failure mode, and this comparison does not admit it.

### §7 Verdict

**Two layers, in this order: prose for the human, then the line for the caller.** The
machine line below is parsed by `/adw-build`; its shape is frozen. Everything above it is
written for a person who has not read this file and never will.

**Layer 1 — the plain-language head (2–4 sentences, always).** No `§` refs, no rule names,
no `verifier-green`. Answer, in this order:

1. **What is this PR?** One clause.
2. **Is it safe?** What the gates actually said, in words a person can act on.
3. **What now?** — as a sentence they can **reply with verbatim**. `say "merge" to ship` ·
   `say "apply and merge"` · `fix <gate> on <branch>, then re-run /pr-ready <N>`.

**Layer 1 is for a human-invoked run. A caller that maps the state takes Layer 2 only** —
`/adw-build` prints its own run-report and PR-body surfaces off `ready`/`blocked` (adw-core §7's templates,
which are strict), so prose emitted into those is a format violation, not a kindness. The
head is unconditional when a person typed the command, and suppressed when a caller
consumes the verdict.

**Layer 2 — the machine line.** One line, always both fields:

```
ready    #838  <title>  — verified <sha7> · review clean · <tier>
blocked  #839  <title>  — <one-line reason> · verified <sha7>
         default: <the single next action>
```

`blocked` carries a recommended default; a blocked verdict with no named next action is
incomplete. Echo a non-default `BASE` and a draft state on the same line.

**`blocked` is one token covering two unrelated situations, and Layer 1 MUST say which.**
The token cannot split — `/adw-build` switches on `ready|blocked` — so the disambiguation
lives in the prose or nowhere:

| situation | what the head must convey |
|---|---|
| something is **red** — a gate failed, findings did not converge, an escalation is open | this PR is not finished; here is the failing thing |
| everything is **green**, a rule wants a human — §4.2 tripwire, a §7 blast-radius stop, an unpushable fix | nothing is broken; this needs your signature, and here is the sentence that gives it |

Never let a green-but-gated run read as a defect report. Field-verified: PR #941 came back
`blocked` with `default: the owner reads the clean-checkout evidence and decides` — seven
green gates, a mergeable PR, and a user whose literal reply was *"I have no idea what is
next step with your response."* A `default:` that hands the decision back without naming
the reply is not a next action; it is the absence of one wearing its label.

**When a §7 blast-radius stop withheld a fix, print the sentence that authorizes it.**
`review-core.md` §7 falls back to comment-only precisely so a human decides — so state the
decision and quote the words: `3 fixes found but not pushed (root config); say "apply the
fixes" to land them`. A stop the user must first *discover*, then *guess the phrasing for*,
has converted a safety feature into an obstacle.

**`verified <sha7>` is not a recollection — re-ASSERT it at print time**, on `ready` and
`blocked` alike. Not "re-derive": deriving it fresh
(`VSHA=$(git rev-parse origin/<headRefName>)`) satisfies the words and produces the exact
lie this paragraph exists to stop — a verdict stamped with a SHA no pass ever checked out.
Run §6's comparison immediately before printing:
`[ "<the VSHA literal>" = "$(git rev-parse origin/<headRefName>)" ]` must hold —
substituting `VSHA`'s value as a literal, as §8 does for `REF`, since it was set back in
§4.1 and shell variables do not survive between Bash tool calls. If it does not, the
verdict is `blocked` and the printed `<sha7>` is still `$VSHA` — the SHA that was actually
verified — never the new head. They differ whenever anything pushed between the last pass
and the verdict, which is exactly when the line would be a lie, and it is the cheapest
possible check: one `rev-parse` against a value already in hand.

`ready` here means *the gates and the review agree at this SHA* — it is not merge
approval. The human owns the merge, and is free to merge over a `blocked` verdict; the
verdict's job is to stop **the runner** from claiming a clean state it did not verify.

### §8 Cleanup

Remove every `pr-ready-$REF-*` worktree this run created (`$REF` from §1 — the same symbol
§4.3 named them with). `/code-review`'s own `pr-<N>` worktree is not yours to remove.

**Then assert it, in the same breath — substituting `REF`'s value as a LITERAL** (shell
variables do not survive between Bash tool calls, and an empty `$REF` makes the pattern
`pr-ready--`, which matches nothing and passes silently: the very failure this assertion
exists to close). `-qF`, not bare `grep`: a grouped ADW `REF` contains `+`
(`<slug>-uNN+uMM`), which `grep -E` reads as a quantifier. And branch on the match rather
than chaining `&& echo`, whose exit code is inverted — clean would exit 1, dirty 0:

```bash
if git worktree list --porcelain | grep -qF "pr-ready-<the REF literal>-"; then
  echo "CLEANUP INCOMPLETE"; else echo "cleanup clean"; fi
```

`CLEANUP INCOMPLETE` → say so on the verdict line and name the paths. A removal that quietly
failed looks exactly like a removal that ran, which is how three of these accumulated across
three runs before a retro counted them (2026-08-01). Sweeping other runs' leftovers is
`/cleanup`'s job, not yours — but a leftover of *your own* `REF` is yours, and unreported it
is a half-executed section reported as a whole one.

**The delegation to `/cleanup` is only real because row 8b exists.** `$VWT` is created
`--detach`, so `/cleanup` Phase 2 classifies it as a detached worktree — and row 8 parses a
PR number **out of the directory name**, which `pr-ready-<N>-v1` carried and the ADW form
`pr-ready-<slug>-uNN-v1` does not. Worse, a blocked/failed unit's PR stays **open** at that
head (adw-build §3.5), so any rule keyed on "no open PR has this OID" is false for exactly
the case that needs reaping, and the worktree sits in row 9, "Skip — not stale", forever.
Row **8b** therefore keys on the **prefix**, not on PR state: a `pr-ready-*` worktree is a
throwaway verify checkout and never any PR's working tree, so clean + detached + the prefix
is sufficient. Do NOT "fix" this by suffixing `REF` with the PR number: `REF` must be one
value across every `PASS` of a unit (§1), and pass `v1` runs before a number exists.

---

## Callers

`/adw-build` §3.4 and §3.6 delegate here, passing `BASE`, `PASS` **and `REF`** explicitly
(§1 makes `REF` a required override for that caller) and adding
its pipeline-control layer on top (mutation check, progress conditions, chain state, run-report/PR-body
surfaces). When a rule in this file changes, that is the caller to re-read — and the only
copy of these rules that should exist is this one.
