---
description: "Shared ADW contract — spec headers, naming, depth ladder, packaging, surfaces. Read by /adw-init and /adw-build at Phase 0 — not invoked directly."
---

# ADW Core — shared contract

**This file lives in the `adw` repository and is fetched, not copied** (§9). It is repo-agnostic:
every command, path, branch and gate it needs is declared per-repo in the consuming repo's
`.claude/repo-profile.md`, cited throughout as `repo-profile §N` against frozen anchors §1–§18.
Both `/adw-init` and `/adw-build` read that file at their Phase 0 alongside this one — it is not
auto-included.

Rationale and evidence live in `docs/00-design.md` of this repository, cited throughout as
`design §N`. This file is the operational subset both commands parse and print. If the two
disagree, this file wins at runtime and the discrepancy is a bug — fix both in the same PR that
finds it.

## 1. Intent and artifacts

`<specs-dir>` and `<plans-dir>` below are `repo-profile §2`'s values.

- **intent-slug:** kebab-case, derived from the intent (e.g. `overnight-shifts`).
- **Specs:** `<specs-dir>/YYYY-MM-DD-<intent-slug>/NN-<unit-slug>.md`;
  a single-unit intent uses the flat file `<specs-dir>/YYYY-MM-DD-<intent-slug>.md`.
