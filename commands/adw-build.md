---
description: "ADW do side: consume approved specs/plans → worktrees → gates → independent verification → PRs → /code-review loop → ready|blocked|failed. An unknown slug routes to /adw-init first. Usage: /adw-build <intent-slug>"
---

# /adw-build — from contract to PR

> **Phase 0 reads [`adw-core.md`](adw-core.md) first** — header schema (§2), chain
> conventions (§5), consent carve-out (§6), run-report and PR-body templates (§7), dispatch tier (§8 —
> binds every `Agent` call this file makes), the contract source (§9). **It also reads
> [`pr-ready.md`](pr-ready.md), [`review-core.md`](review-core.md) and the consuming repo's
> `.claude/repo-profile.md` end-to-end** — §3.4 and §3.6 delegate their
> bodies to the first two, the third holds every repo-specific path, branch, gate, trap domain and
> environment fault this file cites as `repo-profile §N`, and `.claude/commands/*.md` are prompt
> templates with **no auto-include** (`review-core.md` header), so an unread pointer leaves the
> verify/review contract loaded nowhere and the pass gets improvised. Design rationale and
> evidence: the design doc `repo-profile §2` names, §4.
>
> **This file lives in the `adw` repository and is fetched, not copied** (adw-core §9). It is
> repo-agnostic: every value that could differ between repos is in `repo-profile.md`.
>
> Orchestration runs in THIS session and cannot be
> delegated wholesale to a subagent — the Workflow tool is main-session-only (design
> §4.9), and cycle counting + worktree creation are the orchestrator's, never a
> subagent's (recorded incident: self-served EnterWorktree branched fresh off origin and
> stranded commits). Implementers and verifiers are subagents.

**Input:** `$ARGUMENTS` = intent-slug. Empty → list candidate intents by header
(`grep -rl '^intent: ' <specs-dir> <legacy-specs-dir> | xargs grep -h '^intent: ' | sort -u`;
`<specs-dir>` and `<legacy-specs-dir>` are `repo-profile §2`'s values, here and everywhere
below — a repo that declares no legacy root simply drops the second path) and stop.

**Unknown slug → route to `/adw-init`, do not stop.** A first-time user reaches for
`/adw-build` because it is the command that names the thing they want, and stopping with a
list of slugs they have never seen tells them nothing about the phase they skipped. Before
Phase 0, resolve the argument against **three** sources — all must come back empty:

```bash
git fetch origin --quiet                                       # REQUIRED: this runs
                                                               # BEFORE Phase 0's fetch
grep -rl "^intent: $SLUG\b" <specs-dir> <legacy-specs-dir>            # uncommitted, main tree
git grep -l "^intent: $SLUG\b" origin/<default base> -- <specs-dir> <legacy-specs-dir>   # committed
git ls-remote --heads origin "adw/$SLUG-*"                      # already building
```

The second and third are not optional. Specs stay uncommitted in the main tree until build
lands them (adw-core §1), so a `/adw-build` run from a worktree, or a resume after
build committed them to `adw/<slug>-u1`, sees an empty first grep and is NOT a new intent.
Then:

- **Any source non-empty** → the intent exists; continue to Phase 0 as today.
- **All empty, but a candidate slug is a near-match** (the argument is a prefix, suffix or
  edit-distance-1 of one) → print `did you mean <slug>?` and stop. Never init a typo.
- **All empty, no near-match** → print exactly one line —
  `no spec for \`<argument>\` — starting /adw-init first` — and invoke `/adw-init
  <argument>` with the argument verbatim as the intent. Init runs its OWN Phase 0; this
  file's Phase 0 does not run first and its `CONTRACT_SHA` is not pinned here. Where init goes next is init's Phase 5 decision, and
  a clean `approve` comes back through this file's Phase 0 by the normal route.

**Skill tier (design §4.9):** this loop and every artifact it consumes may reference
plugin skills (`superpowers:*`, `code-review:code-review`), tracked commands
(`.claude/commands/*.md`) and tracked skill dirs ONLY. Repo-local symlinked skills
(`.claude/skills/*` → `.agents/`) do not exist in worktrees — do not add such a
reference in a future edit of this file.

**Session-boundary provenance (adw-core §6 corollary):** the merge carve-out requires
provenance THIS session established. After any session boundary — compaction that loses
the run state, crash, or a fresh invocation — every already-open adw PR is human-owned:
resume may build the next units, but it never merges a PR the current session did not
itself open and carry to `ready`. **This binds hardest on a `ready` sub-PR still awaiting
its §3.7 merge: if run state was lost, do not merge it — halt the chain and report it on
the run report as human-owned.** Long runs compact (the 10-unit `subscription-locks` run did, 8 times);
compaction is not schedulable from inside the loop, so the durable defences are the ones
that survive it — §3.4's evidence block in the PR body, the `fix-attempt-N`/`fix(review):`
prefixes step 7 recovers counts from, and re-deriving `$VSHA` and the base rather than
trusting a remembered value.

**Never:** `git stash` (repo-global, shared across worktrees) · draft PRs (permanently
review-ineligible) · merge anything targeting the default or production branch
(`repo-profile §3`) · merge a PR whose
provenance this session did not establish · resolve a sync conflict unattended · edit a
gate file to get green · let a subagent create its own worktree.

## Phase 0 — resolve the contract

1. `git fetch origin` — every diff-scoped step below breaks silently on stale refs.

   **Pin the contract.** The loader stub already fetched it before this file was read (adw-core
   §9), so there is nothing to check — only something to record:
   ```bash
   CONTRACT_SHA=$(git -C <cache> log -1 --format=%h)
   ```
   **Substitute the resulting value as a literal** wherever it is printed: shell variables do not
   survive between Bash tool calls. It goes on the run report's `note contract` line (adw-core §7)
   and in §3.4's evidence block, under that name, and it is the same value in both — one repository,
   one commit.

   Do **not** re-fetch or re-compare it later in the run. A run starts on one contract version and
   finishes on it. The old contract-freshness check existed because each repo held its own copy and
   a copy could be stale; it ran after the skill text had loaded, could not self-correct, and
   shipped inside the file that might itself be stale. Two runs executed a superseded contract with
   it in place (design §10 v2.7, v2.12). Fetching before reading retires the whole class.

2. Labels: run the two idempotent creates from adw-core §5.
3. Locate specs: `<specs-dir>/????-??-??-<slug>/` (multi-unit) or
   `<specs-dir>/????-??-??-<slug>.md` (single-unit flat) — **and the same two shapes under
   `<legacy-specs-dir>`** for an intent born before that repo's artifact-root cutover
   (adw-core §1). One slug resolves in exactly ONE root; a slug found in both is the same
   refusal as two dated folders. Anchor the date, or
   a bare `*-<slug>` also matches `<date>-<other>-<slug>` and the refusal below fires on
   an unrelated run. **Two FOLDER matches for one slug → refuse the run** naming both
   paths: intents are append-only (adw-core §1), so a second folder means a later batch
   minted one instead of extending — picking the newest would silently drop the earlier
   units from the manifest. A folder AND a flat file for one slug is legal: that is an
   extended single-unit intent, the flat file being its first unit's spec (adw-core §1.1)
   — parse both into one manifest.
4. Parse every spec header (adw-core §2). Any missing required field, duplicate unit id,
   an `intent:` value that does not equal the slug, an `after` cycle, or a `base:`
   present on some units but not all (or with differing values) → refuse the whole
   run, print what to fix, stop. No partial builds on a broken manifest.