- **Plans** (D3 only — §3; a D2 plan lives inside the spec's `## Implementation`):
  `<plans-dir>/YYYY-MM-DD-<intent-slug>-NN-<unit-slug>.md`.
- **A profile may declare a legacy artifact root** — `<legacy-specs-dir>` /
  `<legacy-plans-dir>` (`repo-profile §2`): the directory that held specs and plans before
  the current one. It is **frozen, not forbidden**, and the difference is the whole rule:
  - **Nothing already in it is ever moved, renamed or rewritten.** At scale the old files are
    cited from other files and from merged PR bodies, so migrating would break every citation.
  - **No NEW intent is ever born there.** A brand-new intent always starts under `<specs-dir>`.
  - **An intent that already lives there keeps writing there for its whole life**, later units
    included, because one intent never straddles two roots. Extending a legacy-rooted intent
    writes its new sibling spec (and, at D3, its plan under `<legacy-plans-dir>`) beside the
    ones already in that root.

  So every read that resolves a spec by path — extend (§1.1), resume (§5), `/adw-build` Phase 0
  step 3 — checks **both roots**, the current one first, and remembers which one answered: that
  answer is where the unit's own artifacts get written. A repo that declares no legacy root has
  one root and drops the second path everywhere.
- Nothing else. No manifest, no run-state file, no new directories. The durable record is
  the specs plus the merged PRs — made true by `/adw-build`: each unit PR commits its
  spec (and its plan file, D3 only) alongside the code, and the main-tree originals are deleted once the
  unit's first commit carries them (adw-build §3.1). Until a unit builds, its documents
  live uncommitted in the main tree; after a completed run, nothing lingers there.

**An intent is append-only and outlives one run.** The date in the folder name is the
intent's BIRTH date, never re-dated; later batches add `NN` files to the SAME folder with
unit ids continuing from the highest ever used (§1.1). One slug therefore has exactly one
spec folder — two dated folders for one slug is a bug, not a choice, and `/adw-build`
refuses the set rather than picking the newest.

### 1.1 Extending a live intent

Testing a built unit surfaces the next issues; they belong to the intent that produced
them. An intent is **live** while any of: an adw PR for the slug is open · its spec folder
still holds UNTRACKED unit specs · a **non-default** `base:` (§2) is still unmerged. Bare
folder existence is NOT liveness — §1's deletion removes only the uncommitted originals,
and the merged copies come back tracked at the next `git pull`, so "the folder exists"
never expires; likewise the default base (`repo-profile §3`) is never merged into anything, so a
default base would make every intent live forever. While live, `/adw-init` extends it instead of minting a
new slug (adw-init Phase 0.5).

- **Prior state is recoverable without a state file**: unit ids and packaging from the PR
  titles (`[adw <slug> u2+u3]` — §5 resume's per-slug enumeration, never a capped
  `--search` listing: best-match truncation lowers `max` and a reused id breaks resume),
  merged units' specs from git on the base branch (`git show origin/<base>:<spec path>`),
  OPEN-PR units' specs from their own branch
  (`git show origin/adw/<slug>-uNN:<spec path>` — §1 already deleted the main-tree copy
  and they have not reached `<base>`), unbuilt units' specs from the main tree.
- **New units continue the numbering** — `max(every unit id ever used for this slug) + 1`,
  merged units included. Ids are never reused, so a merged `u2` and a new `u6` cannot
  collide in a PR title.
- **A new issue inside an UNBUILT unit's scope amends that unit's spec** rather than
  minting a neighbour — one fewer PR, and the unit has not shipped yet. A new issue
  inside a MERGED or open-PR unit's scope becomes its own unit citing the original.
  An amend rewrites a spec the owner ALREADY approved, so it prints as its own approval-surface `cut`
  line marked `[amend — <delta>]` (§7) — never folded in silently.
- **A flat single-unit intent extends without moving its spec** — new units go in
  `<date>-<slug>/NN-*.md` at the intent's birth date, and the flat `<date>-<slug>.md`
  stays put as that first unit's spec; `/adw-build` parses both into one manifest. Only
  two *folders* for one slug is the bug.
- **Extend is proposed, never automatic** — a different `base:`, or a different subject,
  is a new intent (run-7's per-team-module-toggles feature was correctly split out).
- The pipeline still never merges a PR it did not open this session (§6, adw-build
  session-boundary provenance): extending across sessions builds new units, and the
  earlier open PRs stay the owner's.

Mapa cirúrgico ran as three disconnected intents across three sessions; the second
restarted ids at `u1` against a live `u1–u5` and had to reconstruct a cross-batch
dependency by hand — design v2.9.

## 2. Spec header — the manifest

Every spec opens with this block; the set of headers under one intent slug IS the manifest:

```yaml
unit: u3                          # uNN, unique within the intent
intent: overnight-shifts          # the slug groups the set
depth: D2                         # D0 | D1 | D2 | D3
packaging: chain A / sub-PR 2     # or: independent · grouped independents: independent / PR 1
after: [u1, u2]                   # in-chain ordering; [] when independent
verify: <a command per the rules below and repo-profile §5's allowlist>
base: <a branch that exists on origin>   # OPTIONAL — omitted = repo-profile §3's default base
```

Rules:
- **`verify` is a command, not a sentence** — output must distinguish done from not-done. A
  whole-tree type check is a complete proof for a rename; `grep -rn <deleted-symbol>` expecting 0
  hits proves a deletion. Where a real test can express it, emit the test. The first token must be
  on `repo-profile §5`'s allowlist, and `repo-profile §12`'s single-test traps bind the form.
- `after` names only units of the same intent; the graph must be acyclic.
- **`base:` is the one OPTIONAL field** — the branch the whole intent forks from and its
  PRs target. Omitted = `repo-profile §3`'s default base. Intent-wide: every spec of one intent
  carries the same value or none (`/adw-build` refuses a mixed set), and the branch must exist on
  origin. It substitutes for the default base throughout `/adw-build` (chain open, unit branches,
  PR bases, stale-base anchors, and the audit anchor's fallback — NOT a sub-PR's
  `adw/<slug>` anchor; adw-build Phase 0 step 5) — and never in §6's consent boundary. It has no
  bearing on the contract either way: the contract comes from its own repository (§9), not from any
  branch of this one. Three straight runs needed a non-default base; run-5 abandoned `/adw-build`
  for want of it — design §10 v2.8.
- No spec, no build: `/adw-build` refuses a unit whose header is missing any of the six
  required fields.

## 3. Depth ladder

| Code | Word | Stages | Typical unit |
|---|---|---|---|
| **D0** | `express` | triage drafts the flat spec in its one pass | single-unit intent meeting every D1 criterion; obvious mechanical fix |
| **D1** | `spec` | diagnose → spec | single reproducible bug, mechanical fix |
| **D2** | `plan` | diagnose/brainstorm → spec+critical (spec carries `## Implementation`) | bug with design surface; small feature |
| **D3** | `design` | brainstorm → design+critical → spec+critical → plan+critical | new behaviour, cross-cutting change, anything touching money/authz/migrations |

**A separate plan file is D3 only.** D2's plan is a mandatory `## Implementation` section
inside its own spec — the numbered table of exact files, exact changes and exact commands
that `superpowers:writing-plans` would have produced, written where the ACs it implements
already are. D2 keeps the word `plan` because it still produces one; what it stops
producing is a second document. Nothing is lost in review coverage: D2's critical pass
already read only the spec (§Critical passes), so the D2 plan was the one artifact in the
system no refute agent ever saw. What is saved is the second file's overhead — its own
header, its restatement of the problem, its restatement of the ACs, its restatement of the
context — which is most of its length. 225 plan files averaging ~380 lines were written in
one two-month window and the committed pairs ran ~2.4× spec-to-plan (design §3.6).

**The word is what rendered surfaces print; the code is what the contract and the spec
header carry.** Each word names the deepest artifact that depth produces. Every surface in
§7 prints the word (`u1  plan  <title>`), never the code. `depth: D2` stays the spec-header
value — 204 specs on disk carry it — and the criteria, envelope check and prose below stay
on codes, because those are machine rules, not things a human reads at a gate. The `depth`
verb accepts either form (`depth "u4→spec"` = `depth "u4→D1"`). This is not a new
convention: D0 has rendered as `express` since it went active.

Spec at every depth. Critical passes are FRESH subagents with an adversarial prompt
("refute this"), never self-review. A critical-pass finding only the owner can settle is
carried to the handoff `needs you` line — never buried in the artifact it reviewed.

**D1 criteria — all four, mechanically checkable at triage:** root cause reproduced with
file:line evidence · expected diff ≤4 **production** source files, tests excluded · **the
`verify` has a home** — a co-located test file exists **OR** the verify is a
self-contained mechanical assertion (grep, a type check, a CSS-rule match) that goes red on
revert · the surface touches NONE of the **trap domains `repo-profile §11` declares**. Any
uncertainty → D2. That same list is the build-side envelope check (adw-build §3.1): a D0/D1 diff
that touches one bounces to `blocked` instead of shipping. The check is mechanical on both sides —
`§11` gives any path prefixes matched as prefixes, and semantic domains matched by grep over the diff's
added/changed lines. Its patterns are deliberately coarse proxies: a false hit costs a bounce to D2
(the cheap direction); tune from run evidence, never toward judgment calls.

**A trap domain is a grep over the diff's added/changed lines, never a directory.** The list
itself is `repo-profile §11`. Two rules keep that list honest, and they live here because they
are what the list keeps getting wrong:

- **A directory name is not a risk class.** Two whole-layer directory prefixes sat in this list
  until v2.17 and they are why the ladder collapsed: on a full-stack monorepo almost every real
  unit touches a layer, so 208 of 245 specs landed D2 or D3 and `express` fired three times ever
  (design §3.6). A prefix that matches most units escalates most units. Name the risk the prefix
  was standing in for and grep for that instead — `repo-profile §11` records which prefixes were
  swapped for which greps in this repo. A prefix survives only where the directory IS the risk,
  as generated migrations are.
- **Measure a candidate row against real diffs before adding it, and prefer a gate that
  executes.** Soft delete is a real trap and is deliberately not a row: over the last 25 backend
  commits every candidate pattern fires on 36–44% of them, which is a tax rather than a
  discriminator, and its polarity is inverted — a grep for the soft-delete helper matches when
  the author **used** it, while the trap is **omitting** it, so the row fires loudest on the
  diffs that are already correct. What catches a missing filter is a gate that reads the rows
  back from the real database. Depth buys a spec and a refute agent; neither runs the
  query. Cover a trap with a gate that executes, not with a rung on this ladder.

The verify-home criterion reads OR, and the file bound is ≤4 rather than ≤2 in one directory,
because a full-stack unit is normally shared schema + handler + consumer and the old bound could
not express that (design §3.6; run-7 cut zero D0/D1 units out of six). The criterion exists so the
`verify` has a home, not so a *file type* does; red-on-revert is the property that matters, and the
build-side mutation gate (adw-build §3.4) already measures exactly it. A grep verify does NOT buy
relief from the file bound or the trap-domain list.

**The bound counts production files. Test files do not count against it.** The bound caps blast
radius, and a test file is not blast radius — it is where the verify lives, which the criterion
immediately above already requires, and whether it actually reds is measured separately by §3.4's
mutation gate. Counting it both obliges a test and charges for it, which is how a unit of three
production files with a co-located test each lands at six and can never be D1. That is not
hypothetical: `tour-flow-attribution` u1 was three production files and two tests, and the five
put it out of reach of a depth its risk profile fit. A repo whose test files are not obvious from
their names should say so in `repo-profile §2`.

**D0 (express) — status: ACTIVE · earned by PR #788 + PR #807, both mutation-clean.**
For a single-unit intent meeting every D1 criterion: the triage agent itself drafts the
flat spec in its one pass, the approval surface presents cut + spec together, and `approve` is the whole
contract approval (no fan-out, no critical-pass subagent — the mutation gate carries
the discriminating-verify property; AC completeness has no catcher but the approval glance —
accepted at this tier). The do-side never thins at any depth.

## 4. Packaging

Two shapes: **independent** (unit or grouped units → one PR targeting the intent's base; grouped
units share `packaging: independent / PR N` and one title `[adw <slug> u2+u3] <title>`)
and **chain** (dependent units share integration branch `adw/<intent-slug>`; one final
PR).

Units MUST share a sub-PR (or PR) when any holds:
- they touch the same file or function;
- they share a root cause;
- one's correctness depends on the other landing in the same merge.

Units MAY be independent when each is independently correct, independently mergeable, and
independently revertible — no shared files, no ordering hazard, **no consumption of another
unit's output** (disjoint file lists do NOT prove independence).

Default when it could go either way: **group**. A separate base-targeting PR is earned,
never chosen — each costs the owner +1 review, +1 local preview, +1 merge consent.

## 5. Chain conventions (contract, not style)

- **Integration branch:** `adw/<intent-slug>`, created from fresh `origin/<base>` (§2
  `base:`, default `repo-profile §3`), pushed to origin at chain open (a sub-PR cannot target a
  base that exists only locally).
- **Unit branches:** `adw/<intent-slug>-uNN` — dash, not slash (`adw/<slug>/uNN` is an
  invalid git ref while the integration branch exists).
- **Sub-PR titles:** `[adw <intent-slug> uNN] <unit title>` (grouped units:
  `[adw <intent-slug> u2+u3] <title>`). The unit id must be recoverable from `gh pr list` —
  unit ids are unpadded everywhere (`u2`, never `u02`); resume depends on title↔header
  equality.
- **Labels** (names are contract — they store the §5.1 metrics):

  ```bash
  gh label create adw:blocked --color D93F0B --description "ADW: escalated finding or gate-file diff — needs the owner" || true
  gh label create adw:failed  --color B60205 --description "ADW: fix cycles exhausted or environment fault" || true
  ```

  After the creates, `gh label list --search adw` MUST list both — the `|| true`
  swallows a gh outage that otherwise resurfaces far from the cause as a failed
  `--add-label`.

- **Derived anchor, never stored:** a sub-PR's verify base = `git merge-base
  adw/<intent-slug> <unit-branch>`. (Design §4.1's "records the base SHA" is satisfied by
  derivation — valid because the integration branch is never rebased mid-chain; sync
  happens only at chain close.)
- **Resume:** enumerate every adw PR of the intent — BOTH bases (`adw/<intent-slug>`
  AND the intent's own base: independent units target that base and are invisible to a
  chain-only listing), states merged + open + closed:
  `gh pr list --state <s> --base <b> --json number,title,headRefName` — keep PRs whose
  `headRefName` is `adw/<intent-slug>` or matches `adw/<intent-slug>-u*`, then map the
  title's unit field back to unit ids. The field is `+`-separated (`u2+u3`): EVERY
  listed id maps to that PR's state. No state file.

## 6. Consent carve-out (exact)

The pipeline may merge ONLY: a sub-PR **it opened itself**, for a unit of the **current
intent**, whose base is that intent's **integration branch**, whose loop reached
**`ready`**. Provenance is the authority — a PR that merely targets some `adw/*` branch
does not qualify. Any PR targeting the default base, the production branch (`repo-profile §3`),
or the intent's `base:` branch (§2) requires explicit human consent, always — a `base:` override
does not open a consent side-door. The carve-out never widens.

## 7. Surfaces — the format contract

Four surfaces, named for what they are. The `S<N>` codes are retired — they said nothing
and appeared in three files' cross-references:

| Surface | When | Old code |
|---|---|---|
| **approval** | `/adw-init`, interactive — the human gate | S1 |
| **handoff** | `/adw-init` exit | S2 |
| **run report** | `/adw-build` exit | S3 |
| **PR body** | a `blocked`/`failed` sub-PR | S4 |

Three rules (owner feedback, structural after prose failed twice):
1. Every surface has a **directive slot** — async surfaces open with a `Next:` first line;
   interactive prompts end on the verb menu at the cursor.
2. **The report is the whole message.** No narration before or after. Each fenced template below
   ends with a `← nothing follows this block` annotation for this reason: stated only here,
   the rule loses to whatever instruction sits at the cursor when the surface is printed.
   A run that prints the handoff and then explains itself in three paragraphs has violated
   the contract, however good the paragraphs are.
3. **Decisions read plainly** — one sentence a non-engineer can act on, recommended
   default first. Engineering detail one level down (spec or `<details>` fold).
4. **Depth renders as its §3 word** — `express` / `spec` / `plan` / `design` — on every
   surface and in every `note` line. `D<N>` is the contract's code and the spec header's
   value; it is never printed to a human.

### approval — the human gate (interactive, `/adw-init`)

```
Intent: <one line>
base    <branch> — <one clause why>        ← only when not the default base (§2 base:)
extends <slug> · u1–u6: merged u1 u2 u3 u5 · open u4 (#820) · unbuilt u6   ← extend mode (§1.1)

needs you  2                               ← or: none — answer by number; blank = defaults
  Q1 (u4) — <one plain-language question>? default: <recommended default>
  Q2 — <question>? default: <recommended default>

cut     chain A ── adw/<intent-slug>: u1 → u3 · independent: u4 · u5 · u6
  u1  plan     <unit title>
  u2  spec     <unit title>                [same sub-PR as u1 — <short reason>]
  u3  plan     <unit title>                [after u1+u2]
  u4  spec     <unit title>
  u5  spec     <unit title>                [same PR as u4 — <short reason>]
  u6  spec     <unit title>                [amend — <delta>; extend mode, no new PR]

⚠ spec criteria covered by no unit: <list | none>   ← ALWAYS prints, `none` included
⚠ <one line each: gate-visibility gap (design §2.2 rollout rule), shared-file hazard,
   uncharted territory>                    ← these print only when they exist

approve → cut + build · specs only → stop after specs · detail · re-cut "<instruction>" ·
regroup "u3→sub-PR 1" · depth "u4→spec"

                        ← nothing follows this block: no summary, no narration
```

The surface is **brief by default**: everything above is all that prints. `detail` and
`fyi` do NOT render — the `detail` verb re-renders the whole surface with them appended:

```
detail — challenge anchors
  u1  why-plan: <one line naming which D1 criteria hold/fail> · verify: <command>
  u2  why-spec: <one line> · verify: <command>
  …
fyi
  · <one line each: decisions already taken, with their default applied>
```

Brief is the default because the surface is read by people who did not write the
pipeline, and the pre-v2.8 shape buried both the cut and the asks under rationale
(owner-reported, twice). Hard rules:

- **Hazards are `⚠` lines, never `fyi`.** `fyi` used to carry gate-visibility gaps,
  shared-file hazards and uncharted territory alongside settled decisions; brief mode
  would hide exactly those. The split is mechanical, decided when the line is written,
  not at render: anything a human might act on is `⚠` (always printed), anything already
  decided with its default applied is `fyi` (hidden). `⚠` is the one zone that grew when
  `approve` started building — see the verb semantics below.
- **The cut line prints the depth WORD** (§3), never `D<N>`. `detail` prints `why-<word>:`
  to match.
- **Anything that needs an answer is a numbered `QN`, never an fyi bullet.** A line
  containing "confirm", "your call", or a question mark inside `fyi` is a contract
  violation — run-6 buried its base-branch override there as concern #1 of ten. Q ids
  are run-wide and START at the approval surface: the handoff continues the sequence, and a question answered at
  the gate keeps its id and does not reprint.
- `why-<word>` and `verify` live only in `detail`, ONE line each — still the anchor the
  human is invited to challenge (run-1: an unchallenged D2 cost a 307-line plan for a
  24-line diff; run-7 stretched the one-liner to four lines). Brief-by-default does not
  make the anchor optional: it must be WRITTEN for every unit and held ready, so `detail`
  answers instantly and a re-cut round never re-derives it.
- `fyi` lines are one line each, context only — a decision already taken prints with its
  default applied, not as a pending item.
- **Extend mode: every `amend: uNN` gets its own `cut` line marked `[amend — <delta>]`,
  and the `extends` line names each prior unit's state including `unbuilt`.** An amend
  rewrites an already-approved spec (§1.1); leaving it off the scan zone hides the run's
  only spec mutation from the gate that exists to see it.

The `⚠ spec criteria covered by no unit:` line is mandatory even when `none` — omitting
the hard unit makes every metric look better, and this line is the one silent failure the
human gate catches for free.

**Verb semantics.** `approve` = freeze the cut, run the fan-out, print the handoff, then
continue straight into `/adw-build <slug>` **in the same session, in the same turn**.
`specs only` = everything except that last step; it is the old plain `approve`, kept for
reading the specs before any code exists. Two consequences the surface must own:

- **`approve` consents to code, not just to the cut.** Design §6 used to get that consent
  from the human invoking build; with the round-trip collapsed, nothing stands between
  this verb and an implementation subagent. That is why the menu spells out
  `approve → cut + build`, why every hazard is a `⚠` line the brief surface still prints,
  and why the `⚠` split above is not cosmetic. The merge carve-out (§6) does not move:
  sub-PRs still merge only into the intent's own integration branch, and the PR to
  `base:` still needs explicit human consent.
- **The collapse is gated on a clean exit.** A non-empty `needs you` on the handoff stops
  there exactly as `specs only` would — a pending critical-pass question is the whole
  reason the round-trip existed, and auto-defaulting it sight-unseen would bake the answer
  into the implementation.

D0 (`express`) approval variant: the draft flat spec body renders as a fenced block
between the `⚠` lines and the verb menu — cut + spec are one approval surface, and the
prompt still ends on the verb menu (rule 1). The body renders in brief mode too; it is
the artifact being approved, not detail.

### handoff — end of init (async; a run boundary, not always a stop)

```
Next: nothing — building u1 · u3          ← `approve`, clean exit: build starts this turn
specs      <specs-dir>/YYYY-MM-DD-<intent-slug>/   N units
plans      u1 u3  ·  none: u2 u4 (below design — plan is in the spec)
⏱ run      machine 41m · your gate 3m                ← unconditional (§7.1)
needs you  none

                        ← nothing follows this block: no summary, no narration
```

Stopping variant — `specs only`, or `approve` with a non-empty `needs you`:

```
Next: /adw-build <intent-slug>
specs      <specs-dir>/YYYY-MM-DD-<intent-slug>/   N units
plans      u1 u3  ·  none: u2 u4 (below design — plan is in the spec)
⏱ run      machine 41m · your gate 3m                ← unconditional (§7.1)
needs you  2                     ← ids CONTINUE the approval surface's sequence:
  Q3 (u3) — <one plain-language question>? default: <recommended default>
  Q4 (u3) — <question>? default: <recommended default>

                        ← nothing follows this block: no summary, no narration
```

The first line is the directive slot (rule 1) and it is the run's state in one line: a
`Next:` naming a command means the human acts next; `Next: nothing` means the session
does. Never print `Next: /adw-build <slug>` and then build anyway — that line is what the
human reads to decide whether to walk away.

`needs you  none` when empty. **Items are numbered `Q1..QN` in ONE sequence across the
whole run — the sequence starts at the approval surface and the handoff continues it, never restarting and never
labelling by bare unit id** — the owner answers by number (`1- …`, `Q3: no`), and
repeated unit labels give them nothing to reference (runs 3 and 6 both shipped
`u1 · / u1 · / u2 ·` shapes; both times the answers came back by guessed position).
The same `QN` ids carry into the specs where defaults are recorded.
Unanswered items ship with the recommended default, recorded in the spec. A single-unit
(flat-file) intent prints its spec's flat path on the `specs` line instead of a folder.

### run report — build exit (async, end of `/adw-build`)

```
Next: review + preview + merge PR #NNN (<which>)
ready    #NNN  <desc> — <units> · gates green · review clean · ⏱ <N>m
blocked  #NNN  <unit> — <one sentence>; default: <recommended default> · ⏱ <N>m
failed   none
unbuilt  none
⏱ run    machine 2h38m · your gate 20h04m   ← unconditional (§7.1)
note     contract <short-sha>               ← unconditional, always the first note line
note     review #NNN — <what ran instead of /code-review>   ← only when a PR skipped it
note     window <N>k — compact before resuming             ← only when ≥400k
note     tier <uNN> <word> author=<tier> impl=<tier>       ← only for units built below opus (§8)
note     level <uNN>+<uNN> built concurrently              ← only when a DAG level ran >1 unit
note     <further run-level caveats — one line each, only when present>

                        ← nothing follows this block: no summary, no narration
```

`ready` and the words `review clean` may not be printed on evidence the runner asserts:
adw-build §3.6 (→ `/pr-ready` §5) fetches the PR's comments and reviews and requires one
dated after the last production-code commit (NOT `$VSHA` — a docs-only amendment must not
demand a re-review the void rule exempts). None → the line is `blocked`. One line per PR, ordered
ready → blocked → failed → unbuilt. These four keywords are the
only PR states — a PR whose `ready` was voided by a post-review amendment (adw-build
§3.6) prints on the `blocked` row, never as a fifth state and never as `failed`.
Multiple `ready` PRs → the `Next:` line lists them in merge order. `· ⏱ <N>m` is
unconditional on every PR line — **net of owner wait**, exactly as §7.1 computes it
run-wide (`machine = (T3 − T0) − gate`): the per-PR number must not charge the human's
latency to the unit. It is **reported, never a trigger** — v2.12 replaced the wall-clock
bound with adw-build §3's progress conditions — and it is durable only because adw-build
§3.4 lands it in the PR body; the terminal line does not survive the session. A PR line may carry trailing `· ⚠ <flag>`
annotations (e.g. `· ⚠ no trustworthy gate sees this unit`); the `note` row carries
run-level caveats (non-default `base:`, extend-mode's prior-unit summary, a
`· ⚠ mutation per-file <covered>/<total>` ratio). The first `note` line is
unconditional: `note  contract <short-sha>` — the commit the loaded contract came from:
`git -C <cache> log -1 --format=%h` (§9). One repository, one commit, one sha, and it is the same
value `CONTRACT_SHA` carries in the evidence block. A tree sha, or a `%h` over a directory, is not
this stamp and must not be printed as one.

Before the extraction this line was harder than it needed to be. Each repo held its own copy of the
contract, so the stamp had to name a *file list* rather than a commit, and it had to be read in the
main tree because a unit worktree branched off fresh origin would stamp current while the loaded
text was stale. Two stamps existed — one for the contract the run loaded, one for the contract that
was available — because those two could differ. Keeping the file list in sync between them was its
own defect class: for one version the freshness check gained two files and the stamp did not, so a
`pr-ready.md`-only contract PR printed an unchanged stamp and the anchor reported the wrong
contract for exactly the files whose body had just moved (design §10 v2.11). None of that survives
one source. There is one stamp, and it cannot lag a rename because it names no files.

Four further `note` lines are conditional. The first two exist because both failures are
silent — the run looks identical on the run report whether or not they happened; the last two exist
because both decisions are invisible after the fact, and each is the labelled sample the
next run's analysis needs:

- **`note review #NNN — <what ran instead>`**, once per PR whose review did not go through
  `/code-review` (adw-build §3.6). The review path is a contract with adjudication tiers, a
  calibration loop and §7 safety stops; a hand-rolled fan-out of review subagents produces
  findings but none of that, and it reads as "reviewed" on every other surface. On the
  `team-active-seat-model` run `/code-review` was invoked on 3 of 7 PRs; the other 4 were
  reviewed by 18 orchestrator-authored lenses and nothing said so.
- **`note window <N>k — compact before resuming`** when the orchestrator's context window is
  **at or above 400,000 tokens** at run report. Compaction is not schedulable from inside the loop
  (design §10 v2.13 — and a checkpoint at a unit's verdict is *inverted*, since `ready` is
  exactly when an unmerged self-opened sub-PR exists), so the only correct move is to hand
  the owner the number at a boundary where compacting is safe. Read it from the session's own
  transcript per §7.1's recovery recipe — the last `usage` record's
  `input_tokens + cache_read_input_tokens + cache_creation_input_tokens`.

  **The threshold is absolute, not a percentage of the window, because the cost it controls
  is absolute.** Every call re-reads the whole window, so spend is the integral of window size
  over calls, independent of remaining headroom — a percentage rule fires too late on a 1M
  model and too early on a 200k one (design §10 v2.15). Report `<N>k`, not `<N>%`.
  Auto-compact (~92% of window) remains the backstop, not the target. Never compact
  unprompted mid-chain.
- **`note tier <uNN> <word> author=<tier> impl=<tier>`**, once per unit whose spec/plan
  author or implementer ran below `opus` (§8's depth gate). The tier a unit was built at is
  recoverable only from the dispatch itself, and dispatches do not survive a compaction —
  so without this line a later "did the cheaper tier hurt?" question has no sample to answer
  from, which is exactly how the u4 pilot ended up as an anecdote.
- **`note level <uNN>+<uNN> built concurrently`**, once per DAG level that ran more than one
  unit (Phase 1). Names what actually overlapped, so a gate flake or a merge conflict at
  chain close can be attributed to concurrency instead of re-diagnosed from scratch.

Nothing else is printed.

### PR body — a `blocked`/`failed` sub-PR (async)

First line `Next:` (what to decide or fix) · then the one-sentence reason with recommended
default (`blocked`) or the last red gate output (`failed`) · then, when the PR halts a
chain, the remaining unbuilt units and why the chain stopped · everything else under a
`<details>` fold, never above the decision line.

### 7.1 The `⏱ run` line — machine time vs gate time

`machine` is wall-clock the pipeline spent working; `your gate` is wall-clock it spent
blocked on a human answer. Both surfaces carry the line unconditionally, `0m` included.

Take `date +%s` at these points: **T0** run start (before any dispatch) · a **T1/T2**
pair around every halt that waits on the owner — the approval surface, a re-cut round, a mid-build
question — T1 immediately before the print, T2 on the answer · **T3** at every `⏱ run`
print, which on a chained run means twice: once for the handoff's partial, once for the
run report's total, over one continuing series.
**Tag every pair with the unit whose PR loop it interrupted** (`—` for a run-level halt
like the approval surface, which precedes every loop): without the tag the run total is derivable but the
per-PR `owner-wait` of adw-build §3.4's evidence block is not, and it defaults to a
`0m` nobody measured. Then
`gate = Σ(T2ᵢ − T1ᵢ)` over every pair and `machine = (T3 − T0) − gate`. Deriving machine
by subtraction rather than by summing work intervals is deliberate: a halt nobody
stamped inflates `machine`, which reads as the pipeline's own cost and gets
investigated — the failure direction that self-corrects. `/adw-build` reached through
`approve` continues the same T-series rather than restarting it — one invocation
the owner experiences as one run reports as one run. A build reached by a fresh
`/adw-build` starts its own series with `gate 0m`.

**This stores nothing** — the stamps are `date` output in the session transcript, which
is where every other free metric already lives (design §5.1's prohibition is on a run
database, not on reading your own transcript). Do not write a timing file.

**If a `T1`/`T2` pair is no longer in context at the run report, recover it before summing `gate` —
do not treat it as zero.** Compaction evicts stamps from the *window*; it does not delete
them. The session transcript persists on disk at
`~/.claude/projects/<project-dir-slug>/<session-uuid>.jsonl` (one JSON object per line;
the slug is the cwd with **every** non-alphanumeric → `-`, spaces and dots included, so
derive it — `pwd | tr -c 'A-Za-z0-9\n' '-'` — rather than swapping only `/`, which yields
a path that does not exist on any spaced path, this repo's among them; the current session
is the newest `.jsonl` by mtime that greps for this run's intent slug, since mtime alone
can land on a concurrent session in the same cwd — dispatched subagents' own transcripts
sit under the sibling `<session-uuid>/subagents/`),
and reading your own transcript is explicitly inside the prohibition's carve-out, above.
This matters because `machine` is derived by subtraction: an unrecovered pair does not
show up as a gap, it silently folds the owner's wait into the pipeline's own cost —
inverting the one distinction §7.1 exists to draw. A fresh `/adw-build` invocation is NOT
this case (it starts its own series at `gate 0m`); mid-run compaction is. If the pair
genuinely cannot be reconstructed, say so on a run-report `note` line rather than reporting a
number the transcript cannot back. Recovery is scoped to the stamps: a readable transcript
never re-establishes merge provenance, which §6 keys on the session, not on what is
legible from disk.

It exists because the two numbers were conflated in the only direction that matters:
run-7 read as a 24-hour run and was 2h38m of work behind a 20-hour approval gate. Without
the split, "the pipeline is slow" and "the pipeline is waiting for me" invite the same
wrong fix (design §10 v2.10). **A `machine` number that is genuinely large is the signal
that authorises trimming; `gate` never is.**

### 7.2 What survives the session

The run report surfaces above are **terminal output and nothing else**, and every number on
them dies with the session — ten runs produced zero surviving `⏱` stamps across 35 PR
bodies (design §10 v2.12).

So anything a **later** run or retro must read goes in the **PR body**, per unit
(adw-build §3.4's evidence block): contract sha, cycle counts and what they resumed from,
the phase split, `owner-wait`, the gate exit vector, the mutation coverage ratio, the
artifact ratio. `gh pr view --json body` fetches it forever, it survives a re-review that
posts a fresh comment, and it is where a human merging three days later looks.

This is **not** a narrowing of design §5.1, whose prohibition is on a run *database* — a
file or directory a human has to maintain. A PR body is neither. Do not write a timing file.

## 8. Dispatch tier (every `Agent` call, no exceptions)

**Every dispatch declares `model:`. An omitted `model:` is a defect, not a default.** An
unpinned dispatch inherits the session's tier, and the orchestrator runs Opus — so the
omission is invisible in the prompt, invisible in the result, and multiplies that agent's
cost by ~5.

Classify by **what the agent is asked to produce**, never by who dispatches it or how
important the unit is:

| The agent's job | Tier |
|---|---|
| **Find** — refute, review, audit, scan, check against a doc, run a fixed checklist | `sonnet` |
| **Re-execute and relay** — run gates, report exit codes and output tails, verify | `sonnet` |
| **Look up** — read a file or a history and answer a bounded question | `haiku` |
| **Apply a diagnosed finding** — a *separately dispatched* remediation agent, handed findings that already name the defect and the file | `sonnet` |
| **Author** — write a spec, a plan, or production code | **keyed on the unit's `depth:`** — `opus` at D3, `sonnet` at D0–D2 |
| **Adjudicate** — decide a finding's severity, resolve a conflict, close a chain | `opus` |

Write the tier out even where it equals the session's; **an omitted `model:` is a defect
regardless of which tier it would have inherited.** A *fix cycle* is not a new dispatch —
adw-build §3.1 keeps the same implementer, so it stays at the tier that unit's depth
selected; the remediation row above governs only a remediation agent dispatched on its own.

The split is *produce prose the run depends on* vs *return findings the orchestrator then
adjudicates*. A finder that is wrong is caught by the adjudicator downstream; an author
that is wrong ships. Adversarial quality does not need the top tier — it needs
independence and a hostile prompt, both of which are properties of the dispatch, not the
model.

**Author tier is keyed on depth because §3's ladder already IS the design-risk gradient**
— it is the same judgment, already made, at contract time. D3 is defined as "new behaviour,
cross-cutting change, anything touching money/authz/migrations" and is the only depth that
buys a brainstorm and a design stage; D2 and below are a scoped change against a reproduced
cause. Key on the unit's own `depth:`, never the intent's heaviest unit — a mixed intent
dispatches mixed tiers in one message, and that is correct. **Depth is a claim the pipeline
already checks**: §3's D1 criteria are mechanically checkable and adw-build §3.1's
trap-domain envelope bounces a D0/D1 diff that reaches any domain `repo-profile §11` declares —
so a unit mis-declared shallow to buy a cheaper tier is caught on the build side, at the cost of a
bounce.

**The gate is deliberately more conservative than the evidence** — the one unit ever built
below Opus was D3, the tier this rule keeps on Opus. That is an argument, not a measurement,
and `note tier` (§7) is what turns it into one: the run report names any unit whose author
or implementer ran below Opus, so the next run has a labelled sample instead of an anecdote.

**Pin because an unpinned dispatch is invisible in everything but the bill** — 37 of 83
dispatches on one run were unpinned and were 91% of its subagent cost (design §10 v2.14).
Do NOT claim a
per-unit saving for the pinning rule itself; what tracks per-unit cost is depth, and the
control that kills the tempting story is in design §10 v2.15. Compare tiers price-weighted and
normalized by diff churn, never on raw token counts — that error is what this section
exists to correct (design §10 v2.15; the Sonnet-implementer reading and its correction).

**This section is the only place the tier table lives.** `adw-init.md` and `adw-build.md`
reference it; they must not restate it. `pr-ready.md` §4 keeps its own inline pin because
it is invocable standalone and must not depend on this file being loaded — that one
duplication is deliberate. If the table changes, change §4 with it.

## 9. The contract source

**This file is not in the repo that runs it.** The contract lives in one repository, `adw`, and
every consuming repo carries a loader stub plus its own `repo-profile.md`. The stub fetches the
contract before reading it, so a stale contract is not a state a run can be in.

```
adw repo                     consuming repo
  commands/adw-core.md         .claude/commands/adw-core.md   ← 6-line loader stub
  commands/adw-init.md         .claude/commands/adw-init.md   ← stub
  commands/adw-build.md        .claude/commands/adw-build.md  ← stub
  commands/pr-ready.md         .claude/commands/pr-ready.md   ← stub
  commands/review-core.md      .claude/commands/review-core.md ← stub
  commands/code-review.md      .claude/commands/code-review.md ← stub
  commands/cleanup.md          .claude/commands/cleanup.md    ← stub
  docs/00-design.md            .claude/repo-profile.md        ← the per-repo half, authored here
                               .claude/adw/fetch.sh           ← the fetch, gitignored cache
                               docs/adw/{specs,plans}/        ← this repo's own artifacts
```

`<cache>` below is `.claude/adw/cache` in the consuming repo — where `fetch.sh` puts the contract.

**`CONTRACT_SHA` is `git -C <cache> log -1 --format=%h`.** One repository, one commit, one sha. It
is pinned once at `/adw-init` Phase 0 or `/adw-build` Phase 0 and printed on the run report's
`note contract` line (§7). A run that starts on one contract version finishes on it; the cache is
not re-fetched mid-run.

**There is no freshness check any more.** Until the extraction each repo carried its own copy of
these files and a check compared them against `origin`. That check ran *after* the skill text was
already loaded, said in its own words that it "cannot self-correct", printed a note and ran anyway
— and it shipped inside the very file that might be stale. Runs 6 and 7 executed a superseded
contract with that check in place (design §10 v2.8). Fetching before reading moves the question to
a point where it can still be answered.

**One residual case, and it is reported at the point of loading.** If the network fails and a cache
already exists, `fetch.sh` reuses that cache and **exits 2**, printing `CACHED — NOT VERIFIED`.
The run may proceed, but the loader stub requires it to carry
`⚠ contract from cache, not verified against origin (<sha>)` on the run report, the approval
surface and the PR evidence block — and never to print that sha as if it were verified. This is
narrower than the old check in the way that matters: it fires before a single rule has been read,
and it names an unverified contract rather than a stale one it cannot do anything about. A hard
failure with no cache at all is **exit 1**, and the run stops.

**What is still per-repo.** `repo-profile.md`, authored in the consuming repo and never fetched.
Every file above cites it as `repo-profile §N` with frozen anchors §1–§18. A contract file that
needs a value which could differ between two repos is wrong: the value belongs in the profile. The
failing test is always the same — could this exact sentence be true in a repo with a different
stack? If not, it names a value, and the value moves.

**A contract change is now one PR in one repository** and is live in every consuming repo on their
next run. That is the whole benefit and the whole risk: there is no per-repo staging step, so a
contract PR is a production change everywhere at once. Review it as one.