5. **Base resolution:** `INTENT_BASE` = the intent's `base:` header value, default
   `repo-profile §3`'s default base; `git ls-remote --heads origin <INTENT_BASE>` must return it,
   else refuse. From here every `origin/<default base>` in this file — **and every bare mention of
   it as a branch point or PR base** — means `origin/<INTENT_BASE>`: chain open, unit branches,
   PR bases, stale-base checks, resume enumeration, final-PR target, and the
   default-base fallback of §3.4's audit anchor. §3.4's `<BASE>` is a DIFFERENT,
   per-PR-type placeholder — a sub-PR still audits against `adw/<slug>`; do not conflate
   the two names. EXCEPT the consent boundary
   (adw-core §6: PRs targeting the default base, the production branch, OR the intent's base
   branch all need the human), which always mean the literal branches. Non-default `INTENT_BASE`
   prints on the run report `note` row. Three straight runs needed a non-default base; run-5
   abandoned `/adw-build` for want of it — design v2.8.
6. Reconstruct topology: independent PRs (respecting grouped packaging) + chains ordered
   by `after`.
7. **Recover the cycle counts before anything else in this step** — they are the operative
   stop metric now (§3), and a session boundary must not reset them. For every unit being
   resumed, against **`origin/<unit-branch>`** and the unit's own `<BASE>` (sub-PR →
   `origin/adw/<slug>`, else `origin/<INTENT_BASE>`):
   ```bash
   # fix cycles: the HIGHEST N present, never the commit count
   git log --format=%s <BASE>..origin/<unit-branch> \
     | grep -oE 'fix-attempt-[0-9]+' | grep -oE '[0-9]+$' | sort -n | tail -1   # empty ⇒ 0
   # review cycles: an UPPER BOUND only — see below
   git log --oneline <BASE>..origin/<unit-branch> | grep -c 'fix(review):' || true
   ```
   (`|| true` because `grep -c` exits **1** on a legitimate count of `0`, which the harness
   reports as a failed call.)

   **Count cycles, not commits.** One cycle routinely lands several commits — §3.2 says a
   failed PR must be reviewable as `feat` + `fix-attempt-1..3` rather than one blob, and an
   implementer handed four findings writes four. On `team-active-seat-model` the commit count
   read **7 / 5 / 6** for u4 / u7 / u6 against true cycle counts of **2 / 1 / 1** — every one
   of them past the cap of 3, so resuming any of those units would have hard-stopped a unit
   that had cycles left. This is the `fix-attempt-4` incident (#829) inverted: that fix
   closed an undercount across a resume, and the naive counter it installed overcounts within
   one. `fix-attempt-N` carries its own cycle number, so take the max and the ambiguity is
   gone.

   `fix(review):` carries no number (`code-review.md` fixes the literal prefix, and a
   standalone `/code-review apply` has no ADW cycle to name), so its commit count is an
   **upper bound** — several commits sharing one cycle is allowed, and only a tripwire.
   The authoritative count is the **prior session's own evidence block**, which §3.4 wrote
   into the PR body and adw-core §7.2 keeps fetchable forever:
   ```bash
   gh pr view <N> --json body --jq '.body' \
     | sed -n 's/.*cycles .*· review \([0-9]*\)\/.*/\1/p' | head -1   # empty ⇒ no block
   ```
   **Not the PR's review submissions — there are none to count.** `/code-review` reports via
   `gh pr comment`, so `.reviews` is empty on every adw PR and a count of it reads `0` on a
   unit that has spent both cycles. §3.6's fetch is a different quantity in a different
   place: an existence *floor* dated against the code head (`/pr-ready` §5), and it runs
   later in this session's per-unit loop — at resume nothing has fetched it yet.
   No block (a PR predating §3.4's block, or a run that died before 3.5) → fall back to the
   `fix(review):` commit count as the upper bound and carry a `note` saying which was used.
   Never fail a unit on the commit count alone.

   **The `origin/` ref, never the local one** —
   `/cleanup` deletes local unit branches whose PR merged or whose upstream is `[gone]`, and
   a missing ref makes `git log` error, `grep -c` print `0`, and the counter silently reset:
   the exact failure this step exists to close. A ref that does not resolve is a **hard stop**
   (`blocked`, "cannot recover cycle counts for uNN"), never a `0`.
   Seed the orchestrator's counters and print `resumed-from N` in the PR-body evidence block
   (§3.4). A prior run shipped **`fix-attempt-4`** against a cap of 3 because the counter
   restarted across a 3-day, two-sync resume (retro 2026-08-01, #829). The prefixes are the
   durable record: `fix-attempt-N` is mandated by §3.2, `fix(review):` by §3.6 below.

   Resume (adw-core §5): enumerate every adw PR for the slug — merged, open AND
   closed-unmerged, across BOTH bases (`adw/<slug>` and `<INTENT_BASE>`; independent units
   target `<INTENT_BASE>` and are invisible to a chain-only listing); map head branch + title
   (`+`-separated unit field) → unit ids. Merged units are skipped. **A still-OPEN adw
   PR for a unit of this intent (blocked/failed/ready from a prior session) is
   human-owned** (see Session-boundary provenance): do not duplicate it, do not merge
   it — its chain halts at that unit, the run-report line says `blocked #N — pre-existing PR
   from a prior run; merge or close it, then re-run`. A CLOSED-unmerged adw PR is
   owner-decided: do not rebuild — its chain halts `blocked` at that unit (run report: `closed
   by owner — reopen or re-cut, then re-run`) unless the unit's spec changed after the
   close. A pre-existing unit branch with no PR and NO registered worktree is stale
   state: delete it (local AND any `origin/` leftover — a pushed branch whose
   `pr create` failed collides non-fast-forward on rebuild otherwise) and rebuild. A
   REGISTERED worktree for the unit (`git worktree list`) may be a concurrent session
   mid-build (two agents in one working tree lose changes): never delete it — refuse the run naming the
   worktree; same-intent concurrency is unsupported.
8. Gate-coverage note per unit (design §2.2 rollout rule): persistence unit with no
   integration test in `verify`, or UI unit with no e2e/unit-test coverage (`repo-profile §6`
   maps the layer to its gates) → the
   unit still builds — the human already saw the coverage concern at the init approval gate,
   which is the targeting decision point — but its PR body and run-report line carry
   `· ⚠ no trustworthy gate sees this unit's correctness`.

## Phase 1 — scheduling

- **Timing series (adw-core §7.1):** reached via `approve` (adw-init
  Phase 5 step 3), continue init's T-series — do NOT restart it. Invoked fresh, stamp T0 here and report `your gate 0m`.
  Any mid-run halt for an owner answer stamps its own T1/T2 pair into the gate total.
- **Halt only where §6 binds, and batch what you halt for.** The run stops for exactly two
  things: a merge outside adw-core §6's consent carve-out, and an escalation the owner alone
  can settle (§3.6 → `blocked`). **A progress report is not a halt** — print it and keep
  building; the owner reads the run report at the end. When two or more units are ready to ask something,
  ask once with every question numbered (adw-core's approval-surface shape): on
  `team-active-seat-model` one halt cost **90 minutes** and was answered `proceed with
  defaults`, which is a question that should have been carried on the run report rather than blocking a
  chain overnight.
- **Stamp `owner-wait` from T1/T2 pairs; never infer it from a gap in the transcript.** The
  same run shows why. Idle blocks with no orchestrator and no subagent activity totalled
  ~5.2h, and they are **indistinguishable post-hoc**: 1.7h were genuinely the owner, and
  3.45h were the machine — a backgrounded `git fetch` that foreground-timed-out at 15.7 min
  and only returned 2h later, plus the ~15-min turns a sleeping host produces. The single
  longest block (1h51m) looks exactly like an owner gate — it even opens with a status table
  posted while units were unbuilt — and ended with a `<task-notification>`, no human within
  two minutes either side. Charging that to the human libels the owner and hides a machine
  fault; charging the owner's real 90 minutes to the machine hides a schedulable halt. Only
  the stamps separate them, which is the whole reason adw-core §7.1 defines them.
- **Independent PRs build in parallel** — one worktree each; never two agents in one
  working tree.
- **Chains build by DAG level, not in a line.** `after:` (adw-core §2) is a graph the init
  phase already validated acyclic — schedule against it. Units whose `after:` sets are all
  satisfied are **siblings** and build concurrently, one worktree and one unit branch each,
  all cut from `origin/adw/<slug>`. Two exclusions, checked before a level starts:
  - **Migration siblings serialize**, where the repo has migrations at all. Two units that both
    author one share whatever ordering key the migration runner reads — a shared high-water mark
    that must not be raced. Build the lower unit id
    first; the other joins the next level. `team-active-seat-model`'s u4 says this in its own
    spec — its `after: [u1]` is a *migration* dependency, nothing in it reads u1's column.
  - **File-overlap siblings serialize.** `after:` declares a *logical* dependency; it does
    not promise disjoint files. Plans here are dense with `path:line` references, so
    intersect them:
    ```bash
    # roots and extensions are repo-profile §2's source roots and code extensions
    paths() { grep -ohE '(src|api|packages|scripts)/[A-Za-z0-9_./-]+\.(ts|tsx|sql|css|json)' "$1" | sort -u; }
    comm -12 <(paths <plan-A>) <(paths <plan-B>)   # any output → serialize
    ```
    **Rooted at a source directory and excluding `.md` on purpose** — the loose form
    (bare basenames, any extension) matches `CLAUDE.md`, the umbrella docs and every
    barrel file in the repo, and made all three of `team-active-seat-model`'s L1 siblings
    collide. That version of the rule is a no-op wearing a check's clothes. The rooted form
    on those same plans returns nothing for u2↔u3 and u3↔u4, and for u2↔u4 returns
    `billing.ts`, `PricingContent.tsx`, `TermosAssinatura.tsx` — which is right: u4's plan
    says in prose that the roster wording in `TermosAssinatura.tsx` is u2's, under a
    *Handoff* heading. The grep found a declared handoff on its own. Still coarse, and a
    false hit costs only the serial order the pipeline had anyway, so never tune it toward
    judgment.

  **Cap the level at 2 concurrent units** and serialize the gate stage inside a level
  (implement in parallel, gate one unit at a time) — `repo-profile §10` §Parallel-gate isolation
  states what this repo's worktrees do and do not share. Raise the cap only after a run reports no
  cross-unit gate flake.

  **A sibling that merges first leaves its twin behind, and that is fine — do not rebase
  it.** Both branched from the same `origin/adw/<slug>`; when the first merges, the second is
  simply behind its base, which is the ordinary sub-PR shape. §3.7's merge assertion still
  holds (`baseRefName` unchanged, `headRefOid == $VSHA`) and Phase 4 replays the three-way
  merge for every file both parents touched at chain close. Rebasing mid-level would break
  §3.7's `--match-head-commit` and re-open the verified head for no gain. The one thing that
  must NOT happen is the second sibling silently inheriting the first's work: its verify base
  is derived (`git merge-base adw/<slug> <unit-branch>`, adw-core §5), which stays correct
  because it is derived at use, not stored.

  Measured across two intents, a level schedule beats the serial one by roughly a quarter of
  wall-clock (14.29h → 10.87h on `team-active-seat-model`), and both figures are lower
  bounds. Nothing in the pipeline was choosing this: 12 of 14 implementer dispatches over
  four intents never overlapped another implementer at all (design §10 v2.15).
- **Chain open:** `git branch adw/<slug> origin/<INTENT_BASE> && git push -u origin adw/<slug>`.
  From here on `origin/adw/<slug>` is the ONLY source of truth for the chain — sub-PR
  merges advance origin alone, the local ref goes stale immediately, and every chain
  read below keys on the origin ref. A pre-existing branch (resumed chain) is NOT
  required to contain current `origin/<INTENT_BASE>` — divergence is normal, the sync happens
  once at chain close (Phase 4). On resume, report the lag
  (`git rev-list --count origin/adw/<slug>..origin/<INTENT_BASE>`) in the run report `note` row and
  continue.
- **Parallel-gate caution: `repo-profile §10` §Parallel-gate isolation owns this.** It states
  which gates isolate themselves per worktree, which share state, and which env flag defeats the
  isolation (never set inside a run). Read it before scheduling two units on one level. A shared
  stateful gate is what produces reds that look unit-caused and that §3.3's connection-refused
  classifier will not intercept. If stateless gates still flake each other, serialize the whole
  gate stage: implement in parallel, gate one PR at a time.

## Phase 2 — worktree provisioning (orchestrator, before any gate)

Run as **one Bash invocation** — cwd resets between calls in this harness, and a
half-provisioned worktree symlinks into (or runs gates against) the MAIN repo:

```bash
MAIN="$(git rev-parse --show-toplevel)"
WT="$MAIN/.claude/worktrees/adw-<slug>-uNN"
git branch adw/<slug>-uNN origin/adw/<slug>   # chain — origin ref, the local one is stale after any sub-PR merge; independent units: git branch adw/<slug>-uNN origin/<INTENT_BASE> (same naming)
git worktree add "$WT" adw/<slug>-uNN
# Per-repo dependency + env provisioning. `.claude/repo-profile.md` §4 owns the exact
# commands and the traps. Never improvise this step: a hand-rolled symlink is the
# documented way to corrupt the MAIN checkout.
```

Conditional provisioning — these are setup, not fix cycles:
- every diff-triggered block `repo-profile §4` declares, per `review-core.md` §1.2, which owns
  them for every worktree this contract stands up. One copy; do not restate;
- stale-base check at unit start: independent units
  `git merge-base --is-ancestor origin/<INTENT_BASE> HEAD`; sub-PR units
  `git merge-base --is-ancestor origin/adw/<slug> HEAD` (origin ref; load-bearing on
  resume with a leftover unit branch — the branched-far-behind incident class).

## Phase 3 — the per-PR loop

```
implement ⟲ gates → verify → open PR → /code-review ⟲ → re-verify → ready | blocked | failed
     ↑________|                            ↑______|
     max 3 cycles                          max 2 cycles
```

**Progress, not elapsed time, terminates a loop** (v2.12; the 45-minute bound it replaces
is design §4.8). Record `date +%s` at **PR start = this loop's first implementer dispatch
(3.1)**, never `gh pr create` (3.5 runs after gates+verify — anchoring there would make
every `⏱` incomparable across runs). That number is **reported, never a trigger**.

Wall-clock cannot tell a slow serialized gate from a confused implementer: an integration suite
may be single-forked by config, a unit suite grows every week, and §3.2 obligates a D3 migration
unit to gates a D0 CSS unit never runs. Gate
cost tracks depth, so a flat budget in seconds binds hardest on the cheapest units — which
is backwards, and is why one unit skipped per-file mutation on **31 changed files** while
nothing enforced anything on a 26-hour run. Ten runs and 34 PRs produced **zero** `adw:failed`
and **zero** `adw:blocked` from the bound, and **zero** surviving `⏱` stamps — the
recalibration dataset §4.8 promised does not exist (retro 2026-08-01). Observed fix depths:
**19** (#828), **4** (#829, a counter reset across resume — Phase 0 step 7 closes that), **2**
elsewhere. So the caps are not a redundant second backstop that made the clock unnecessary;
they are the **only** backstop, they were breached once, and that is the argument for making
them countable rather than for trusting them.

**At every phase boundary (gates → verify → PR open → review → re-verify), evaluate the
six progress conditions, and stamp `date +%s` at each (the phase split the PR-body
evidence block reports is exactly these stamps; one stamp at PR start cannot produce it).
Any one fires → finish the phase in flight, then abort →
`failed` if the PR is not terminal:**

1. **No cycle beyond the caps.** Fix cycle **4 never starts** — cycle 3 runs, and its
   exhaustion is `failed` (§3.2). Review cycle **3 never starts** — cycle 2 runs, and its
   verdict stands as `/pr-ready` §3 returns it, which is **`blocked`**, not `failed`
   (§3.4 verdict routing). The caps permit the cycle they name; this condition stops the
   one after it.
2. **Repeated error signature.** The red at cycle N carries the same
   `(gate command, first failing test id or `TSxxxx`, NORMALISED assertion message)` as
   cycle N−1. Two consecutive matches is a loop, not progress; it fires *ahead* of the
   3-cap. **Normalise before comparing** — strip numeric and quoted-string literals, so
   `expected 3 to be 4` and `expected 3 to be 5` are the same signature. Comparing raw
   messages does not soften this condition, it disables it: test runners embed received values,
   so almost every attempt yields a distinct string. The test id must match too, which is
   what keeps a genuine two-part fix (different test, same gate) from tripping it.
3. **Gate regression.** A gate **green** at cycle N−1 is **red** at cycle N. Re-run that
   gate alone once first, then route the red through **§3.3's environment classifier like
   any other** — a shared-cache flake between worktrees is an environment fault (`repo-profile §10`)
   and costs no cycle, by §3.3's standing rule. Only a red §3.3 calls genuine consumes a fix
   cycle, and the condition terminates only on a *second consecutive* genuine regression.
   A single one is an ordinary fix cascade — widening a type to clear the type check reds the
   bundler — and killing a unit at cycle 2 of 3 for it would be this rule's version of the
   old clock's mistake. The vector is **three-valued** (`green | red | not-run`): §3.2 stops
   at the first red, so downstream gates are `not-run`, and `not-run → red` is not a
   regression. Only `green → red` is.
4. **Diff oscillation.** For any two `fix-attempt` commits on the unit branch,
   `git -C "$WT" diff <ci> <cj>` is empty — the branch has returned to a tree it already
   had. `git -C "$WT" log --format=%T <BASE>^..<unit-branch> | sort | uniq -d` is the cheap
   form and catches only an exact A→B→A; prefer the pairwise diff, because an implementer
   bundling a revert with its replacement produces a *new* tree every time. **`-C "$WT"`
   and the unit branch by name, never bare `HEAD`** — the orchestrator's own cwd is the main
   repo on `<INTENT_BASE>`, where `<BASE>..HEAD` is empty and the condition can never fire.
   `<BASE>^`, not `<BASE>`, so a revert all the way back to the base tree is visible.
   **Precautionary, not evidenced** — no run has ever tripped it (design §10 v2.12.1).
   Exempt a deliberate `git revert` of a reviewer-rejected fix and a mutation-check restore.
5. **Stall.** Two consecutive boundaries at which the triple
   `(git rev-parse HEAD, gate exit-code vector, gh PR state)` is unchanged (`not-run` slots
   count as unchanged). Nothing advanced and nothing will. Bookkeeping — a PR-body edit, a
   base assertion — is not advancement: it moves none of the three.
   **Evaluate this ONLY at a boundary closing a REPEAT cycle** — a fix cycle, or a review
   pass that pushed. It inherits the carve-out below: a first pass is a completion, and a
   completion legitimately changes nothing. On a green zero-finding unit the triple is
   *supposed* to sit still — `verify` commits nothing, and `/code-review` with an empty
   `toFix` skips its apply steps entirely — so an unscoped condition 5 fires on the
   **clean happy path** (gates→verify unchanged, then review→re-verify unchanged) and
   ships the ideal run as `failed`. Nothing else in the six is this easy to invert.
6. **Boundary cap: 16 boundary crossings for one PR** → `blocked` (not `failed` — the work
   is gate-green, just unconverged), `default: re-run /adw-build <slug>`. This is the
   backstop the other five do not provide, and it is deliberately the last resort. A unit
   that never reds a gate spends **zero** fix cycles, so conditions 1–3 never evaluate; if
   it also commits each pass (refactor → re-check → refactor) conditions 4 and 5 never fire
   either — a real shape, not a hypothetical (design §10 v2.12). Count boundaries, not
   minutes: it is the one quantity that
   rises monotonically no matter what the implementer does. **16, not 12:** a fully-loaded
   legitimate run is 5 base boundaries + 3 fix-cycle gate passes + 2 review boundaries = 10,
   and a §3.6 void re-pass adds more — a cap of 12 would trip on a run that did everything
   right. Size it above the legitimate maximum or it becomes the 45 again.

**The FIRST pass of a mandatory stage always runs, and no condition above suppresses it:**
the 3.4 verify, the single 3.6 review, **and Phase 4's composition review**. Each is a
completion, not a loop. Two runs shipped PRs unreviewed by reading the old clock literally
on a zero-fix-cycle run (design §10 v2.7 + v2.8); the count is three stages now, not two.

**One clock survives, sized not to bind: 4 hours inside a single phase with no boundary
crossed** → `failed`, classified as an environment fault under §3.3. Sized against the
largest legitimate single-phase run on record (31-file per-file mutation, ~90 min
projected) with ~2.7× margin. Never re-size it from per-PR totals; that is the error the
45 made.

**Be honest about what it can catch.** A subagent that returns nothing leaves the
orchestrator blocked *inside* the `Agent` call, which takes no timeout — so no check of any
kind runs, and this ceiling is evaluated at the *next* boundary, as a post-hoc `failed`
classification rather than a live trigger. It genuinely bounds a phase built of many
returning calls; it does **not** bound a true hang. A hung *gate* is already bounded — the
`Bash` timeout maxes at 600000 ms. If a live bound on subagent hangs is ever wanted, the
mechanism is background dispatch plus `Monitor` polling, not a number in this paragraph.
**Precautionary, not evidenced** — no run has yet produced a hung subagent.

Every run-report PR line still carries `· ⏱ <N>m`, and §3.4 lands it in the **PR body** where it
survives the session (adw-core §7.2). Reported, not enforced.

**Reading discipline.** File reads are 23% of what enters this loop's window and dispatched
subagent reports are only 10% — dispatching is not what fills the window (design §10 v2.13).
So: a file read in order to **edit** it stays inline, you need the content; a file read to
**answer** something (does this symbol survive, which surfaces does this rename touch) is
what a subagent returns in ~2 KB. Check size first (`wc -c`/`wc -l`) and narrow with
`offset`/`limit` or `grep` — a small read stays inline, where a dispatch would cost more than
it saves and trades a `Bash` call bounded at 600 000 ms for an `Agent` call bounded by
nothing (§3). This governs the orchestrator's own reads; subagent-internal spend is ~4.3×
larger, which **adw-core §8** rules on by tier, not by volume (design §10 v2.15 — and when
measuring any of this, dedup by `message.id`; summing per transcript record multi-counts).

**Every `Agent` call this loop makes declares `model:` — adw-core §8 owns the table.** Do
not restate it here and do not reason about the tier per dispatch: look it up. The rule
exists because an omitted `model:` is invisible everywhere except the bill (37 unpinned
dispatches were 91% of the `team-active-seat-model` run's subagent cost), and because two
narrower pin rules had already been written and neither generalised.

### 3.1 Implement

One implementer subagent per PR, working in the provisioned worktree, **pinned by the
unit's `depth:` per adw-core §8** — `model: opus` at D3, `model: sonnet` at D0–D2. A
grouped sub-PR takes the tier of its deepest unit. D3 → follow the plan file; D2 → follow
the spec's `## Implementation` section (adw-core §3); D0/D1 → implement from the spec.
Units sharing a sub-PR: **one commit each, dependency order**. Keep the SAME implementer across fix cycles via SendMessage — the ORCHESTRATOR
counts cycles (caps enforced by prose drift; counted caps do not). A fix cycle re-uses that
implementer at the tier it was dispatched on; never re-dispatch a cycle at a higher tier to
"try harder" — a second consecutive genuine regression is §3's stop condition, not a tier
signal.

The unit's spec/plan live UNCOMMITTED in the MAIN repo tree (`/adw-init` writes
documents only): pass their absolute main-repo paths in the implementer prompt —
read-only access breaks no isolation. The implementer's FIRST commit copies the spec
(and its plan file, D3 only) into the worktree at the same repo-relative paths, so each PR lands its
own contract — adw-core §1's durable record becomes true at merge.

**Once that commit exists, the orchestrator DELETES the unit's main-tree originals**
(`rm` the exact spec/plan paths — untracked by contract, so no git surgery). The PR
branch is the carrier from here; a failed/blocked PR still holds them. Leftovers collide
with the merged paths at the next `git pull` — checkout refuses over untracked files
unless byte-identical, and any post-copy edit breaks identity (run-1). Resume is
unaffected: a unit with a PR is enumerated via Phase 0 step 7, not via its main-tree
spec — which is also why extending an intent (adw-core §1.1) reads merged units' specs
from git rather than the main tree.

**Depth-envelope check (D0/D1 units).** After implement, before gates: if the unit's
diff touches any trap domain from adw-core §3's D1 negative list (`repo-profile §11` — any path
prefixes plus the grep proxies, as pinned there), the depth promise is broken — halt `blocked`, PR body:
`depth escalation — diff touched <path>; re-run /adw-init at plan`. "Looks trivial" is
unfalsifiable at triage; the diff is not. A misclassified unit costs a bounce, never a
shipped trap. A diff exceeding the ≤4-source-file bound WITHOUT touching a trap domain
does not bounce — it carries `· ⚠ depth envelope: N source files (spec promised ≤4)` on
its run-report PR line (size is a proxy; the trap list is the risk).

### 3.2 Gates (cheapest first, run in the worktree)

The gate list and its ordering live in `repo-profile §5`; which gates a given diff obligates lives
in `§6`; the single-test invocation traps in `§12`; the environment-fault list in `§10`; worktree
provisioning in `§4`. Read them before the first gate — they are the contract. `<BASE>` is
`adw/<slug>` for a sub-PR, otherwise the chain's origin base.

Three properties hold in every repo, whatever that file declares:

- **Cheapest first.** Ordering is not cosmetic; a type error found in ten seconds must not cost a
  full test run.
- **Conditional gates are computed from `git diff --name-only <BASE>...HEAD`, never judged.** A gate
  the diff reaches is not optional because it looks unrelated to the change.
- **A gate that inspected nothing is not a pass.** Where a repo's audit-style gate can be handed an
  empty scope, `repo-profile §5` states how to opt in explicitly. Reaching for that opt-in to turn a
  real code change green reinstates the exact lie the exit code exists to close.
- **Mutation check (design §2.2(5)) — the unit's `verify` must be able to fail.** Once
  the gates first go green, neutralise the unit's changed PRODUCTION files (tests stay),
  scoped by `git diff --name-status <BASE>...HEAD`: `M`/`D` paths →
  `git checkout <BASE> -- <path>` · `A` paths → delete the file (it does not exist at
  `<BASE>`; a plain `checkout <BASE> --` pathspec-errors on it and can leave a partial
  revert). Re-run the unit's `verify` command — it MUST go red. Then restore the mirror
  image: `M`/`A` → `git checkout <unit-branch> -- <path>` (in a verify worktree:
  `$VSHA`) · `D` → delete again. (File-level neutralisation is deliberately coarser
  than design §2.2(5)'s line-scoped wording; for grouped same-file units it conflates
  the units' changes — accepted, the check asserts only that each verify CAN fail.)
  A verify still green against neutralised code is vacuous — feed it to the implementer
  as a genuine red (the test, not the code, is wrong; it counts as a fix cycle). Skip
  only for verify forms with no test to mutate (tsc/grep proofs — design §5.2's
  human-owned residue); the 3.4 verifier's re-run includes this check. This gate is
  what makes the thinner think-side depths (D0/D1) safe: it mechanizes the
  discriminating-verify property the D2+ critical pass provides by hand.
  **Then iterate per file:** neutralise each changed production file ALONE and re-run
  `verify` — a file whose lone neutralisation leaves verify green is mutation-blind;
  carry `· ⚠ mutation-blind: <path>` on the PR/run-report line. Aggregate-green stays the hard
  red; per-file blindness is a flag, not a bounce — some files (a CSS rule, a type
  union) have no test that can see them, and the flag says so honestly. `mutation-blind`
  fires on roughly a quarter of pipeline PRs — the check earns its keep routinely
  (design §10 v2.12).
  Cost is `verify` × N files. **No clock may cut this check** — the per-file sweep is N
  first passes on N distinct files, not loop iterations, and design §5.2 credits the mutation-proof
  as the *sole* system-level detector of a lying gate ("not via the verifier, which re-runs
  the same blind gates") for the exact failure class the design exists to prevent. Trading
  it for a costing proxy inverts the deliverable. **Bound it by file count instead: mandatory
  at D0/D1**; above **2 changed production files** (the count, not the depth — §3.1 lets a
  D1 unit exceed its ≤4 promise without bouncing) iterate **8 files** and report what you covered —
  `· ⚠ mutation per-file 8/31` — so the signal degrades gracefully at every diff size
  instead of dropping to zero above a threshold. **Select those 8 by inverse test
  proximity, never by diff size:** changed production files with no sibling `__tests__`
  entry and no same-name `*.test.*` first, remaining slots by delta. Blindness correlates
  with untested surface, not with line count — a blind CSS rule is small by construction and
  would never rank in a largest-delta top 8. Ranking by delta
  spends the whole budget on the files most likely to already have tests.
  The covered/total ratio goes in the PR body's
  evidence block (§3.4), never terminal-only: "ran, unreported" and "never ran" must stay
  distinguishable.
- e2e narrowing is a standing practice, not a clock concession → **narrow the spec selection
  to the touched surfaces rather than dropping the gate** (design §4.2), and carry
  `· ⚠ e2e narrowed to <specs>` so a shrunk surface leaves a trace — the mutation skip has
  always been flagged and this one never was. Baseline-red e2e
  (the red reproduces at `<BASE>`) ⇒ skip the e2e gate for this unit and carry
  `· ⚠ no trustworthy gate sees this unit's correctness` — the approval gate already approved
  the targeting (design §2.1/§2.2); a baseline-broken suite never terminates a unit.
- Gate commands with `cd` run as subshells against the worktree path — never a bare persistent
  `cd`. `repo-profile §5` writes each one in that form.
- Each red gate → Phase 3.3 classifier FIRST → if genuine, feed the output to the
  implementer → fix lands as its own commit `fix-attempt-N: <what>` (a failed PR must be
  reviewable as `feat` + `fix-attempt-1..3`, never one blob) → re-run from the failed
  gate. Third cycle exhausted → `failed`.

### 3.3 Environment faults abort; they never consume a cycle

Classify every red BEFORE feeding it back — an implementer holding only red output and
its own diff WILL edit source. Abort as environment fault (`failed`, PR body names the
fault, no fix cycle spent):

- any fault in the per-repo list at `repo-profile §10` — dependency/link resolution failures, a
  database or service that is down, a missing env file, a served-build or port unavailable
- a gate red that REPRODUCES at `<BASE>` (run the failing gate once against the base
  checkout when in doubt) — a baseline fault, not the unit's; report it in the PR body as
  such. Exception: the e2e gate — a baseline-red e2e suite skips the gate and the unit
  proceeds with the `⚠ no trustworthy gate` flag (3.2), never `failed`

These wear a test-failure disguise — connection-refused output reads like a red test.
The classifier is the orchestrator's job, not the implementer's.

### 3.4 Verify — re-execution, never a second opinion

**Runs `/pr-ready` §4 — the independence pass.** That file owns the mechanism: resolution
of the verified head **`$VSHA`** (`git fetch origin` → `git rev-parse
origin/<unit-branch>`; the reviewer pushes to origin and the local unit branch never
advances — `$VSHA` is the symbol 3.6 and 3.7 both key on), the gate-file tripwire and its
`clean-checkout evidence` fallback — on a hit that is the **A/B pair**, the PR's own gate
files and base's restored, never one run — the detached fresh checkout and its gate-file
restore, the sonnet-pinned relay verifier, the per-gate evidence table, and the rule
that a report missing an obligated gate's row is a red, never a green. Do not restate any
of it here — one copy, and this file is the caller.

A tripwire hit still routes to `blocked` (3.7) whichever way A and B land; what the pair
changes is the PR body, which must say **which** run disagreed, or that both were green
and the PR therefore needs a signature rather than a fix.

adw-build supplies the parameters `/pr-ready` §1 declares, and adds what only the
pipeline knows:

- **`BASE`** — independent → `origin/<INTENT_BASE>` head · sub-PR →
  `git merge-base origin/adw/<slug> <unit-branch>` · final PR → `origin/<INTENT_BASE>` head
  with the full-branch diff (`git diff origin/<INTENT_BASE>...origin/adw/<slug>`). This is the
  per-PR-type placeholder Phase 0 step 5 warns not to conflate with `INTENT_BASE`; it is
  why `/pr-ready` takes `BASE` as an override rather than always deriving it from
  `baseRefName`.
- **`PASS`** — `v1`, `v2` for the post-review re-pass, `v3+` for a void re-pass (3.6).
- **`REF`** — `<slug>-uNN` (grouped: `<slug>-uNN+uMM`). This pass runs BEFORE 3.5 opens the
  PR, so `/pr-ready` §1's default `<N>` does not exist yet; §4.3 names the worktree and §8
  sweeps it, both off `$REF`. Pass the same value to every `PASS` of the same unit.
- **The mutation check.** The verifier's report must ALSO carry §3.2's red-then-restored
  pair, plus the per-file iteration where §3.2 makes it mandatory. It stays here rather
  than in `/pr-ready` because it is keyed on the unit's declared `verify` command — a
  contract field a generic PR does not have. A report missing it is a red, by the same
  rule as a missing gate row.
- **Where the evidence lands: the PR body, not only a comment.** Copy the per-gate table
  and the mutation row into the PR body at 3.5 (re-pass → edit the body). A review comment
  is the wrong home for the one artifact that has to outlive the run: three PRs across two
  runs reported the mutation row in a comment on one PR and nowhere on the others, and
  nothing could tell afterwards whether the check ran and went unreported or never ran
  (retro 2026-08-01, #838/#841 vs #839). The body is fetchable by `gh pr view --json body`
  forever, survives a re-review that posts a fresh comment, and is where a human merging
  three days later actually looks.
- **The evidence block.** Alongside the table, the body carries one fenced block — the
  whole durable record of how this PR was built. Every field is already computed mid-run;
  cost is one `gh pr edit` per pass. This is what makes the §3 progress conditions
  auditable in the next retro, and it is why they are enforceable at all: a stop metric
  nothing preserves is the exact failure the 45-minute bound died of.

  ```
  contract   <CONTRACT_SHA>            depth D2       resumed-from 0
  tier       author sonnet · impl sonnet · level u2+u3
  cycles     fix 1/3 · review 1/2      progress-conditions none fired
  phases     implement 9m · gates 14m · verify 7m · review 21m · reverify 6m
  owner-wait 0m
  gates      <one field per repo-profile §5 gate the diff obligated: name + exit code>
  mutation   aggregate red · per-file 4/4
  artifact   plan 260L / diff 71L = 3.66x
  ```

  `owner-wait` is the decisive one: it is the single bit that distinguishes a 21-hour
  owner gate from a 21-hour stalled pipeline. Git already exposes the *gap* via commit
  timestamps; only the attribution is missing, and three retros failed on exactly that
  (design §10 v2.12). **Measure it, do not default
  it to `0m`:** any halt that waits on the owner *while this PR is in flight* stamps its own
  `T1`/`T2` pair (adw-core §7.1's mechanism, charged to the unit rather than to the run) and
  `owner-wait = Σ(T2ᵢ − T1ᵢ)` over that PR's pairs; subtract it from the per-PR `⏱`. A field
  reported without being measured is the shape §4.8 just retired the clock over.
  `resumed-from` is the recovered cycle count, not `0` by default — see Phase 0 step 7.
  `tier` records the tiers adw-core §8's depth gate actually selected, and `level` the
  sibling units this one built alongside (Phase 1) — `level none` when it built alone. Both
  are dispatch-time facts that exist nowhere else once the session compacts, and both are
  the sample any later "did the cheaper tier / the concurrency cost us anything?" question
  has to be answered from. the run report's `note tier` / `note level` lines mirror these for the
  terminal; the body is the copy that survives.
  This block is **not** a run database: no file, no directory, nothing to maintain
  (design §5.1 forbids the file, not the PR body).
  On a `blocked`/`failed` PR the body is the PR body template — put the block inside the `<details>` fold,
  never above the decision line (adw-core §7's PR body template).
- **Verdict routing.** `/pr-ready`'s `blocked` maps to adw `blocked` (3.7). A red gate
  goes to the 3.3 environment classifier FIRST; only a genuine red becomes a fix cycle.

Fork-point verification is the accepted bound: an independent/final PR is verified
against its fork point, never re-synced to a base that moved afterwards (3.5
declares that EXPECTED — design §4.8). The human merge gate owns the residual
semantic-conflict risk.

### 3.5 Open the PR (always non-draft)

- Sub-PR: base `adw/<slug>`, title `[adw <slug> uNN] <unit title>`.
  Independent: base `<INTENT_BASE>` (Phase 0 step 5), title
  `[adw <slug> uNN] <unit title>` (grouped:
  `[adw <slug> u2+u3] <title>`). Final PR: base `<INTENT_BASE>`, title
  `[adw <slug>] <intent title>`. Every adw PR carries the bracket prefix — resume
  (Phase 0 step 7) AND extend-mode's id/state recovery (adw-core §1.1) both parse it.
- **Assert the base you asked for is the base you got** — `gh pr create` silently defaults
  to the repo's default branch when `--base` is omitted or misspelled:
  ```bash
  gh pr view <N> --json baseRefName --jq .baseRefName    # must equal the base above
  gh pr edit <N> --base <the base above>                 # only if it does not
  ```
  A non-default `INTENT_BASE` is exactly when this drifts, and the failure is invisible in
  the PR list: an independent unit of a non-default-base intent opened against the
  **default base** 1h51m before that base was absorbed, so the unit shipped to a branch its
  own spec never targeted (design §10 v2.8). **If `INTENT_BASE` merged into the default base
  mid-run** — `git merge-base --is-ancestor origin/<INTENT_BASE> origin/<default base>` succeeds —
  retargeting the remaining PRs to the default base is correct, but it is a decision, not a
  default: name it on the run report `note` row so the topology stays readable afterwards.
- Stale-base recheck at open (the base moves under long runs):
  `git fetch origin`, then a moved `origin/<INTENT_BASE>` is EXPECTED — proceed and let
  `/code-review` handle the moved base at its end (design §4.8). Abort to `blocked` only
  on the pathological case: the PR's target branch is no longer an ancestor of HEAD
  (`git merge-base --is-ancestor <target> HEAD` fails — someone force-moved the base).
- **Measure the artifact ratio at open** (the diff finally exists here, so this is the
  only place it is real): CODE diff lines = `git diff --shortstat <PR-BASE>...HEAD --
  <repo-profile §2 artifact exclusion pathspec>` added+deleted, where `<PR-BASE>` is the base this PR was just
  opened against (sub-PR → `origin/adw/<slug>` · else `<INTENT_BASE>`), NOT §3.4's
  `<BASE>`; artifact lines = `wc -l` of the unit's spec, **plus its plan when D3 has one**
  (D0–D2 units have no plan file — adw-core §3). `artifact_lines > code_lines` → carry
  `⚠ artifact-heavy: uNN <artifact>L docs / <code>L diff` onto the PR's run-report line.
  **Re-count the flat guard rail here too**, on the artifacts as COMMITTED in this PR:
  adw-init Phase 4 counted a draft and the critical-pass revisions land after it, so this is
  the only count taken on the final text. Over the depth's guard rail (adw-init Phase 3's
  budget table — D0/D1 spec 200 · D2 spec 250 · D3 spec 200 / plan 300) →
  `⚠ over-guard-rail: uNN <spec>L[/<plan>L]`; over the 2× hard stop → the same line plus a
  `needs you` note that the unit was mis-cut. Measure, never block — the code is already
  written and gate-green; failing here would burn a correct PR to punish a document. The
  flag is the denominator adw-init's authoring-time ratio has to estimate blind (design §10
  v2.12 + v2.14, run-11).
- `blocked`/`failed` PRs open too — labelled, PR body. Nothing dies silently in a
  worktree.
- **Every adw PR body carries §3.4's per-gate table and evidence block** — stated here
  because this is the section that enumerates what a body contains, and a rule defined only
  at 3.4 is a rule a reader of 3.5 never applies. On `blocked`/`failed` PRs both go inside
  the PR body `<details>` fold, never above the decision line.
- Every adw PR body carries one depth-conditional line, naming the spec/plan dirs
  (`repo-profile §2`) — D3:
  `<specs-dir>/<plans-dir> in this PR = the unit's contract, authored and critical-passed
  at init (design + spec + plan) — review surface is the code diff.` · D2 (one artifact,
  critical-passed whole — adw-core §3): `… = the unit's contract; the spec and its
  `## Implementation` were critical-passed at init — review surface is the code
  diff.` · D0/D1 (no critical pass runs at these
  depths): `… = the unit's contract, authored at init and
  approval-approved — review surface is the code diff; verify discrimination is carried by
  the mutation gate.` Never claim a critical pass a depth did not run. Without the line a
  reviewer treats already-reviewed contract text as findings fodder (design §10 v2.5).

### 3.6 Review loop

**Runs `/pr-ready` §2, §3, §5 and §6** (and, through it, `repo-profile §7`'s gate-file list and
`§9`'s CI coverage). That file owns tier scoring from the code-only diff, the 2-cycle cap, the `since:<sha>` delta scope that makes cycle 2 grade only the fix
(and therefore able to converge at all), the unconverged → not-`ready` rule, the fetched
review-evidence gate (with the `submittedAt` / UTC-normalisation facts it depends on),
and the `$VSHA` void rule. One copy; do not restate.

**`/code-review <N> <tier> apply` IS the review. Dispatching your own review subagents is
not a substitute for it, and not a supplement to it.** `/code-review` carries the §3.1
adjudication bar, the `.agent/review-calibration.md` loop, the §7 safety stops and the
`fix(review):` commit discipline the cycle counter is recovered from; a hand-authored fan-out
of review agents returns findings and none of that, while every downstream surface still
reads "reviewed". On one run `/code-review` ran on 3 of 7 PRs and the other four took 25
review-fix commits that never passed the adjudication bar, with nothing on any surface
saying so (design §10 v2.12.2) — which is why adw-core §7's `note review #NNN` line exists:
if a PR's review did not run `/code-review`, say so on the report. Prefer fixing the tier or
the scope over hand-rolling a replacement — and if a
diff genuinely needs a lens `/code-review` lacks, that belongs in `code-review.md`, where the
next run inherits it.

adw-build always passes `apply` — the recorded push-consent carve-out, and NEVER merge
consent — and adds:

- **Cycle cap only.** Review cycle 2 is bounded by `/pr-ready` §3's cap and by §3's five
  progress conditions — never by elapsed time. The single first review always runs
  regardless: it is a completion, not a loop. Code-only tier scoring still earns its keep,
  now on cost rather than on a deadline — a contract artifact alone can cross the >500-line
  `full` bar and buy a 6-agent pass over documents nobody needed re-reviewed.
- **Every review-driven fix lands as its own commit prefixed `fix(review):`** — no
  exceptions for copy, docs, or plan-card touch-ups. Phase 0 step 7 uses that prefix as the
  review-cycle tripwire, so an unprefixed remediation commit is remediation the next session
  cannot see. #854's review round pushed four commits and only two carried the prefix
  (`fix(copy):`, `docs(plan):` were the others) — a 50% undercount on the most recent run in
  the dataset. Several `fix(review):` commits in ONE cycle are fine and expected; the cycle
  count comes from the evidence block §3.4 writes into the PR body, not from counting these
  (Phase 0 step 7).
- **Escalation → `blocked`**: label, PR body carrying the question + recommended default.
  A blocked sub-PR halts its chain.
- **After the review loop's LAST push, re-run 3.4 in full against the PUSHED head.**
  `/code-review apply` verifies in its own worktree — not the clean checkout with gate
  files restored — so without this re-pass a reviewer edit to `package.json` would be the
  one unchecked path into `ready`.
- **A void the session cannot re-earn** — the review cap is spent, the boundary cap (§3
  condition 6) fired, or the run is ending — lands `blocked`, never `failed`. (Conditions
  1–5 route to `failed` per §3; this bullet covers only the gate-green-but-unconverged
  shapes, where `failed` would libel a correct PR.) The line:
  `blocked  #NNN  <unit> — amended post-review (head ≠ reviewed <sha>); default: re-run
  /adw-build <slug> · ⏱ <N>m`. `failed` would libel a gate-green PR, and `blocked` is
  terminal, so Phase 3's not-terminal abort stops applying to it. (Run-2: an amendment
  pushed after review+verify closed the session as "reviewed clean · ready"; the PR then
  collected two more review rounds.) Commits landing after the session ends are out of
  reach by construction — Session-boundary provenance already makes such a PR
  human-owned.
- **The `blocked` default line names adw**, not `/pr-ready`:
  `default: run /code-review <N> <tier> apply, then re-run /adw-build <slug>`.

### 3.7 Terminal states

| State | Action |
|---|---|
| **ready** | independent/final PR: leave open, run report lists it — the human reviews, previews, merges. Sub-PR: re-assert provenance at merge time — `gh pr view <n> --json baseRefName,headRefOid` must show base still `adw/<slug>` and head equal to `$VSHA` — then `gh pr merge <n> --squash --match-head-commit "$VSHA"` (adw-core §6 carve-out; any mismatch → `blocked`, never merge). Transient `gh pr merge` failure → retry once, then `blocked` (PR body names the gh error). After the merge, `git fetch origin` — the chain continues from `origin/adw/<slug>` (the merge advanced origin only; the local ref is never a source of truth). Squash (or `repo-profile §3`'s merge convention) keeps the integration branch linear (Phase 4's ≤5-commit rebase rule counts cleanly); the `feat` + `fix-attempt-N` commits stay reviewable inside the sub-PR itself |
| **blocked** | label `adw:blocked`, PR body. Sub-PR → chain halts; the halting PR's body lists every unbuilt unit of its chain |
| **failed** | label `adw:failed`, PR body with the last red gate output, non-draft. Sub-PR → chain halts, same bookkeeping |

## Phase 4 — chain close

All units merged → sync the integration branch with `origin/<INTENT_BASE>` in a dedicated
close worktree. The LOCAL ref MUST be refreshed from origin first — sub-PR merges
advanced origin only, and rebasing the stale local ref would force-erase every merged
sub-PR:

**Do not re-check the contract here.** Until the extraction this was the one point in a run far
enough from Phase 0 for the contract to have moved under it, and a re-compare lived here. The
contract now comes from its own repository and is fetched once, before this file is read
(adw-core §9): the run finishes on the version it started on, and the `CONTRACT_SHA` pinned at
Phase 0 is still the right answer at Phase 4.

**Everything below is ONE Bash call.** `$MAIN`, `$CW` and `$N` are all set here and used
here: a variable set in an earlier call is gone, and the failure is silent — an unset `$N`
makes `[ "$N" -le 5 ]` pick a branch by accident of shell (empty coerces to `0` under zsh →
always rebase; exit 2 under bash → always merge), and an unset `$MAIN` writes the close
worktree to `/.claude/worktrees/…` at filesystem root. Neither consults anything real.

```bash
MAIN="$(git rev-parse --show-toplevel)"
CW="$MAIN/.claude/worktrees/adw-close-<slug>"
git fetch origin
git branch -f adw/<slug> origin/adw/<slug>    # refresh stale local ref (refuses if checked out — it must not be)
git worktree add "$CW" adw/<slug>
N=$(git rev-list --count origin/<INTENT_BASE>..origin/adw/<slug>)   # all squash commits — clean count
if [ "$N" -le 5 ]; then
  git -C "$CW" rebase origin/<INTENT_BASE> && git -C "$CW" push --force-with-lease origin adw/<slug>
else
  git -C "$CW" merge origin/<INTENT_BASE> && git -C "$CW" push origin adw/<slug>
fi
```

`&&`, never `||`: a **conflicting** rebase exits non-zero, and `A && B || C` would run `C`
— auto-attempting the very `git merge` the next paragraph mandates aborting. `N ≤ 5` is the
rebase side and `N = 5` is inside it — a five-commit chain closed with a merge commit at
exactly that boundary (retro 2026-08-01, `0c7a82c6`), which is what comparing by eye does
to an inclusive bound. Let the shell take the branch.

A conflicting sync is **judgement work, never resolved unattended**: abort the sync
(`git rebase --abort` / `git merge --abort`), then **still open the final PR** from the
unsynced integration branch, non-draft, labelled `adw:blocked`, PR body naming the
conflict — the abandoned-integration-branch shape is the most expensive abandonment and
must not have the weakest reporting channel (a terminal line nobody reads). "Unattended"
means *without the owner*, not *without care*: a correct resolution is still a breach, and
the one recorded instance resolved a conflict in repasse-share logic — trap-domain money
code — catching a real auto-merge defect on the way, with no escalation raised (retro
2026-08-01, `d210ca5`). It came out right; the rule exists for the run where it does not.

Otherwise the final PR (`adw/<slug>` → `<INTENT_BASE>`) runs the FULL Phase 3 loop on the
composition — gates, 3.4 verify against `origin/<INTENT_BASE>`, **and 3.6's review** — and
waits `ready` for the one human consent.

**The composition review is not waivable, and "every unit was already reviewed" is not a
reason — it is the reason it is mandatory.** Chain close is the only place code exists that
no unit ever contained: conflict resolutions, and cross-unit type errors that surface only
once both sides share a tree. One final PR merged unreviewed carried a hand-applied
conflict resolution that was invisible to tsc, lint and `audit.sh` alike and rendered a
wrong mobile gutter with nothing going red (design §10 v2.12.1). Composition code is the
least reviewed and most integration-shaped code in the whole run.

**Derive the merge-created set from `git show --cc`, then read the body against it.** The
body explains a resolution; only git delimits it. #853 is the worked example of the trap:
its second item names the *error* (`TS2352`, reported on the `as StageEntry` cast at the
call site) where the merge-created thing is the *fix* (`bodyInset: 'self'`) — and that cast
pre-dates the merge in parent `49b28f61`. Grep the body's nouns and you land on a ` +` line
and conclude nothing was invented. The `++` lines are the record.

**Bound the review to that set, and prove the set is complete.** "The composition" is not
the final PR's whole diff. Only files **both** parents touched ever needed a three-way
merge — for #853 that is 9 of the 48 it changed, and replaying those 9 leaves exactly one
file to read; the other 8 are byte-identical to the clean auto-merge and were already
reviewed in their sub-PRs. Run this in the close worktree to get the surface and the proof:

```bash
MERGE=<merge-sha>
P1=$(git log -1 --format=%P $MERGE | awk '{print $1}')
P2=$(git log -1 --format=%P $MERGE | awk '{print $2}')
BASE=$(git merge-base $P1 $P2)

git show --cc $MERGE     # lines prefixed "++" are in NEITHER parent — the review surface

# Proof the set is complete: replay the three-way merge for every file BOTH parents touched.
# git merge-file needs seekable FILES — not blob SHAs, and not process substitution.
D=$(mktemp -d)
comm -12 <(git diff --name-only $BASE $P1 | sort) <(git diff --name-only $BASE $P2 | sort) |
while read -r F; do
  git cat-file blob $P1:"$F"    > "$D/a"
  git cat-file blob $BASE:"$F"  > "$D/o"
  git cat-file blob $P2:"$F"    > "$D/b"
  git cat-file blob $MERGE:"$F" > "$D/m"
  git merge-file -p "$D/a" "$D/o" "$D/b" > "$D/r" 2>/dev/null
  cmp -s "$D/r" "$D/m" || echo "HAND-EDITED: $F"   # any output → read that file too
done
```

A rule that reads as "re-review 48 already-reviewed files" is the shape a run rationalizes
past — the same failure as §6's re-verify. The bounded read takes minutes and covers the
whole class; the unbounded one is what gets skipped.

So gate the consent request on the mechanism, not on intent — **print `/pr-ready` §5's
count for the final PR on the run-report line; `0` → `blocked`, never `ready`,** with
`default: run /code-review <N> <tier> apply on the composition, then re-run /adw-build <slug>`.

**§5's count, not a fresh one.** §5 filters on `(.createdAt // .submittedAt) > "$CODE_TS"`;
an unfiltered `gh pr view --json comments,reviews | length` is a *different, weaker* number
that any comment of any age satisfies — including one this run posted itself. One number,
one owner. The rationalization this closes is specific and sounds correct: *"§3.6 already
ran `/pr-ready`, which ran §5 and returned ≥1."* It did — **for a unit PR**. The final PR is
a different PR and has its own count.

`repo-profile §9` states what `gh pr view --json reviews` is worth in this repo — where
`/code-review` posts an issue comment rather than a GitHub review object, that field reads `0` on
every pipeline PR and keying on it scores every PR unreviewed.

**A red repo status check is a note, not a gate — but it is never silent.** `gh pr checks <N>` may
be red for reasons that are not the code; `repo-profile §9` names any such standing condition and
how to confirm it (`gh pr checks` returns only the rollup and cannot tell you — `gh run view <id>
--json jobs` can). Then name it on the run report: the standing-condition wording **only when the
run actually shows that shape**, else `note  CI red — verify before merge`. #853 merged over a
`FAILURE` rollup with nothing recorded either way, and "red because of the standing condition" and
"red because broken" are indistinguishable at a glance — which is the problem.

## Phase 5 — run report

Print the **run report exactly** (adw-core §7): one line per PR, ready → blocked → failed → unbuilt;
`Next:` names the merge order. The report is the whole message — nothing else is printed.
