# ADW — Agentic Development Workflow

**Status:** v2, 2026-07-20. Re-scoped from v1 after the owner rejected the drift: v1 spent
its longest section arguing PR packaging — a premise its own §0 had already retired — while
the actual ask was an end-to-end pipeline. v2 is built on the think/do split the owner
specified directly.
**Owner:** Humberto Uchiyama Costa
**Supersedes:** the review-only scoping in `docs/superpowers/specs/2026-07-18-adw-system-design.md`,
and this file's own v1 (see §10).

---

## 0. Inherited findings

v1 was produced by five critical reviews (red-team, buildability, observability, adoption,
prior art) of a draft they substantially refuted, then a `/spec-review` pass. Four findings
survive every re-scope and bind v2; the detail lives in §10's revision history.

**The fat-PR diagnosis was an outlier, not a distribution.** Measured across 120 merged PRs
(#635–#762): median 263 lines, 6 files; 61 of 120 under 300 lines; merge cadence 5–10/day;
genuinely fat code PRs needing real review ≈ five. #751 (26 files, 1,287 lines) was the
exception that two prior documents mistook for the norm. Decomposition-into-N-PRs is dead as
a centrepiece; the unit rule survives as *work organisation* (§3.1).

**The expensive human cost is visual verification, not review.** `/code-review` (108
invocations) made review cheap. `npm run preview` + manual visual verification of a medical
PWA scales linearly with PR count, cannot be automated by any gate loop, and appeared zero
times in the documents this one supersedes. Every packaging decision in §3.5 prices it in.

**Adopted = automation of a step the owner cannot skip; dead = automation of an optional
step.** `/code-review` (must review) 108 uses; `/test-env`, `/cleanup` (must have a stack /
must fix worktree sprawl) adopted in days; `/rca` (optional) — zero artifacts in 5.5 months,
`.agent/rca/` holds only `_TEMPLATE.md`. And every dead command demanded a **new artifact
directory the human had to maintain**. The law is recorded as under-determined —
`/plan-feature` is dead while planning plainly is not (`docs/superpowers/plans/` holds nine
files from 2026-07-02 to 2026-07-19) — but both candidate readings prescribe the same
design: small commands, terminal output, no new *run-state* trees. Durable design artifacts
(specs, plans) in the trees that already exist are explicitly not what the law forbids;
they are what §3 produces.

**Unattended implementation is exactly as safe as the gate that clears it.** #751 shipped
because the gate could not see the defect, not because the PR was fat. §2 is unchanged from
v1 and remains possibly the whole deliverable.

---

## 1. Objective — think, then do

One human brings intent. Two commands split the pipeline at the contract boundary:

- **`/adw-init`** — *think.* Intent → approved unit cut → per-unit front-end
  (diagnose/brainstorm → design → spec → plan, each with a critical pass where warranted)
  → durable artifacts in `docs/adw/specs/` and `docs/adw/plans/`. Writes documents, never code.
- **`/adw-build`** — *do.* Consumes the artifacts → implements in worktrees → gates →
  independent verification → PRs → `/code-review` loop → `ready | blocked | failed`.

**Human touches:** intake, unit-cut approval (§3.2 — `approve` buys the cut *and* the
build), optionally reading the produced specs/plans, then per
terminal PR: review, **`npm run preview` + visual verification**, merge consent. Plus deploy
and exploratory testing. §6 is the authoritative list and this line must not drift from it.

**Non-objectives:**
- **Not cheaper.** Token spend and wall-clock go up. Machine resources for human attention.
- **Not faster.** METR's RCT (Jul 2025, 16 devs, 246 tasks) found developers **19% slower**
  with AI while estimating themselves 20% faster. Any speed claim here is unfounded.
- **Not more PRs.** PR count is an output of the packaging rule (§3.5), never a goal.
- Does not remove design authority. The human approves the cut and owns every merge.

---

## 2. Prerequisite: the gates (this is possibly the whole deliverable)

**Unattended implementation is exactly as safe as the gate that clears it.** Attended, a
weak gate is survivable — a human reads the diff. Unattended, the gate is the only thing
between a bad plan and a clean-looking PR.

#751 shipped because **the gate could not see the defect**, not because the PR was fat.
An invariance test ("a PATCH omitting `endDate` changes no row's `endDate`") catches it
under *any* topology, decomposed or not. The adoption review's verdict on this section:
*"This is the highest-value item in the draft and it is filed as a prerequisite to
something else. It may be the whole deliverable."* That is accepted here.

### 2.1 Current gate state

| Gate | State | Consequence for an unattended loop |
|---|---|---|
| `cd api && npm test` | **mocks the DB completely** | a persistence bug exits green — #751 exactly |
| `npm run test:integration` | real Postgres; per-worktree database since PR #956 | trustworthy, but covers only what has been moved onto it |
| **frontend `npm test`** | in CLAUDE.md §5's required list | #746 T6 broke mock factories that failed **only** here, not under tsc |
| root `npm test` script | `cross-env TZ=… vitest` — **no `run`** | enters watch mode; unattended this hangs silently and burns the whole budget |
| e2e (Playwright) | **broken en masse** by #731's redirects (measured 2026-07-19) | no UI gate exists at all |
| `audit.sh` | exits **1** on `NOTHING AUDITED` unless `--allow-empty` | fixed; the exit code no longer disagrees with the banner |
| `audit.sh` scope | `^(src/|api/src/|api/drizzle/migrations/|packages/)` | fixed; `packages/` is scanned, including `shiftSpan.ts` (#751's centre) |
| CI | **live and green**, `pull_request` → main/develop | a real independent gate; `paths-ignore` skips docs-only PRs |

**This table was wrong in five rows on 2026-08-15 and it caused a measurable misfire**: a
triage agent read the CI row, concluded no CI gate existed, and reasoned about where to
wire a migration guard on that basis — while CI had been passing for weeks. A "current
state" table nobody re-measures becomes an active source of wrong conclusions, not merely
a stale one. Re-verify a row before citing it; the tallies that used to sit here were
removed for the same reason (a count is drift no gate checks — it is not load-bearing,
the list is).

### 2.2 Gate work required before any unattended rollout

1. **`audit.sh` must assert `checks_run > 0`** and exit non-zero otherwise. The current
   exit-0 is the same "reports success having examined nothing" class PR #755 existed to
   fix — and #755's own follow-up *"anchored on the wrong grep output shape and therefore
   never ran at all; `--all` had been green by luck."* A gate-integrity defect survived a
   human-attended fix **of gate integrity**, in this repo, weeks ago.
2. **Add the frontend suite** as its own gate, invoked as `CI=1 npm test` so it can never
   enter watch mode. **Not `npx vitest run`** — the root script is
   `cross-env TZ=America/Sao_Paulo vitest` and TZ is set nowhere else (no root
   `vitest.config.ts`, and `vitest.setup.ts` does not set it), so bypassing the script runs
   the suite in the machine's local timezone. In a repo with four documented UTC-3
   date-boundary regressions, an unpinned-TZ gate is a lying gate of the same class item 1
   closes.
3. **Extend `audit.sh` scope** to `packages/` (and decide on `tests/`, currently 52
   unscanned files).
4. **Repair the e2e suite** (36 specs) — otherwise there is no UI gate, and UI is the
   scope most tempting to run unattended first.
5. **Automate the mutation-proof step.** The Phase-2 substrate plan
   (`docs/superpowers/plans/2026-07-19-adw-phase2-substrate.md`, merged to `develop` via
   PR #761 on 2026-07-20)
   already mandates it manually at **nine** named steps (2.2, 2.5, 2.9, 3.3, 3.5, 4.2, 5.2, 6.4, 8.7) plus a blanket "repeat for **every** relocated test in every PR": *"A test that only ever passes proves
   nothing… temporarily neutralise the derivation… Expected: FAIL… Revert."* Automated
   diff-scoped: neutralise the unit's changed production lines, re-run only the test files
   the unit touched, require RED, revert. This is the only mechanism that detects a gate
   that cannot see the code it claims to cover.
6. **Move persistence assertions to the real-DB harness** — the substance of the #761
   plan, merged 2026-07-20; items 5–6 have an owning plan on `develop`.
7. **Set `VITE_SENTRY_RELEASE` on the manual deploy path.** `deploy-hosting.yml` sets it
   from `github.sha`, and both consumers — the runtime init (`src/lib/sentry.ts:125`) and
   the sourcemap-upload Vite plugin (`vite.config.ts:61`) — read it; but with Actions dead, prod ships
   via manual `firebase deploy`, which does not. Every hand-deployed bundle reports
   `release: undefined`, severing the only mechanical Sentry-issue → PR attribution chain.

Items 1–3 are hours. Item 4 is PR 1 of the #761 plan. Items 5–6 are the substance of it.

**Rollout is scoped by gate coverage, not by confidence.** A unit runs unattended only
where a *trustworthy* gate can see its correctness. Until e2e is repaired there is no UI
gate, so "start with UI" — the original draft's own recommendation — was the scope with
zero coverage.

---

## 3. `/adw-init` — from intent to contract

### 3.1 The unit rule

The owner already sends related bug lists and they get organised into logical units in
conversation; this works and predates any tooling. The unit is a *work-organisation*
boundary, and the rule for cutting it:

**Cut vertically by behaviour; a layer cut is allowed only when one layer contains the
entire behaviour.**

Rejected: frontend/backend splits of a single behaviour. Neither half is independently
verifiable, and CLAUDE.md already documents the trap — *"Cross-boundary request/response
shape verified only by per-side mock tests… Two green mock tests can codify different
shapes → every real call 400s while CI stays green. Regressed PR #619."* Splitting FE/BE
removes the only place a reviewer sees both sides at once.

Legitimate layer cut: when one layer *is* the whole behaviour — a migration, a backfill,
an endpoint with no consumer yet, a pure authz fix.

**The rule is symmetric.** Split when one intent spans more than one review context; merge
when several changes share one. Five Settings copy fixes are one unit. Reviewability is the
metric, never size — optimising for *small* is trivially gamed (dead-code-then-wire,
migration/consumer split, refactor-shedding).

**Where the rule works and where it does not.** It works when work originates as user
reports (#746: seven independent reports that decompose naturally). It degrades when work
originates as a **survey** (#742), a **triage queue** (#745), or a **sweep** (#731, #756)
— and in this repo those are the majority. For sweep-shaped work, expect one unit — a
split of one is a legitimate outcome, which is why the command is `init`, not `split`.

### 3.2 The cut proposal and the human gate

`/adw-init` first runs **one cheap triage agent** over the intent and prints a proposal:
the unit cut, a **depth** per unit, and a **packaging** per unit (§3.5). Nothing expensive
runs before approval — the per-unit front-end (§3.3) can cost more than the implementation,
and burning it on a mis-cut is the failure this gate exists to prevent.

**Depth ladder** — proposed per unit, overridable at the gate:

| Depth | Stages | Typical unit |
|---|---|---|
| **D1** | diagnose → spec | single reproducible bug, mechanical fix |
| **D2** | diagnose/brainstorm → spec+critical (spec carries `## Implementation`) | bug with design surface; small feature |
| **D3** | brainstorm → design+critical → spec+critical → plan+critical | new behaviour, cross-cutting change, anything touching money/authz/migrations |

**Spec is produced at every depth.** The spec is the contract `/adw-build` consumes and the
durable record of the run — the manifest role, without a manifest file (§3.4). Design and
plan are conditional; critical passes attach to whichever stages the depth includes.

The approval surface, printed to the terminal:

```
Intent: fix overnight shifts

chain A ── integration branch adw/overnight-shifts (§4.1)
  u1  D2  Derivation rule: shift crossing midnight → endDate = date+1
          verify: cd api && npm run test:integration -- -t "overnight span derivation"
  u2  D1  Backfill existing overnight rows        [same sub-PR as u1 — §3.5 ordering hazard]
          verify: cd api && npm run test:integration -- -t "backfill 0049 values"
  u3  D2  Calendar sync reflects the span          [after u1+u2 in-chain]
          verify: cd api && npm run test:integration -- -t "gcal span sync"
  u4  D2  Surfaces render the span                 [after u1+u2 in-chain]
          verify: CI=1 npm test -- EventDetailBody PainelChip

⚠ spec criteria covered by no unit: none
⚠ concerns
  · "fix the calendar too" is underspecified — read as u3, not Trello #167.
  · u1/u4 sit on opposite sides of the FE/BE boundary as separate units — legitimate under
    §3.1's layer-cut clause (u1's derivation is the entire server-side behaviour; u4
    renders the already-persisted field), and the final PR's composition gates + preview
    are the cross-boundary check while e2e stays broken (§2.1).
  · u1 and u3 may both touch the scope=future fan-out: the scope × endDate axes exist on
    exactly two handlers (updatePlantao, updateCalendarEvent), and calendar-events.ts
    carries the FIRST occurrence of the #751 class. If they do, u3 joins u1's sub-PR.

approve · re-cut "<instruction>" · regroup "u3→sub-PR 1" · depth "u4→D1"
```

Read the packaging against §3.5, because the obvious cut is wrong: u3 and u4 look
independent — different surfaces, different files — but both *consume the span u1
produces*. **A unit that reads another unit's output is not independent, no matter how
disjoint its file list looks.** The prior document's version of this exact example made
that mistake twice; §10 keeps the record.

**`⚠ spec criteria covered by no unit` is mandatory.** Omitting the hard unit makes
*every* metric look better — fewer failed exits, fewer escalations, all gates green. It is
the one silent failure the human gate can catch for free, and only if the surface shows it.

### 3.3 The fan-out — per-unit front-end

On approval, `/adw-init` dispatches **parallel subagents, one per unit, in the main tree**.
They write documents only — no code, no worktrees needed, and the main tree is where every
skill exists (§7 · skills). Per unit, by depth:

```
bug:      superpowers:systematic-debugging  →  root cause, evidence
feature:  superpowers:brainstorming         →  explored options, chosen direction
   ↓ (D3)
design + critical pass
   ↓ (always)
spec + critical pass (D2+; at D2 the spec carries `## Implementation` — §3.6)
   ↓ (D3 only)
separate implementation plan file + critical pass
```

**Critical passes are fresh subagents with an adversarial prompt** ("refute this
design/spec/plan"), not self-review. The caveat is stated rather than hidden: the reviewer
is the same model with the same priors (§5.3's correlated blind spot), so a critical pass
buys fresh-context scrutiny, not independence. It is kept because it is cheap and because
this document's own history (§10) shows fresh passes repeatedly catching what the authoring
pass missed. Independence comes only from the non-model gates in §2.

A critical-pass finding only the owner can settle is not buried in the spec it reviewed —
it is carried to the exit surface (§6.1 S2, the `needs you` line) as one plain-language
question with a recommended default.

Diagnosis quality is load-bearing at D1: a D1 unit goes straight from diagnosis to spec, so
`systematic-debugging`'s evidence requirement (reproduce first, no fix without a failing
observation) is the only thing standing between a plausible-sounding guess and an
implemented wrong fix.

### 3.4 Artifacts — the contract layer

- Specs: `docs/adw/specs/YYYY-MM-DD-<intent-slug>/NN-<unit-slug>.md`
  (flat file, no folder, when the intent is a single unit).
- Plans: `docs/adw/plans/YYYY-MM-DD-<intent-slug>-NN-<unit-slug>.md` (D3 only — §3.6).

Both trees already exist and are already maintained — no new artifact directory is created,
which keeps §0's adoption law satisfied: the prohibition is on **run state**, not on design
docs. There is no manifest file. Each spec opens with a header block:

```yaml
unit: u3
intent: overnight-shifts          # the slug groups the set
depth: D2
packaging: chain A / sub-PR 2     # or: independent
after: [u1, u2]                   # in-chain ordering, empty when independent
verify: cd api && npm run test:integration -- -t "gcal span sync"
```

The set of spec headers under one intent slug **is** the manifest: `/adw-build
<intent-slug>` globs the folder and reconstructs the topology. The durable record is the
specs plus the merged PRs, not a state file.

**`verify` is a command, not a sentence.** Checked against 7 real merged PRs, the
prose-sentence form accepted 0 of 7 as authored — #756 and #731 (~24,000 deleted lines)
state in their own bodies that they have *"no reachable behaviour change."* A rule that
cannot represent a quarter of the repo's recent work trains the planner to fabricate. So:
a command whose output distinguishes done from not-done. `tsc → 0 errors` is a complete
proof for a rename; `grep → 0 references to any deleted symbol` for a deletion. Where a
real test can express it, emit the test — then "is this verify real?" reduces to "does it
go red when the unit's code is reverted," which is §2.2(5)'s mutation check and is
mechanical.

**Atomicity override:** a unit may span N files when a smaller cut leaves the tree
non-compiling. The compile check binds, not any size preference.

### 3.5 Packaging — units → PRs

Packaging is proposed at the §3.2 gate and approved with the cut. Two shapes:

- **independent** — the unit (or grouped units) becomes a PR targeting `develop`.
- **chain** — units with cross-unit dependencies share an **integration branch** (§4.1);
  one PR targeting `develop` at the end.

**Units MUST share a sub-PR (or PR) when any of these hold:**
- they touch the same file or function — #742's two "behaviours" both take hunks from
  `handleDeleteEvolution` (`@@ -1375`, `@@ -1389`, `@@ -1407`);
- they share a root cause — #745's items 3/4/5 span `lazyRetry.ts` / `main.tsx` / `sw.js`;
  **split, each is individually incorrect** (the service worker keeps poisoning the cache),
  and #4 imports a function #3 extracts (TS2305);
- **one's correctness depends on another's landing in the same merge** — the derivation
  rule and the backfill of existing rows. Per #757, the backfill *"**arms** the bug on real
  recurring series… Production is safe **only** because `end_date` is empty."* Merging the
  backfill without the derivation is the corruption event.

**Units MAY be independent when each is independently correct, independently mergeable,
and independently revertible** — no shared files, no ordering hazard, no consumption of
another unit's output.

**Separate develop-targeting PRs are earned by independence, never chosen by default.**
Each costs, measurably: +1 review, +1 `npm run preview`, +1 merge consent. The owner's
recorded position (`memory/feedback_consolidate_prs.md`): *"each PR is a separate checkout,
code review, and `npm run preview` run — N PRs = N× review+preview effort."* When a unit
could go either way, group it. A chain already collapses N dependent units into **one**
review+preview+merge, so the pressure that used to force awkward mega-grouping is gone.

Prior art sharpens this: the largest rejection categories for agent PRs are **abandonment
(40.6%)** and **duplicates (25.3%)** — not defects (incorrect implementation 3.4%) — and
**61.4% of AI PRs receive no recorded review activity at all** (MSR '26 / EASE 2026, 562
manually-coded rejections from the 33,596-PR AIDev set). More develop-targeting PRs
multiplies exposure to the two dominant killers.

### 3.6 Depth calibration — why the ladder collapsed, and the v2.17 correction

**Measured on 2026-09-09, over the whole spec corpus and a two-month artifact window.**

Depth distribution across 245 specs on disk:

| Depth | Word | Specs | Share |
|---|---|---|---|
| D3 | `design` | 100 | 41% |
| D2 | `plan` | 108 | 44% |
| D1 | `spec` | 34 | 14% |
| D0 | `express` | **3** | **1%** |

85% of every unit ever cut landed at plan-or-deeper. `express` — active since PR #788,
earned by two mutation-clean runs — fired three times in the ladder's whole life. A ladder
whose bottom two rungs carry 15% of the load is one setting with a rounding error.

**The cause was the trap-domain list, and it was a path glob.** Until v2.17, `api/` and
`packages/` were prefix matches on the D1 negative list. This is a full-stack monorepo:
a shared Zod schema, a Hono handler and a React consumer are the *normal* shape of a small
change, so the two prefixes matched nearly every real unit regardless of its risk. The
worked example that prompted the review (2026-09-09, `admin-user-contact-fields`, PRs
#1207/#1208): adding `phone` and `registry` to one admin detail endpoint — two columns on
a `SELECT`, two fields on a Zod object, two rows in a card — scored D2 purely on directory
name, which at the time bought a ~150-line spec, a ~250-line plan and a refute agent for a
~40-line diff. It was built directly instead, and the direct build's gates found two real
bugs the documents would not have (a missing `55` country code on the `wa.me` link, and
`formatPhoneBR` reading any 11-digit string as Brazilian).

**A directory name is not a risk class.** What the two prefixes were standing in for is now
named directly: v2.17 adds `transactions` and `live sync` grep rows, which are `api/`
failure modes the original grep set genuinely missed.

A third candidate, **soft delete, was proposed and then measured out** — see v2.17a. It is a
real trap, but every candidate pattern fires on 36-44% of recent backend commits, so as a D1
criterion it reinstates `api/` under another name; and its polarity is inverted, since
`notDeleted` matches the diffs that already handled it. The rule that generalises: **a
trap-domain row must be measured against real diffs before it is added, and a row that
escalates a large fraction of ordinary units belongs to a gate that executes, not to this
ladder.** `packages/shared` gets
no row — a schema widening is the best gate-covered surface in the repo (`tsc` fails without
`pack:shared`, the integration test catches a silent strip), and the real trap it was
proxying for, a DB column with *no* schema field, is an absence no path match can detect.
The file bound moves from "≤2 in one feature directory" to "≤4" for the same reason: the
old bound could not express the normal full-stack shape either.

**Artifact volume over 2026-07-01 → 2026-09-09** (`docs/superpowers/`):

| | Files | Lines | Mean |
|---|---|---|---|
| Specs | 268 | 56,217 | 210 |
| Plans | 225 | 86,430 | 384 |

Plans ran ~1.8× the spec corpus by volume and ~2.4× spec-to-plan on committed pairs. Two
observations make the second artifact the right thing to cut at D2 rather than the first:

1. **No refute agent ever read a D2 plan.** The critical passes are D2: spec · D3: design +
   spec + plan. So the D2 plan was the only artifact in the system that no adversarial pass
   ever saw, and the depth-conditional PR-body line had to say so out loud.
2. **Most of a plan's length is restatement** — its own header, the problem again, the ACs
   again, the context again. The part that is not restatement is the numbered table of
   files, changes and commands, which loses nothing by sitting under the ACs it implements.

Hence v2.17: D2 produces one artifact, its spec, carrying a mandatory `## Implementation`
section. D2 keeps the word `plan` because it still produces one; what it stops producing is
a second document. A separate plan *file* is D3 only. The D2 guard rail of 250/500 is the
inherited 200/300 pair collapsed on that reasoning — inherited, not derived, exactly as
200/300 always were.

**What was deliberately NOT thinned.** The do-side. Every gate, the mutation check, the
refute passes and the `/code-review` loop are untouched, because the same worked example
that argued against the documents argued *for* those: the two bugs it caught came from the
mutation check and a review agent, neither of which is a planning artifact. A `machine`
number that is genuinely large authorises trimming (§7.1); an artifact count does not
authorise trimming verification.
---

## 4. `/adw-build` — from contract to PR

`/adw-build <intent-slug>` reads the approved specs/plans and executes. One invocation
covers the whole intent:

- **independent PRs build in parallel**, one worktree each (CLAUDE.md §8: never two agents
  in one working tree);
- **chains build sequentially on their integration branch**, in one worktree per chain.

### 4.1 Chain topology — the integration branch

```
develop ──► adw/<intent-slug>            (integration branch)
              ▲        ▲        ▲
        sub-PR 1  sub-PR 2  sub-PR 3     (unit branches; base = integration branch)
              └────────┴────────┘
                       ▼
        final PR: adw/<intent-slug> → develop     (the ONE human consent)
```

Each sub-PR runs the full per-PR loop (§4.2): implement → gates → verify → open sub-PR →
`/code-review` → **merge into the integration branch**. The next unit branches off the
updated integration branch. The final PR gets its own full pass — gates on the composition,
§4.5 verification, `/code-review` — before it waits for the human.

**Consent carve-out, stated explicitly.** The standing rule (recorded in
`memory/feedback_no_auto_commit_push.md`) is: never merge a PR without explicit human
consent. This design carves out exactly one case, authorised by the owner on 2026-07-20:
**a sub-PR this pipeline opened for a unit of the current intent, whose base is that
intent's integration branch, may be merged by the pipeline once its loop reaches
`ready`.** Provenance is the authority, never the branch-name pattern — a PR that merely
*targets* some `adw/*` branch does not qualify. Any PR targeting `develop` or `main`
requires explicit human consent, always — the carve-out never widens. (Operational note: `gh pr merge --auto`
merges immediately in this repo — checks are not a hard gate — which is the desired
behaviour here since the loop's own gates are the gate.)

Why sub-PRs at all, instead of plain commits on the integration branch: `/code-review` is
PR-keyed end to end (§4.6) and cannot review anything that is not an open PR. Sub-PRs buy
per-unit review with zero consent cost. A chain whose units are too small to earn separate
review collapses to one sub-PR — §3.5's grouping default applies inside chains too.

**No stacking, still.** Unit branches base on the integration branch and merge into it
before the next begins — sequential, never three open branches stacked on each other.
Stacking cost a recorded data-loss incident (`/code-review apply` force-pushing a stale
rebase over parallel commits); sequential merge into the integration branch cannot lose
work. The integration branch is synced with `origin/develop` before the final PR opens
(≤5 commits → rebase, >5 → merge, per CLAUDE.md §8). A conflicting sync is not resolved
unattended — conflict resolution is judgement work of exactly the class §4.3 aborts on;
the chain halts `blocked`, reported per the bookkeeping rules below.

**Chain bookkeeping** — the conventions a builder needs, stated once:

- **Chain open:** `/adw-build` creates `adw/<intent-slug>` from fresh `origin/develop`,
  pushes it to origin (a sub-PR cannot target a base that exists only locally), and
  records the base SHA — the anchor §4.5's sub-PR verification uses.
- **Unit branches:** `adw/<intent-slug>-uNN` — dash, not slash: git refuses
  `refs/heads/adw/<slug>/uNN` while branch `refs/heads/adw/<slug>` exists (file/directory
  ref conflict), so the v2 slash form was unimplementable. Sub-PR titles: `[adw
  <intent-slug> uNN] <unit title>` — the unit id must be recoverable from `gh pr list`.
- **Labels:** `adw:blocked` and `adw:failed`, created once in the repo. §5.1 makes these
  labels the store for two metrics, so their names are contract, not convention.
- **Resume:** `/adw-build <intent-slug>` reconstructs topology from the spec headers,
  enumerates merged PRs with base `adw/<intent-slug>`, and maps titles back to unit ids —
  already-merged units are skipped, the next unmerged unit builds. No state file.
- **Halted chain:** the halting sub-PR's body lists every unit of its chain that remains
  unbuilt and why the chain stopped — the durable carrier §4.7 relies on (terminal output
  is unread by construction, §4.6).

### 4.2 The per-PR loop

Per PR (independent, sub, or final), in its worktree:

```
implement ⟲ gates → verify → open PR → /code-review ⟲ → ready | blocked | failed
     ↑________|                             ↑____|
     max 3 cycles                       max 2 cycles
```

Implementation follows the unit's plan file at D3, the spec's `## Implementation` section
at D2 (§3.6), and the spec alone at D0/D1. Units sharing a sub-PR are implemented **one commit each**, in
dependency order.

**Provisioning precedes the loop.** A fresh worktree without it fails its first gate run
by construction: symlink `node_modules` + `api/node_modules` from the main repo
(CLAUDE.md §8), run `npm run pack:shared` (else TS6305), symlink the gitignored root
`.env` + `api/.env`. §4.3's resolution-error classes are exactly what skipping this step
produces — provisioning makes them the exception the classifier intercepts, not the
common path.

Gate order (cheapest first):

```
npx tsc --noEmit → npm run lint → CI=1 npm test → npm run build
→ cd api && npx tsc --noEmit → npm test → npm run test:integration
→ npx playwright test              (UI-touching units only — see below)
→ bash scripts/audit.sh --diff origin/develop   (asserting checks_run > 0)
```

**`origin/develop`, not `develop`.** `audit.sh --diff` computes `git diff <base>...HEAD`; a
stale local ref silently widens the scope to include already-merged work or narrows it to
nothing. Fetch before the run. §4.8's stale-base precondition uses the same ref. For a
sub-PR the audit base is the integration branch head, not `origin/develop` — otherwise
every sub-PR after the first re-audits its predecessors' diffs.

**e2e is in the list, not merely a prerequisite.** §2.2(4) repairs the 36 broken specs so
that UI units have a gate — but a repaired suite the loop never invokes buys nothing. It
runs only for UI-touching units. Narrow the spec selection to the touched surfaces rather
than dropping the gate, and carry the narrowing as a flag (adw-build §3.2) — a standing
practice, not a concession to a clock. Baseline-red is the one exception (§4.2's own
`⚠ no trustworthy gate` flag).

### 4.3 Environment failures abort; they do not consume cycles

`TS6305` (missing `packages/shared/dist`), `TS2305` (worktree resolving to main's dist),
`TS2307` (new dep through a symlinked `node_modules`), `MODULE_NOT_FOUND` — all documented
in this repo's own history, none fixable by editing source. An implementer holding only the
red output and its own diff **will edit source**. Classify these before feeding back, abort
immediately, and report the environment fault.

**Infra faults belong in the same classifier, and they are the dangerous half.** The last
two gates have preconditions the resolution-error list misses: `test:integration` needs
`api/.env.test` **and** a running Postgres, and e2e needs a served build. A stopped container
or a missing env file produces output that reads as a *test failure*, not an environment
fault — the exact class this section exists to intercept, wearing the exact disguise that
defeats it. Add: connection-refused, env-file-missing, migration-boot-failure, and
port/served-build unavailability.

### 4.4 Each fix cycle commits separately

A `failed` PR must be reviewable as `feat` + `fix-attempt-1..3`. Three rounds of unlabelled
speculative fixes in one blob is strictly more expensive to review than the fat PR this
system exists to improve on.

### 4.5 The verifier is re-execution, not a second opinion

The original draft justified the verifier as *"the implementer has motive to believe it is
done; the verifier has no stake."* **Stake is the wrong variable.** "From Confident Closing
to Silent Failure" (arXiv 2606.09863, Jun 2026): across 5 judge models × 5 prompt
strategies, **no configuration exceeded AUROC 0.65** at detecting false success, because
judges anchor on confident closing language — which false-success trajectories produce by
construction.

Two structural requirements, without which the verifier is theatre:

1. **Fresh checkout.** Apply the unit's diff to base in a clean tree, with **every gate
   definition restored from base**:

   ```
   package.json  api/package.json          ← the gate COMMANDS live here
   scripts/**                              ← audit.sh (mode 755)
   vite.config.ts  api/vitest.config.ts  vitest.setup.ts
   api/vitest.integration.config.ts  api/.env.test   ← the real-Postgres gate — the one §2 trusts
   eslint.config.js
   tsconfig.json  tsconfig.node.json  api/tsconfig.json
   playwright.config.ts
   ```

   **`package.json` is the load-bearing entry and the easiest to miss.** There is no root
   `vitest.config.ts` in this repo — config lives inside `vite.config.ts`, and the frontend
   gate is literally the `test` script (`cross-env TZ=America/Sao_Paulo vitest`). One edit
   to that line — adding `--passWithNoTests`, narrowing an include glob — reshapes every
   frontend gate and the verifier would re-run the reshaped one and return green.

   In a unit worktree all 361 test files across `src/`, `api/src/`, `packages/` and `tests/`
   are writable. Under gate pressure the cheapest path from red to green is frequently
   *editing the test*.
2. **Any diff touching a file in that list is auto-`blocked`.** Never verifier-green. The
   list above is the definition for both this rule and rule 1 — extend them together or the
   hole reopens. The list is derived by enumerating every file each §4.2 gate command
   reads; re-derive it whenever a gate is added, or the newest gate is the unprotected one.

For a sub-PR, "base" is the integration branch head at the time the unit branched — the
gate files must match *that*, which itself was verified against `origin/develop` when the
chain opened. For the final PR: fresh checkout of `origin/develop` head, apply
`git diff origin/develop...adw/<intent-slug>`, gate files restored from `origin/develop`
— the post-sync merge commit makes any other base definition ambiguous.

The verifier's value is that gates are re-executed in a process whose transcript the
implementer never touched. It is not an agent judging whether another agent finished.

### 4.6 Review runs after the PR opens

`/code-review` is PR-keyed end to end — its input is a PR number, Phase 1 runs
`gh pr view`, and its eligibility gate exits on `state != OPEN` or `isDraft`. It **cannot**
run pre-PR, and a `failed` unit opened as a *draft* would be permanently ineligible for
review. Open non-draft with a label instead. Sub-PRs (base = integration branch) are
ordinary open PRs and review normally.

Findings clearing the escalation bar — defined in `.claude/commands/review-core.md` §3
and applied by `/code-review` — are not auto-fixed: *both* gates (under-determined by the
repo · two defensible answers), neither resolution rule disposes of it, *"typically
zero per review; >2 means the bar wasn't applied."*

**Do not elaborate the bar's prose.** Independent measurement (arXiv 2603.00539, Mar 2026,
~1,400 paired correct/buggy instances) finds LLM reviewers reject *correct* code at
73.2%/87.9% (GPT-4o) and 36.0%/62.3% (Claude-4.5-Sonnet) — and **more detailed prompts
increased false rejections.** Over-escalation is the dominant failure and verbosity feeds it.

**The escalation channel must be something the human reads.** `/code-review`'s
`interactive` mode is never inferred from `apply`, so escalations default to a terminal
gate — which, unattended, nobody is reading. Route to the PR body/label. For a sub-PR, an
escalation halts the chain: everything after it depends on its merge.

**§4.5 re-runs after the review loop terminates, not only before the PR opens.**
`/code-review apply` commits and pushes its fixes once its *own* in-worktree verification is
green — which is not the clean checkout with gate files restored from base. Without a second
§4.5 pass, every fix the reviewer applies lands after the only independent verification, and
the auto-`blocked`-on-gate-file rule is never evaluated against it. That would make a
reviewer edit to `package.json` the one path into `ready` — or into an integration-branch
merge — that nothing checks.

### 4.7 Terminal states

| State | Meaning | Result |
|---|---|---|
| **ready** | gates re-verified green in a clean checkout **after the review loop's last push** | independent/final PR: open, awaits human merge. Sub-PR: merged into the integration branch (§4.1 carve-out), chain continues |
| **blocked** | a finding cleared the escalation bar, the diff touches a gate file, the **review**-cycle cap was reached (§4.8 condition 1 — the verdict `/pr-ready` §3 returns), or the 16-boundary cap fired (condition 6 — gate-green but unconverged) | PR open, labelled, body per §6.1 S4. A blocked sub-PR halts its chain |
| **failed** | a §4.8 progress condition fired — **fix**-cycle caps exhausted, repeated error signature, gate regression, diff oscillation, or stall — or an environment fault (including the 4h single-phase clock) | PR open **non-draft**, labelled, body per §6.1 S4 (last red output included). A failed sub-PR halts its chain |

Nothing dies silently in a worktree (30 live today, 2026-07-20). A halted chain reports
its unbuilt units in the halting sub-PR's body (§4.1).

### 4.8 Preconditions and bounds

- **Stale-base check** at unit start: `git merge-base --is-ancestor origin/develop HEAD`
  (for the integration branch at chain open; sub-PRs check against the integration branch).
  Recorded incident: an agent worktree branched ~1017 commits behind `develop` and analysed
  ancient code with no signal. That figure is historical, not current — the worst lag at
  the 2026-07-19 count (27 worktrees) was 123 commits. Also re-check **at PR-open**: at 5–10
  merges/day a long run routinely opens against a base that moved underneath it, and
  `/code-review` already handles that case at its end.
- **Per-PR stop rule: progress, not elapsed time** (v2.12 — the recalibration this bullet
  promised, performed at run 10). Six conditions, evaluated at every phase boundary and all
  enforced in adw-build §3: cycle caps (no cycle past fix 3 / review 2) · repeated error
  signature (normalised) · gate regression (green→red, twice, after §4.3 classification) ·
  diff oscillation · stall (HEAD + gate exit-vector + PR state unchanged across two
  boundaries, **evaluated only after a repeat cycle**) · boundary cap (16 crossings →
  `blocked`). The first pass of a mandatory stage — 3.4 verify, the single 3.6 review,
  Phase 4's composition review — is exempt from all six: it is a completion, not a loop.
  The stall condition's scoping is not a detail: unscoped, it fires on the *clean* run,
  where a green unit's HEAD and gate vector are supposed to sit still. The boundary cap is
  what actually replaces the clock's unconditional backstop — conditions 1–3 never evaluate
  on a unit that reds no gate, and 4–5 never fire on one that commits each pass. One clock survives, sized not to bind: **4 hours inside a single phase with no
  boundary crossed**, an environment fault under §4.3, because a silently hung subagent
  emits no output (invisible to §4.3) and crosses no boundary (invisible to the stall
  condition). Precautionary; no run has produced one.

  **The 45-minute wall-clock bound this replaces was a guess that ten runs falsified.** It
  produced **zero** `adw:failed` and **zero** `adw:blocked` across 34 pipeline PRs — it never
  once reached its own terminal state. Every recorded firing destroyed a *completion*:
  a PR's only review skipped (run 4, #807), a first review blocked at 44 min — *below* the
  threshold (runs 6/7), per-file mutation skipped on a **31-file** diff (#846). Its one real
  overage went unrecorded (run 2, ~49 min). And the one genuine runaway in the dataset —
  **#828, 19 `fix-attempt` commits over ~23 hours** — was structurally invisible to it,
  anchored as it was on an implementer dispatch a hand-run never makes.

  Three structural reasons it could not have worked, independent of the number chosen:
  wall-clock cannot separate a slow serialized gate (`test:integration` is `singleFork`)
  from a confused implementer; gate cost tracks depth (§4.2 runs api-side gates only on
  `api/`/`packages/` diffs, which is D1's trap list), so a flat budget binds hardest on the
  cheapest units; and the highest-value phases are last, so a time bound eats review and
  re-verify first. It also silently substituted for the absent token bound below, which is
  a different quantity — run 1 spent ~640k subagent tokens, and tokens decouple from
  seconds under a serialized gate.

  **A token bound is still deliberately absent:** §5.1 drops token burn because nothing
  produces the number, and a ceiling nothing can measure cannot fire, cannot be shown
  wrong, and is exactly the unfalsifiable bound this bullet exists to avoid. If per-run
  usage accounting ever becomes available, add it here and to §5.1 together. **Do not let a
  clock stand in for it again** — that substitution is what this bullet's first ten runs
  actually tested.
- **The stop metric must outlive the session.** The 45 was unfalsifiable in practice
  because nothing preserved `⏱`: zero stamps survive across 35 PR bodies. Progress
  conditions are enforceable mid-run (the orchestrator counts them) *and* auditable
  post-hoc, because adw-build's `fix-attempt-N` (§3.2) / `fix(review):` (§3.6) commit prefixes are
  durable and §3.4's evidence block lands the rest in the PR body (adw-core §7.2). Two
  seams this exposed and closed: cycle counts must be **recovered on resume** from those
  prefixes — #829 shipped `fix-attempt-4` against a cap of 3 because a 3-day resume reset
  the counter — and `owner-wait` must be **subtracted per PR**, as §7.1 already does
  run-wide, or a human's slow answer spends a unit's fix budget.
- **Never `git stash`** — the stash list is repo-global and shared across worktrees.
- `/cleanup` already refuses to reap dirty worktrees or ones with open PRs; no change
  needed. Merged integration branches are ordinary `/cleanup` fodder.

### 4.9 Runtime constraints

- The `Workflow` tool is available to the **main session only**, not to subagents.
  `/adw-build` cannot be delegated wholesale to a subagent; the orchestration loop runs in
  the main session and dispatches implementers/verifiers as subagents.
- **Skills in worktrees** — three classes, two survive:
  | Class | In a worktree |
  |---|---|
  | Plugin skills (`superpowers:*`, `code-review:code-review`) | **present** — user-level, not repo files |
  | Tracked commands (`.claude/commands/*.md`) | present |
  | Tracked repo skills (real dirs: `port-landing-pr`, `port-prototype-pr`) | present |
  | Repo-local skill symlinks (`.claude/skills/*` → `.agents/`, whose files are untracked) | **absent** |
  §7 makes vendoring the needed symlinked skills a Stream-B prerequisite. Until then the
  build loop may depend only on plugin skills, tracked commands, tracked skill dirs, and
  the spec/plan artifacts themselves.
- Retry caps enforced by prose drift. This repo has direct evidence — `/code-review`'s
  output format failed twice before a structural fix. Count cycles in the orchestrator and
  continue the *same* implementer via `SendMessage`, which keeps context intact while making
  the count deterministic.

---

## 5. Observability

### 5.1 Metrics, and where each actually comes from

| Metric | Source | Status |
|---|---|---|
| Worktree count | `git worktree list` | free |
| PR size / count | `gh` | free |
| Escalation rate | **the `blocked` PR label** | free once the label is the store |
| Failed-exit rate | **the `failed` PR label** | free once the label is the store |
| Gate red/green | exit codes | free **after** the `audit.sh` exit-0 fix (§2.2) |
| ~~Apply/escalate ratio~~ | — | **dropped.** `.agent/review-calibration.md` logs *overrides only* — it has no denominator, making the ratio as unmeasurable as token burn. And `review-core.md:171` records this channel silently failing in this repo (a path-with-space parse bug left two lines recorded and unread), so it is also an unreliable store. Bar erosion is detected by the canary in §5.3 instead |
| Escape rate | Sentry release → SHA → PR, plus `Regressed PR #N` grep | free after §2.2(7) |
| **Run time split** — machine vs human gate | `date +%s` at four stamp points, read back from the session transcript (adw-core §7.1); surfaced on the `⏱ run` line of S2 and S3 | free |
| **Artifact ratio** — plan lines vs code-diff lines | `git diff --shortstat` excluding both artifact roots at PR open vs `wc -l` of spec+plan (adw-build §3.5); surfaced as `⚠ artifact-heavy` on the PR's S3 line | free |
| ~~Token burn~~ | — | **dropped.** No source exists; the draft asserted a metric nothing produces |
| **Progress-condition state** — cycle counts (and what they resumed from), gate exit-code vector, boundary count | orchestrator-held during the run; recovered on resume from the `fix-attempt-N` / `fix(review):` commit prefixes (adw-build Phase 0 step 7) | free |
| **Per-PR evidence block** — contract sha, cycles, phase split, `owner-wait`, gate vector, mutation coverage ratio, artifact ratio | written into the **PR body** at adw-build §3.4, fetched forever by `gh pr view --json body` (adw-core §7.2) | free |
| **The reader over all of the above** | `scripts/adw-metrics.sh` — scans every `[adw …]` PR body, emits the per-run table plus aggregates, and closes with an explicit `NOT MEASURED` block | free |

Nothing else is stored. No run database, and no per-run artifacts — the prohibition is on
run state, not on design docs; the specs and plans §3.4 produces are the latter. The two
rows added in v2.10 keep that property: both are computed inside the run from `date` and
`git` output already in the transcript, and neither writes a file. A timing or ratio
*file* would be a run database by another name and is out of bounds.

The two rows added in **v2.12** keep it as well, by a narrower argument: they are held in
the orchestrator during the run and, where they must outlive it, written into a **PR body**
— no file, no directory, nothing for a human to maintain, which is the adoption law behind
the prohibition (§0). That distinction is load-bearing rather than convenient: the
45-minute bound survived ten runs unfalsified *precisely because* its metric was
terminal-only, and a stop rule nothing preserves cannot be shown wrong. Adding a metric
here without a durable home would repeat that.

`scripts/adw-metrics.sh` is the **reader**, and it is inside the prohibition rather than an
exception to it: it stores nothing, writes nothing, and computes on demand from `gh`. The
PR body remains the only durable home. Delete the script and no measurement is lost — only
the convenience of not re-deriving it by hand, which is precisely where it earns its place:
hand-scanning these fields produced three separate mis-readings before the script existed,
and two of them were **definition** errors rather than arithmetic, so a more careful human
would have made them too. Both are now encoded in the script's header:

- `review N/2` counts review cycles that **applied findings**. `0/2` is a review that ran
  and came back clean, *not* a review that was skipped — the opposite reading inverts the
  headline conclusion, since it turns the system's healthiest runs into its worst. The
  script's `rv` / `rv+` columns are the independent check, fetched the way `/pr-ready` §5
  fetches it rather than inferred from the counter.
- `progress-conditions` is **hyphenated**. A grep for the spaced form matches nothing and
  reports an empty result set, which reads identically to "no conditions fired".

The general shape is worth stating once, because it outlives these two instances: a field
whose absence and whose zero look the same is a field that will be misread. Wherever the
aggregate cannot tell them apart, the script reports `no data`, never `0`.

### 5.2 What the system detects vs what needs a human

| Failure | Caught by |
|---|---|
| Worktree sprawl, PR size, gate red/green, escalations, failed exits | System |
| Stale base | System (free precondition) |
| **Lying gate** | System — via automated mutation-proof (§2.2(5)). *Not* via the verifier, which re-runs the same blind gates |
| **Escape rate** | System, once release attribution is restored |
| **Fabricated `verify`** — test-backed forms | System, once the mutation check runs |
| **Fabricated `verify`** — `tsc`/`grep` forms | **Human.** The mutation check is diff-scoped and re-runs *the test files the unit touched*; a rename or deletion touches none, so there is nothing to re-run. These are exactly the forms §3.4 added to represent #731/#756 — the coverage extension and its verification mechanism are disjoint at the cases that motivated the extension |
| Composition bugs across units in one sub-PR | System — gates run on the composition |
| Composition bugs across sub-PRs in a chain | System — the final PR runs the full loop on the whole chain (§4.1) |
| Hard unit silently omitted | **Human**, at the §3.2 gate, and only because the surface prints uncovered spec criteria |
| Mis-cut units, wrong depth | **Human**, at the §3.2 gate — the reason the gate precedes the fan-out |
| **Correlated blind spot** | **Nobody. Irreducible.** |

### 5.3 The two that stay human

**Correlated blind spot.** The same model writes diagnosis, design, spec, plan, code,
review, verification and `verify`. A wrong premise propagates through every stage and every
stage agrees — the §3.3 critical passes included, since the critic shares the priors. Only
**non-model gates** constrain it: real Postgres round-trips, mutation checks, tsc, e2e
against a running stack. This is the strongest argument for §2 being the deliverable and
for weighting trust toward deterministic checks over agent opinion.

**Bar erosion, downward.** Over-escalation is loud; erosion is silent.
`.agent/review-calibration.md` currently holds **3 lines, all `apply`** (PR#739, #742,
#754) — a one-directional ratchet toward auto-fixing, each entry individually justified.
Complete erosion presents as escalation rate 0, which reads as *success*.

**The detector is a seeded canary, not a ratio.** A ratio needs a denominator the override
log does not record (§5.1). So: keep one known-ambiguous case that genuinely clears the
escalation bar, run it through the reviewer periodically, and require it to be flagged. If
the canary stops being escalated, the bar is dead — regardless of what any count says. This
is the same technique as §2.2(5)'s mutation-proof, applied to judgment instead of tests:
assert that the thing which should go red still goes red.

---

## 6. What stays manual

Intake, the §3.2 cut approval — where `approve` buys the cut *and* the build, so it is the
only gate at which code consent is collected — reading the produced specs/plans (optional),
then per PR targeting `develop`/`main`:
review, `npm run preview` + visual verification, merge consent. Plus deploy and the
`develop → release → main` ritual, exploratory testing.

**Removed from the human (now pipeline work):** diagnosis, design/spec/plan authoring and
their critical passes, implementation, gate running, the fix cycle, review invocation,
sub-PR merges inside a chain.

**Honest accounting.** Expect intake + cut approval + (per develop-targeting PR: review,
preview, merge) + resolving `blocked`/`failed` exits. A single-PR intent is ~5 touchpoints
against ~4 today — with diagnosis, authoring, implementation and the fix cycle removed in
exchange. A chain is the big win: N dependent units cost one review+preview+merge instead
of N.

### 6.1 Interaction surfaces — the format contract

Every human touchpoint above arrives through one of four surfaces. Their shape is a
contract, not a style preference — the owner's recorded feedback
(`memory/feedback_review_output_structure.md`) is that report-shape rules enforced by
prose failed twice and held only once made structural. Three rules:

1. **Every surface has a directive slot** — the single action to take now. Asynchronous
   surfaces (run reports, PR bodies) open with a `Next:` first line; interactive prompts
   (the approval surface) end on the verb menu instead, which is the same slot at the
   cursor.
2. **The report is the whole message.** No narration before or after it.
3. **Decisions read plainly.** Anything asked of the owner is one sentence a non-engineer
   can act on, recommended default stated first. Engineering detail lives one level down
   (the spec, a `<details>` fold), never in the decision line.

**S1 — approval surface** (`/adw-init`, interactive): §3.2's format. The closing verb menu
is the directive slot: `approve · re-cut "…" · regroup "…" · depth "…"`.

**S2 — init exit** (asynchronous):

```
Next: /adw-build overnight-shifts
specs      docs/adw/specs/2026-07-20-overnight-shifts/   4 units
plans      u1 u3  ·  none: u2 u4 (below design — plan is in the spec)
needs you  1 — u3: keep Trello #167 out of scope? default: yes, separate intent
```

`needs you` aggregates every critical-pass finding only the owner can settle (§3.3) —
asked here, once, in plain language. `needs you 0` prints as `needs you  none`. Answers
can be given in-session or ignored; an unanswered item ships with its recommended
default, recorded in the spec.

**S3 — build run report** (asynchronous, end of `/adw-build`):

```
Next: review + preview + merge PR #812 (chain A final)
ready    #812  chain A final — u1 u2 u3 · gates green · review clean
blocked  #809  u4 — reviewer diff touches vite.config.ts; default: reject the edit, re-run
failed   none
unbuilt  none
```

One line per PR, ordered ready → blocked → failed → unbuilt. Multiple `ready` PRs → the
`Next:` line lists them in merge order. Nothing else is printed.

**S4 — `blocked`/`failed` PR body** (asynchronous): first line `Next:` (what to decide or
fix), then the one-sentence reason with recommended default (`blocked`) or the last red
gate output (`failed`), then — when the PR halts a chain — the remaining unbuilt units
(§4.1 bookkeeping). Everything else goes under a `<details>` fold, never above the
decision line.

---

## 7. Sequencing

**Two streams, in parallel.**

**Stream A — gates (§2).** Items 1–3 are hours; item 4 is PR 1 of the #761 plan (merged
2026-07-20); items 5–6 are its substance. Restore CI billing (Phase 0) — a payment action
that fixes deploy, the only independent gate, and visual regression together.

**Stream B — the pipeline.** `/adw-init` + `/adw-build`, shipped together — a proposal
with nothing to execute it is half a tool. Prerequisite, from §4.9:

- **Vendor the repo-local skills the flow invokes** as real tracked files under
  `.claude/skills/` (tracking the symlinks is useless — their targets in `.agents/` are
  untracked; a worktree checkout gets neither). Enumerate the exact set when authoring the
  two commands.
- **Plugin skills are referenced, never forked** — `superpowers:systematic-debugging`,
  `superpowers:brainstorming`, `superpowers:using-superpowers`, `code-review:code-review`
  are user-level, survive worktrees, and are upstream-maintained. Forking them into the
  repo creates exactly the orphan-artifact class §0's adoption law warns about. If
  reproducibility ever demands pinning, record versions in `skills-lock.json` rather than
  copying content.

The streams are independent: A touches `api/src/**/__tests__/`, `tests/e2e/` and
`scripts/audit.sh`; B touches `.claude/commands/` and `.claude/skills/`. **Building B has
no dependency on A.**

**What A constrains is B's *targeting*, not its construction.** A unit runs unattended only
where a trustworthy gate can see its correctness (§2.2). While `cd api && npm test` still
mocks the DB and e2e is broken, the pipeline's first targets are work the *current* gates
can see; the safe scope widens as stream A lands. That is a per-run decision, not a
milestone.

**Not in v2:** automated Sentry/Trello intake (both blocked on a scheduler that does not
exist), auto-merge of anything targeting `develop`/`main`, forking plugin skills. On the
skills evidence: 21 symlinks in `.claude/skills/` point into `.agents/skills/`,
`git ls-files .agents` returns **0**, and all share one mtime (`Jul 12 14:05`) — evidence
of one copy operation, and deliberately *not* evidence that they have never run (reading a
file does not update mtime; v1's stronger claim was withdrawn, see §10).

---

## 8. Kill criteria

Stop rather than tune if:

- **The pipeline stops being reached for.** Deliberately a judgement, not a threshold: if
  intents start going around it instead of through it, that is the signal, and it does not
  need a number to be obvious. Calibration for patience in the other direction —
  `/code-review`, the one unambiguously adopted command here, needed **16 commits over six
  months** to stabilise *while in daily use*. Early roughness is not rejection.
- **Open `blocked` + `failed` PRs (sub-PRs included) exceed 5 at once, or any single one
  sits over a week.** §3.5 cites abandonment (40.6%) as the top rejection category for
  agent PRs, and a `failed` PR is a pre-abandoned PR by construction. The statistic argues
  against fan-out; it applies with equal force to this design's own terminal states. A
  halted chain's integration branch counts — an abandoned integration branch is the most
  expensive abandonment shape here.
- Escape rate goes **up** versus manual work. **Note there is no manual baseline yet** — one
  cannot exist before §2.2(7) restores Sentry release attribution, so this criterion is
  inert until then and must not be cited as satisfied in the meantime.
- **The six progress conditions (§4.8) never fire.** They replaced the 45-minute bound on
  the argument that a clock cannot distinguish a stuck run from a slow one — sound, and so
  far untested: read the `progress-conditions` aggregate from `scripts/adw-metrics.sh`,
  and read **only its `fired` bucket** — a body reading `… not consumed` records a
  condition that was evaluated and deliberately did *not* stop the loop, which is a
  non-firing. Pooling the two credits the conditions for work they did not do, and biases
  this criterion toward never triggering. If `fired` stays at zero across enough
  instrumented units that both
  caps have bound at least once, then the **caps** are the terminating mechanism and the
  conditions are not; delete them and shrink the contract every run loads, rather than
  tuning six rules that have never executed. Two guards, because this criterion is easy to
  misuse in both directions. A single firing is **not** vindication: the PR body records
  *that* a condition fired, never *whether it should have*, and that question needs the run
  transcript. And zero firings are only meaningful over **instrumented** runs — PRs
  predating the §3.4 evidence block carry no data, which is not the same as a zero and must
  never be pooled with one.
- The escalation bar's canary (§5.3) fails and one recalibration does not restore it.
- A full intent consistently costs more than doing the work in-session would have —
  including the cases where the §3.3 front-end (specs, plans, critical passes) exceeds the
  cost of the implementation it produced.

---

## 9. Known-thin evidence

Do not let anyone — including a future revision of this document — fill these with
plausible prose:

- **Optimal retry caps.** No published study, and none is coming. What *is* now local and
  readable (`scripts/adw-metrics.sh`) is that the two caps are **not symmetric in effect**:
  the fix cap has never been reached, while the review cap has, and the review cap — not
  any progress condition — is where `blocked` verdicts have actually come from. So `max 3`
  is untested headroom and `max 2` is the live constraint. That is a description of where
  the system binds, **not** evidence that either number is right: a cap that never binds
  cannot be shown too high, and a cap that binds cannot be distinguished from work that
  genuinely needed more cycles without reading the runs it stopped.
- **Vertical vs horizontal review quality.** No empirical work exists. Practitioner
  consensus and GitHub's own scoping guidance both favour vertical, but neither is
  measurement.
- **Per-unit front-end depth.** The D1–D3 ladder (§3.2) is judgement. No study measures
  when a spec/plan/critical-pass pays for itself against direct implementation; §8's last
  criterion is the local measurement.
- **Integration-branch chains for agent pipelines.** No published measurement. The shape is
  standard human practice (feature branches); its interaction with per-sub-PR agent review
  loops is untested anywhere.
- **Escape rates for agent-authored code.** GitClear's duplication/churn figures are a
  vendor proxy, not an escape measurement.
- **Merge outcomes for pipelines with a human split-approval gate.** Nobody has published
  this. GitHub Copilot Workspace shipped exactly this gate and was retired (30 May 2025)
  before anyone measured it.

**Closest published analogue, and it is encouraging:** CAID (Geng & Neubig, CMU,
arXiv 2603.21489, Mar 2026) — dependency-aware task plans, concurrent execution in isolated
**git worktrees**, structured integration with **executable test-based verification**.
Reports +25.6% (PaperBench) and +14.7% (Commit0) over single-agent baselines. Arrived at
independently here. It has no human gate; that is this design's addition, and the part with
no published evidence either way.

---

## 10. Revision history — FROZEN ARCHIVE

> **This section is closed. Do not add entries to it.**
>
> It records every change to the ADW contract from v2.0 to **v2.17d (2026-09-09)**, the point at
> which the contract moved into this repository. Before that it lived inside a product repo, where
> 97 pipeline commits were buried in 3,595 product commits and a hand-written changelog was the
> only way to find them. That is no longer true: **from v2.17d on, the history of a contract change
> is its commit and its PR in this repository.** A hand-maintained changelog on top of a dedicated
> git history is duplication that drifts.
>
> **Every measurement below was taken on one repository** — `AXCMED/Plantoes-app`, a full-stack
> TypeScript monorepo (React + Vite frontend, Hono + PostgreSQL API, one shared npm workspace).
> Numbers like "208 of 245 specs landed D2 or D3" and "the trap greps fire on 44% of backend
> commits" are properties of that codebase and that team, not constants of the method. They are
> recorded so the *reasoning* can be audited, not so the *figures* can be reused. A repo adopting
> ADW should re-measure before inheriting any threshold in here — and `repo-profile §11` is the
> place its own numbers go.


Newest last. **Two version numbers collided until 2026-09-09** — a second `v2.13`
(2026-08-02) and a second `v2.14` (2026-08-15) were written while an earlier pair of the
same names already existed. They are renumbered `v2.12.1` and `v2.12.2`, which is where
their dates put them; each carries a `[renumbered from …]` marker. The original `v2.13`
(context cost) and `v2.14` (inflated token figures) keep their numbers, so every existing
citation of those two still resolves. Entries below are now in version order, which is
also date order.

- **draft (2026-07-19)** — decomposition into N PRs as centrepiece; manifest file; parallel
  fan-out across worktrees; `verifiable` as a user-observable sentence; verifier justified
  by "no stake".

- **v1 (2026-07-19)** — five reviews. The motivating diagnosis retired as an outlier;
  packaging separated from splitting, defaulting to grouping; manifest file and
  `docs/adw/` run-tree deleted in favour of a terminal surface; `verifiable` became a
  command; the verifier re-specified as re-execution from a clean checkout with gate files
  restored from base; review moved after PR-open; environment failures abort instead of
  consuming cycles; token burn dropped as unmeasurable; gates promoted from prerequisite to
  possibly-the-whole-deliverable; fan-out removed.

- **v1.1 (2026-07-19)** — `/spec-review` pass. Five Blocking findings resolved in place,
  twelve Warnings and five Notes applied — among them: `package.json` added to the
  gate-restore list; the 500k-token bound dropped as unfalsifiable; the worked example
  corrected after breaking its own rules **for the second time**; the apply/escalate ratio
  replaced by a seeded canary (no denominator, and `review-core.md:171` records the channel
  silently failing); `npx vitest run` noted as silently dropping the TZ pin; `--diff
  develop` corrected to `origin/develop`; re-verification added after `/code-review`'s
  auto-push; two claims withdrawn as unevidenced ("none of the vendored skills has ever
  run" — mtime proves copying, not use — and the calibration count, 3 not 4). The adoption
  law recorded as under-determined rather than asserted.

- **v1.2 (2026-07-20)** — `/adw-init` (renamed from `/adw-split`: a split is an outcome,
  and plenty of intents are one unit) ships together with `/adw-build`; the two-week
  adoption trial dropped — the question it would have answered (does the split rule produce
  useful cuts?) is already answered by daily practice.

- **v2 (2026-07-20)** — re-scoped to the owner's think/do split after v1's packaging
  emphasis was rejected as drift. `/adw-init` becomes the full contract producer: cheap
  triage → **human-approved cut with per-unit depth (D1–D3)** → parallel per-unit front-end
  (systematic-debugging/brainstorming → design → spec → plan, critical passes by depth) →
  spec+plan artifacts in the existing `docs/superpowers/` trees, spec headers replacing any
  manifest. `/adw-build` becomes the executor for a whole intent in one invocation:
  independent PRs in parallel worktrees; **dependency chains on an `adw/<slug>` integration
  branch** with per-unit sub-PRs the pipeline may merge (owner-authorised carve-out —
  consent stays mandatory for anything targeting `develop`/`main`), one final PR and one
  human consent per chain. Fan-out returns in its safe form (worktree-per-PR over
  independent work; stacking stays banned). Skills resolved two-tier: vendor repo-local,
  reference plugin. §2 gates, the §4 loop internals, §5 observability and §8–§9 carried
  forward intact.

- **v2.1 (2026-07-20)** — spec-review pass on v2 (19 findings: 2 Blocking, 10 Warning,
  7 Note; all applied). Blocking: the §4.5 gate-restore/auto-block list omitted
  `api/vitest.integration.config.ts` + `api/.env.test` — the files defining the one gate
  §2 calls trustworthy (added, plus the derivation rule: enumerate every file each §4.2
  gate command reads); and `/adw-build` was unbuildable for lack of a unit↔PR contract —
  §4.1 now specifies chain-open (create + push from fresh `origin/develop`), unit-branch
  and sub-PR title conventions, the `adw:blocked`/`adw:failed` label names, resume by
  enumerating merged sub-PRs, and the halting sub-PR's body as the halted-chain carrier.
  Warnings: the carve-out re-keyed on pipeline provenance instead of the `adw/*` name
  pattern; sync-conflict now halts the chain rather than being resolved unattended; the
  final PR's verifier base defined (`origin/develop` head + full-branch diff); worktree
  provisioning made an explicit pre-loop step (its absence produced §4.3's fault classes
  on every first run); the escalation bar's home cited (`review-core.md` §3); the §3.2
  example's u1/u4 layer cut annotated against §3.1 (avoiding a third worked-example
  failure); #761 recorded as merged (it merged ~3.5 h before v2 was committed — a stale
  load-bearing claim caught only by re-verification); counts refreshed (18 integration
  files, 30 worktrees, nine plans, six months, arXiv dates matched to their IDs).

- **v2.2 (2026-07-20)** — owner-requested pass on the interaction layer. New §6.1: a
  format contract for the four human surfaces — S1 approval, S2 init exit, S3 build run
  report, S4 `blocked`/`failed` PR bodies. Directive slot on every surface (`Next:` first
  line for asynchronous, verb menu at the cursor for interactive), the report is the whole
  message, decisions in plain language with the default first. Init-time critical-pass
  findings that need the owner surface once, at S2's `needs you` line, never buried in a
  spec; unanswered items ship with their recorded default. Rules imported from the owner's
  recorded feedback on review output structure (structural slots, after prose rules failed
  twice).

- **v2.3 (2026-07-20)** — Stream B implementation erratum: §4.1 unit branches renamed
  `adw/<intent-slug>/uNN` → `adw/<intent-slug>-uNN`; the slash form is an invalid git ref
  while the integration branch exists (verified empirically at implementation time). The
  operational contract both commands parse lives in `.claude/commands/adw-core.md`; this
  document remains the rationale. Operational additions recorded there and adopted here by
  reference: S3 gains a `note` row and per-PR-line `· ⚠ <flag>` annotations (adw-core §7).

- **v2.4 (2026-07-21)** — post-implementation spec-review of PR #774 (4 Blocking + 7
  Warning findings); operational fixes live in the commands, adopted here by reference:
  §4.1's "records the base SHA" is satisfied by **derivation** (`git merge-base` — valid
  because the integration branch is never rebased mid-chain); every chain read keys on
  `origin/adw/<slug>` (sub-PR merges advance origin only — the stale local ref silently
  dropped merged code from subsequent units); **all** adw PRs carry the
  `[adw <slug> …]` title prefix (independent units were invisible to resume, which now
  enumerates both bases, `+`-separated unit fields, and open/closed states); sub-PR
  merges re-assert provenance at merge time (`--match-head-commit "$VSHA"` + base
  recheck — closes the TOCTOU on the consent carve-out); the verifier provisions with
  the FULL Phase-2 recipe (conditional blocks included); spec transport settled: specs
  stay uncommitted in the main tree, implementers receive absolute paths, and each unit
  PR commits its spec+plan — which is what makes §0's durable record true at merge.
  Grouped independents gain header syntax (`independent / PR N`). Baseline-red e2e
  skips the gate with the ⚠ flag instead of failing UI units; the integration-test gate
  serializes across worktrees by default; review-loop exhaustion → `blocked`;
  closed-unmerged adw PRs are owner-decided, never rebuilt; same-intent concurrency is
  refused, never silently deleted; chain close gets an explicit command recipe.

- **v2.5 (2026-07-22)** — run-1 recalibration (intent `time-dial-click-center`,
  PR #780: a 24-line fix that cost 67 min and ~640k subagent tokens). The critical
  review's verdict: the waste was duplication and un-tuned fixed costs, NOT the checking
  phases — the D2 critical pass produced the run's only discriminating assertion (the
  hardcoded-`scrollTop` AC; every other AC was green pre-fix). Changes, all in the
  operational contract and adopted here by reference: §2.2(5)'s mutation check lands as
  a build gate (neutralise the unit's changed production files, added-file-aware → its
  `verify` must go red — the enabler for thinner think-sides); the depth ladder gains
  mechanical D1 criteria (trap domains pinned to path prefixes + grep proxies) + a
  per-unit `why-D<N>` rationale on S1 (run-1's D2-on-a-D1-unit went unchallenged for
  lack of a stated anchor) and a **D0 express tier** (triage drafts the flat spec in
  its one pass; S1 approval is the whole contract; activation is an owner-flipped
  status line in adw-core §3, earned by two runs with a passed — not skipped —
  mutation check); the build re-checks the depth envelope against the actual diff
  (trap-domain touch → bounce to D2, never a shipped trap; size-only breach → ⚠ flag);
  triage pinned to a cheap model; api-side gates skipped when the diff cannot reach
  them; spec/plan snippets bound to the terse-comment rule (run-1's entire 18-min
  review tail was deleting one plan-dictated comment block); `approve & build`
  collapses the S1→S2→build round-trip, gated on `needs you: none`; the PR-body
  contract line is depth-conditional (D0/D1 never claim a critical pass they did not
  run). §1's non-objectives stand — this is cost-shaping, not a speed claim.

- **v2.6 (2026-07-24)** — run-2 recalibration (intent `shift-title-template-autocomplete`,
  PR #788: a net-new D2 feature, 104.5 min intent→ready). Every v2.5 fix verified live
  and working (sonnet triage 10.5→4.2 min with the run's highest-leverage output — a
  false-premise catch pre-spec; mutation check ran and self-extended; fresh verifier;
  main-tree cleanup; title marker; the declared ⚠ eyeball gap was exactly where the
  owner found the run's one real issue). Changes, all in the operational contract and
  adopted here by reference: **`ready` is a property of the verified SHA, never the
  PR** — a post-ready in-session commit voids the state and forces re-verify (+ review
  on production deltas); the run closed "reviewed clean" on a head the review never saw,
  the one false status line of the run. §4.5's verifier gains teeth: pinned to a cheap
  model and required to report a per-gate evidence table (command · exit · tail) — a
  missing row is a red; prose "all green" was the last unfalsifiable assertion in the
  do-side. The §4.2 mutation check iterates per changed production file (blind file →
  `⚠ mutation-blind` flag; run-2's blind file was the CSS — the same surface the owner's
  eyeball then caught). Review tier is computed from the code diff excluding
  `docs/superpowers/**` (a D2 plan alone can cross the full-path bar and spend ~18 of
  the 45 bound-minutes reviewing documents). §4.8's 45-min bound becomes measurable:
  elapsed checked at phase boundaries (kills loops, not completions — run-2 breached at
  ~49 min with no record) and every S3 PR line stamps `⏱ <N>m`, creating the
  recalibration dataset. D0 activation becomes countable: "two separate `/adw-build`
  runs", S3 activation note, progress recorded on the adw-core §3 status line itself —
  run 2 is qualifying run 1 of 2. D2/D3 authoring gains an artifact budget (spec ≤200 /
  plan ≤300 lines, one-line justification to exceed; writing-plans' no-placeholder rule
  re-scoped to decisions, never full-code transcription — run-2's 682+1141-line pair
  for a 342-line diff made authoring the most expensive agent of the run at 118.8k
  tokens, §8's own kill-criterion shape) and the critical pass now attacks
  verify-narrowness and artifact redundancy. Deliberately NOT changed, after
  adversarial review: the `approve & build` needs-you gate (its 2.3-min stop bought
  informed consent on a destructive-behavior default — working as designed) and the
  ad-hoc escape hatch (run-2's post-preview loop fixed 3 items in 24 min carrying the
  do-side disciplines voluntarily; policing it would violate §8's first kill criterion).

- **v2.7 (2026-07-25)** — runs 3+4 recalibration (intents `blog-seo-meta` PR #802 and
  `last-login-tracking` PR #807). The headline finding is not a rule but a delivery
  failure: **run 3 executed entirely on the superseded contract** — it started 46 min
  after v2.6 merged, the main tree had not pulled, and the skill loads from the local
  checkout, so zero v2.6 mechanisms fired (inherit-model verifier, no ⏱ stamps, no
  per-file mutation, no activation note) with nothing signalling it. Both commands now
  run a contract-freshness check at Phase 0/1 (`git diff --quiet origin/develop --
  .claude/commands/adw-*.md`; drift → a first-class S1 concern / S3 note — the loaded
  text cannot self-correct, but the run stops being silently stale). Run 4 ran v2.6
  faithfully and validated it: ⏱ 55m stamped, activation note fired, mutation checks
  bit, and the triage caught the Trello card's proposed fix targeting dead code.
  Its one failure closed a v2.6 wording hole: the 45-min bound was read literally and
  **skipped the PR's only review** on a zero-fix-cycle run — the bound now blocks
  REPEAT cycles only; the first pass of a mandatory stage (verify, the single review)
  always runs, with the overage stamped. Owner-reported surface defect fixed: S2
  `needs you` items were labelled by bare unit id (`u1 · u1 · u2 …`, run-3 shipped
  five) leaving nothing to answer by — items now carry run-wide `Q1..QN` ids. The
  §4.5 tripwire gained the evidence path run 3 improvised: a gate-file hit stays
  auto-`blocked` and can never earn verifier-green, but the S4 body now carries
  labelled clean-checkout gate output (a unit whose S1-approved scope IS gate-file
  work — run-3 added the `functions/` workspace — is undecidable on absence alone).
  **D0 flipped ACTIVE** — the §3 activation gate was met by PR #788 + PR #807 (both
  mutation-clean adw builds), the owner approved the flip in run 4 and directed it
  applied here; the honest caveat recorded there stands (the evidence shows the
  mutation gate works alongside the critique apparatus, not that it substitutes for
  it — the build-side envelope check and the S1 read are the remaining catchers).

- **v2.8 (2026-07-27)** — runs 5–7 (`b3a` PR #814 via pivot; `mapa-cirurgico-manager-bugs`
  PRs #817/#818/#819; `…-round2` and `b2c-landing-bugfixes` in flight). The headline is
  v2.7's own centrepiece failing: **the contract-freshness check has a bootstrap hole** —
  it ships inside the files it checks, so a checkout stale from before v2.7 never runs
  it. The main tree sat 5 commits behind for two days and runs 6 and 7 executed the
  entire pre-#810 contract: unnumbered `needs you` items reshipped (`u4 · / u4 ·` — the
  owner again answered by invented ids), and the 45-min bound again blocked a
  zero-fix-cycle run's first review at 44 min, costing the same "go ahead" round-trip
  v2.7 was written to remove. Mitigations, since the check cannot be made retroactive:
  S3's `note` row now stamps `contract <short-sha>` unconditionally (post-hoc detection
  becomes one glance instead of transcript archaeology), and the operational rule is
  recorded owner-side — merging any PR that touches `.claude/commands/adw-*.md` is
  immediately followed by a main-tree pull. Second finding, three runs deep: **the
  develop hardcode**. Run 5 had to abandon `/adw-build` entirely (Track B code exists
  only on `release/mapa-cirurgico`; the S1-side also could not ingest the umbrella's
  plan-card format), run 6 overrode the base by a hand-approved S1 concern threaded
  through every phase, run 7 forks off another intent's still-open chain branch.
  `base:` is now a first-class optional header (core §2): intent-wide, must exist on
  origin, substituted for `origin/develop` across the build, and explicitly NOT a
  consent side-door (§6 extended — base-targeting PRs still need the human). Widening
  spec ingestion to umbrella plan cards was considered and rejected: umbrella tracks
  ship fine via `port-prototype-pr` (B1/B2/B3a/B3b all did), and `base:` removes the
  sharpest blocker. Third, owner-reported: **S1 is unscannable** — run-6's S1 carried
  ten multi-line concern bullets with a genuine needs-input item buried as bullet #1;
  run-7's stretched one-line `why-D` rationales to four lines; five ~15-line critic
  relays landed between S1 and S2. S1 is now two-tier (scan zone: base + numbered
  `needs you` first, one-line-per-unit cut; `detail`/`fyi` below the fold), Q ids
  start at S1 and S2 continues the sequence, "confirm"/"your call" inside `fyi` is a
  contract violation, and init Phase 3 got a relay budget (one line per unit event).
  What run 6 validated (it ran v2.6 faithfully): the S2 needs-you gate held
  `approve & build` through two real product questions; the critical passes killed a
  `verify` that ran zero tests and exited 0 (npm swallowing `-t`, and vitest's name
  filter separately broken under the integration config — the revision measured the
  fix rather than assuming it) plus an assertion mechanism that could never observe
  its effect; regroup-by-shared-file fired (u5 → u1's PR); the fresh verifier surfaced
  a baseline-red integration file and the orchestrator classified it correctly against
  #785/#811 instead of blaming the unit; per-file mutation honesty-flagged
  aggregate-only on a 19-file unit; and the review found two real money-visibility
  bugs that had shipped green through a shared fixture gap, closing both with
  discriminating tests. Also recorded: run 5 merged its PR without the owner's merge
  word (session-level consent breach, outside `/adw-build` — the adw runs 6–7 held
  their merges correctly; recorded owner-side against the standing rule).

- **v2.9 (2026-07-28)** — owner-driven, not run-driven: two asks, one about the shape of
  the work, one about the size of the contract.
  **(1) Intents are now append-only and extensible (core §1/§1.1, init Phase 0.5).** The
  owner's report: "after I ran 1 adw-build and I start testing and getting new issues …
  I want to continue sending the issues and the pipe run for these new items in the same
  pipe." The pipeline had no such verb, so mapa cirúrgico became three disconnected
  intents across three sessions — `…-manager-bugs` (u1–u5), `…-round2` (ids restarted at
  `u1` against a live `u1–u5`), plus a correctly-split-out feature. The cost was not
  bookkeeping: round2's triage had to *reconstruct by hand* that its u2 carried a
  semantic dependency on round1's still-unbuilt u4 ("u4's design assumes owner_share is
  ABSENT from the repasse query"), a class the erratum's own §5.3 says no gate can see.
  An intent is now live while any of its PRs is open, its spec folder still holds
  **untracked** unit specs, or a **non-default** `base:` is unmerged; `/adw-init` detects
  the match and proposes extension, continuing unit ids from `max+1` across every id ever
  used and reading merged units' specs back from git (§1's deletion rule means the main
  tree no longer has them). Review of this PR hardened five points that would each have
  silently defeated the mechanism: liveness keyed on bare folder existence never expires
  (merged folders return tracked at the next `git pull`, and `develop` is never merged, so
  every past intent read live); an OPEN-PR unit's spec had no named retrieval path though
  it is in neither the main tree nor `<base>`; `amend: uNN` had no slot in the S1 block
  that §7 declares exact, hiding the run's only spec rewrite from the approval gate; `max`
  computed off a best-match-truncated `gh pr list --search` reuses an id; and suffix-only
  `*-<slug>` matching turned the new refusal into a block on unrelated runs. Two properties
  fell out that a fresh slug cannot express: a new issue inside an **unbuilt** unit's
  scope becomes `amend: uNN` — a spec revision, not a new PR — and the triage is
  required to report cross-batch semantic dependencies explicitly. Extension is proposed
  at S1, never assumed; a different `base:` or subject is still a new intent, and the
  session-boundary provenance rule is untouched (earlier open PRs stay the owner's).
  Build-side, "multiple dated folders for one slug → newest wins" flipped from silent
  selection to a refusal: with append-only intents a second folder means someone minted
  instead of extending, and picking the newest would drop the earlier units from the
  manifest.
  **(2) The contract was pruned against adherence, not tokens.** At 920 lines the three
  command files cost ~12k tokens against runs spending 100k–800k — pruning for cost is
  noise. The argument is that long contracts get skimmed, which is observable: runs 4
  and 6 both skipped a mandatory review at the bound, run 7 stretched a rule reading
  "one line" to four. Cut: the D0-INACTIVE activation machinery (unreachable since the
  flip — activation counting, the progress note, the `depth "uN→D0"` refusal path), the
  §3.4 step-2/step-3 duplication (step 2 now points at step 3 "verbatim minus one named
  line" instead of restating its provisioning), and every multi-line incident narrative,
  compressed to a consequence clause plus an erratum pointer. Deliberately NOT done:
  deleting the citations outright. A bare rule gets rationalized around — the same
  reason this repo's forbidden-patterns table carries `Regressed PR #NNN` on every row —
  so each keeps a short "what it cost" clause. Honest accounting: the prune removed ~45
  lines and extend-mode added ~110, so the contract grew. The prune's measurable effect
  is on the scan-critical surfaces, not the total.

- **v2.10 (2026-07-29)** — throughput recalibration. The owner asked whether the runs,
  which take hours, are earning it. Forensics on `mapa-fixes-batch-2` (3 units, init +
  build + PRs) and `mapa-fixes-batch-3` (6 units, init only) separated the wall-clock:
  **machine time is 2.7h and 2.6h; the sessions span 50h and 24h.** The remainder is the
  human gate — batch-3's triage finished and then waited 20 hours at S1. That is the
  single largest wall-clock item in the pipeline and it is not a pipeline defect, but it
  means "the run took a day" and "the run burned a day" are different claims, and §5.1
  could not tell them apart. It can now: a **run time split** row, computed from four
  `date +%s` stamps and printed as `⏱ run machine <t> · your gate <t>` on S2 and S3
  (adw-core §7.1). The stamps store nothing — they are transcript output, like every
  other free metric — so §5.1's no-run-database rule holds. The reason this matters is
  narrower than "observability": conflated, the two numbers produce one complaint ("slow")
  and invite one wrong fix (cut depth), and cutting depth is precisely what the refute
  evidence below forbids.
  The deep passes were audited for whether they earn their cost, and they do — the refute
  agents did not return nitpicks. In batch-2 one measured that **every** `file:line` in a
  spec and plan was anchored to `develop` while the PR targeted the chain branch (one file
  off by 141 lines), and another queried **production** to show the diagnosed root cause
  had zero incidence there — the fix targeted a shape that does not occur — plus a frozen
  `verify` that exits 1 on "No test files found". In batch-3 one read React Router's own
  source to refute a design's stated reason for rejecting sibling routes, another found an
  AC asserting a measurement on an element that unmounts in that same tick, and a plan pass
  found 3 tasks broken as written and 4 spec requirements with no implementing step. None
  of those is reachable by a cheaper gate. **The deep passes stay.**
  Three mechanical losses were fixed instead. **(1) Depth inflation:** run-7 cut zero
  D0/D1 units out of six. u4 — one CSS selector, verify already a discriminating grep —
  was demoted purely because its component has no co-located test file, buying a 191-line
  spec, a 260-line plan and a refute agent. §3's verify-home criterion now reads
  test-file **OR** red-on-revert mechanical assertion; the other three criteria are
  untouched, so a grep verify buys no relief from the ≤2-file bound or the trap domains.
  **(2) The wave barrier:** run-7 dispatched 4 of 6 unit authors, then held the last two
  until the *last* of the four returned — two slots idle for 57 minutes behind an
  82-minute straggler, spec phase 136 min against a possible ~85. Phase 3 now dispatches
  on slot-free, never on batch-complete; the straggler is by construction the unit with
  the most to discover, so blocking on it loses every time. **(3) The artifact budget was
  advisory, and then it was the wrong shape.** "Exceeding takes one stated line of why" is
  a toll, not a bound: run-7's u3 plan paid it and landed at 562 lines, 87% over, caught
  only by a post-hoc trim agent. The escape line is deleted. But the first version of this
  fix kept the flat cap as the operative rule, and the owner's challenge —
  *"wouldn't it be better if, when the task is simple, the plan is simpler?"* — exposed
  that the cap measures backwards. Checked against the run: u4's **one CSS selector**
  produced 191+260 lines and was **compliant** at 200/300, while u3's genuine routing
  change was the only violation. A constant fires on size, and size is what a hard unit
  legitimately has; it is blind to 451 doc lines for a one-line diff. So the operative
  bound is now a ratio — **plan shorter than the diff it produces, spec shorter than the
  plan** — with 200/300 demoted to a backstop against a wrong estimate, and labelled as
  what they are: inherited numbers, never derived. The ratio was already in the file as a
  parenthetical rationale while the constant held the operative slot; the wrong one had
  been promoted. Authoring-time the ratio is estimated (the diff does not exist yet) and
  therefore gameable, so adw-build §3.5 measures it for real at PR open — where the diff exists and
  `docs/superpowers/**` is already excluded for review scoring — and flags
  `⚠ artifact-heavy` on the S3 line. It measures and never blocks: the code there is
  written and gate-green, and burning a correct PR to punish a document is a worse trade
  than the bloat. That flag is also the denominator §5.1 needs before 200/300 can be
  retuned or retired on evidence rather than taste.
  Also on record from batch-2: the mandatory §3.6 review was skipped on three PRs, flagged
  at S3, and not stopped — the owner discovered it two days later and hand-drove three
  review loops plus a fix agent. Most of what read as "a lot of back and forth" traces to
  that one skip. The rule was already unambiguous — the failure was compliance, not
  wording, so no prose was strengthened. It was closed mechanically instead: §3.6 now
  **fetches** the PR's comments and reviews and requires one dated after the last
  production-code commit before any surface may print `ready` or `review clean`. Three
  drafts got there. The first keyed on
  the `### Code review` comment carrying the reviewed head SHA — and was wrong twice over,
  caught only by reading `/code-review` rather than assuming it. The SHA reaches that
  comment **only** through finding permalinks, so a clean review carries none; and Phase 7
  has branches that post no project comment at all, letting the plugin's own comment stand.
  A header-and-SHA match would therefore have blocked precisely the PRs that passed
  cleanest. Timestamps are shape-independent and survive both. A third error was caught by
  the owner asking whether re-review is unconditional: dating the evidence on `$VSHA`
  contradicts the void rule two lines above it, which requires a re-review **only when the
  delta touches production code**. A docs-only amendment moves the head, no review
  post-dates it, and the PR blocks for a cycle the contract just exempted — or wedges
  permanently once the 2-cycle cap is spent. The check therefore dates on the last
  production-code commit (`git log -1 … -- . ':!docs/superpowers/**'`), which also makes
  the void rule self-enforcing rather than dependent on remembering to void. Three drafts,
  three defects, all of them found by reading the thing being depended on instead of
  assuming its shape — the same lesson §5.3 keeps producing.
  The check is a floor, not a proof — an unrelated comment satisfies it — and that is
  sized to the failure that occurred: run-5 declined the rule, said so at S3, and shipped
  three PRs as `ready` when the note drew no objection. Flagging a deviation is not
  permission to take it, and a gate the runner can narrate past is not a gate.
  **Found in passing, not fixed here:** `/code-review`'s own re-run guard
  (code-review.md Phase 1) exits "already reviewed at this SHA" when a prior comment
  body contains the current head SHA — which, per the same two facts above, a clean
  review never does. That guard is dead for exactly the reviews it should short-circuit,
  and the fix is to stamp the head unconditionally in the comment footer. Out of scope
  for an adw erratum; recorded so the next `/code-review` pass has it.
  This is the third mechanical-evidence conversion in this erratum (`wc -l`, artifact
  ratio, review comment) and they share a shape worth naming: each replaces a judgment
  the runner renders about its own work with a value fetched from outside it.

- **v2.11 (2026-07-30)** — the review loop is extracted to `/pr-ready`. The owner asked
  whether the loop they keep invoking by hand could be made reusable. A critical pass
  found the proposal half wrong and narrowed it three times before a file was written:
  - **`/code-review` already verifies.** `review-core.md` §4 ("Smart verification") runs
    layer-branched gates over applied fixes, declares docs-only honestly, and blocks a
    push on red. The gap was never *verification* — it is **independence** (a checkout
    the author never touched; an agent that neither wrote nor fixed the code) plus
    **evidence** (a fetched review, a void rule). The extracted file composes
    `review-core` instead of restating it, which deleted most of what the first sketch
    would have invented.
  - **The mutation check does not travel.** It is keyed on the unit's declared `verify`
    command — an adw contract field a generic PR has no equivalent of. Deriving a proxy
    would be new design smuggled inside a refactor, so §3.2's check stays in
    `/adw-build`, and §3.4 requires it as an addition to the shared verifier's report.
  - **`BASE` stays a parameter.** Deriving it from `baseRefName` is right for the generic
    case but would silently move adw's sub-PR anchor from a merge-base to the integration
    head. `/pr-ready` §1 takes an override and §3.4 passes adw's own per-PR-type table —
    so v2.10 behaviour is preserved by construction, not by hope.

  The extraction also surfaced a **pre-existing defect in `review-core` §1.2**: its
  provisioning carried the base symlinks and `pack:shared` but neither conditional block,
  so a `/code-review` run on a PR that adds an npm dependency hits TS2307, and one on a
  `packages/shared` PR hits TS2305 — both presenting as the PR's own breakage. Those two
  blocks existed only inside `/adw-build` Phase 2. Now in §1.2, where all three consumers
  see them — Phase 2 and `/pr-ready` §4.3 both point there rather than carrying a copy.

  Two contract defects the review caught before merge, both the same class as the
  extraction itself: `/adw-build` delegated §3.4/§3.6 to `/pr-ready` without a **Read**
  step (and `/pr-ready` cited `review-core` the same way) — `.claude/commands/*.md` have
  no auto-include, so an unread pointer is a rule loaded nowhere and the pass gets
  improvised. And Phase 0's contract-freshness check still grepped only the three `adw-*`
  files, so a stale `pr-ready.md` would have run an old verify contract with no drift
  note. Both closed: explicit Read instructions, and both new files added to the grep.

  Deliberately NOT moved: the 45-min clock (anchored on implementer dispatch — a hand-run
  has no implementer), S3/S4, chain state, the artifact ratio, the depth ladder. The split
  rule is stated once in `/pr-ready` so future edits classify without re-litigating —
  **loop body in the shared file, loop control in the caller**; anything that must know
  *why this PR exists* is control. adw-build drops from 505 to 426 lines and every §3.4 /
  §3.6 citation still resolves, because the headings stayed and only their bodies became
  references.

  The standing objection, recorded rather than solved: adw sizes this loop through the
  depth ladder, and a standalone `/pr-ready` has no depth signal. It is deliberately NOT
  given a second budget system — `review-core` §4 already makes the gate set proportional
  to the diff, leaving one worktree and one sonnet subagent as the fixed cost. If that
  flat cost proves wrong on small PRs, the fix is a cheaper independence pass, never
  another ladder.

- **v2.12 (2026-08-01)** — runs 8–10 recalibration (`mapa-fixes-batch-3` PRs #838/#839/#841,
  `mapa-fixes-batch-4` PRs #843–#853, `module-toggles` PR #854). Three read-only analyzers,
  one per run, under a hard citation contract (every claim carries a PR number, 7-char SHA,
  `file:line`, or timestamp; anything unestablished returns `unknown — <what would establish
  it>`), with adjudication held back to the orchestrator. That split earned its keep
  immediately: the batch-3 analyzer's headline finding — v2.10's `⚠ artifact-heavy` flag
  failing to fire on 5 of 6 units — was **withdrawn**, because v2.10 merged
  `2026-07-30T21:40:30Z` and two of the three PRs opened 20h22m earlier. adw-build §3.5
  measures at PR-open; they were never bound. The one PR that was bound (#841) is the one unit that
  complies. An analyzer that adjudicates its own evidence would have shipped that.

  What the runs actually cost, and the fixes, all in the operational contract:

  - **The final chain PR ships unreviewed — the most expensive finding.** #853 merged
    7m50s after opening: +3950/−155 across 48 files, `comments: 0`, `reviews: 0`. Phase 4
    already said the final PR "runs the FULL Phase 3 loop", and `/pr-ready` §5 would have
    returned `0` and printed `blocked`. Neither fired. Worse, chain close is the *only*
    place code exists that no unit ever contained — closing #853 hand-added one line
    neither parent contained, `bodyInset: 'self'` on the `SharePanel` push in
    `MapaModule.tsx` (`0c7a82c6`). It did not come from the textual conflict (that resolved
    take-both, inventing nothing) but from a cross-unit type error, and no gate could see
    it (the call site casts `as StageEntry`, so a missing required field is still green
    tsc; the failure mode is a wrong mobile gutter). The least-reviewed code in the run is
    its most integration-shaped. Phase 4 now gates the consent request on the fetched
    comment count and names the rationalization ("every unit was already reviewed" is the
    reason it is mandatory, not a waiver).

    **Forensics (2026-08-02)** — checked against the parents rather than read off the body.
    `git show --cc 0c7a82c6` marks exactly one token as present in neither parent, the
    `bodyInset: 'self'` above, and the resolution is **correct**: spec u10's audit table
    gives that body `SharePanel` → `.aj-invite-screen` → `'self'`, all four sibling
    `SharePanel` pushes declare it, and `'chrome'` would render 32px and inset the panel
    tint — the regression that table warns about. One wording fix: this bullet originally
    cited the `TS2352` *error*, which is reported on the `as StageEntry` cast that
    pre-dates the merge in parent `49b28f61`, where the merge-created line is its *fix*.
    Phase 4 now derives the set from `git show --cc` and bounds the read with a
    `git merge-file` replay: only 9 of #853's 48 files were touched by both parents, and 8
    of those replay byte-identical, leaving one file to read.
  - **Contract bumps land mid-run and nothing re-checks.** batch-3 spanned v2.10 (20h into
    a 26h run), batch-4 spanned v2.11 (22 min after its first sub-PR opened) — two
    consecutive runs. v2.7's freshness check is a Phase 0 snapshot and runs have outgrown
    it. Phase 0 now pins `$CONTRACT_SHA` and Phase 4 re-compares. The loaded text cannot
    change mid-run, so the fix is honest reporting, not correction: S3 must say which
    contract the units were built under. batch-3's u5 sync merged the new `adw-build.md`
    into its own worktree as *source* while executing the old text — a sync touching
    `.claude/commands/**` is now an explicit tell.
  - **`base:` did not reach PR targets.** All 9 batch-4 specs declared
    `base: release/mapa-cirurgico`; #846 opened against `develop` 1h51m *before* that
    release was absorbed. adw-build §3.5 now asserts `baseRefName` after create and defines the
    retarget-on-absorption case the contract previously left unnamed.
  - **Evidence reporting was discretionary.** The mutation row appeared on #839 and on
    neither #838 nor #841; module-toggles had two production review rounds with no
    fetchable comment of their own. Nothing could distinguish "ran, unreported" from "never
    ran". adw-build §3.4 now lands the gate table and mutation row in the **PR body** — fetchable
    forever, surviving re-reviews, and where a human merging days later looks.
  - **`/pr-ready` §4.3's `pr-ready-<N>-` was unfulfillable in the ADW path** — a v2.11
    defect. adw-build §3.4 verifies *before* §3.5 opens the PR, so pass `v1` has no `<N>`;
    every run improvised a slug name while `/pr-ready` §8's glob still said `<N>`, and a
    cleanup glob matching nothing fails silently. Three orphan worktrees across three runs.
    Both sides now key on a `$REF` parameter, and `/pr-ready` §8 asserts its own sweep
    instead of assuming it.
  - **`/pr-ready` §6's re-verify was prose and got narrated past.** module-toggles closed with
    "`<sha>` is docs-only, so the verification above still stands for every executable
    line" — reading the review exemption onto the re-verify, which says `always`. The
    merged tree was one no pass had checked out. The sentence is almost true, and that is
    why it worked: the executable lines *are* unchanged; what is unverified is the tree,
    and the tree is what merges. `/pr-ready` §6 is now a matrix plus a `rev-parse`
    comparison, and §7 re-**asserts** `verified <sha7>` at print time (§7 rejects
    "re-derive" by name — deriving it fresh reproduces the lie). Same shape as v2.10's own lesson — replace
    a declinable narration with a fetched value.
  - **Chain sync merged at N=5**, the inclusive edge of the `N ≤ 5 → rebase` band. Phase 4
    now runs the branch as a shell test rather than an instruction to compare by eye.
  - **A sync conflict was resolved unattended in trap-domain money code** (`d210ca5`,
    repasse-share logic), correctly, catching a real auto-merge defect, with no escalation.
    Phase 4 now says what "unattended" means: without the owner, not without care.

  **What the runs got right, and it is not a small list.** Escape rate across all 18 units
  is **zero** — every post-run commit sharing a file was traced line-by-line and is
  unrelated later work, including the em-dash sweep, which was writing that rule for the
  first time. §9 lists escape rates for agent-authored code as unmeasured industry-wide;
  this is three runs of local measurement. batch-3 had zero `fix-attempt` commits across six
  units; batch-4's worst was two against a bound of three; no run exceeded the two-cycle
  review cap. And batch-4 — the first run fully bound by v2.10 — validates the ratio's
  premise directly: **all 9 units pass the 200/300 backstop while 4 of 6 D2/D3 units fail
  the ratio** (u9: a 267-line plan against a 71-line diff). The constant sees nothing the
  ratio catches.

  Two things stayed unmeasurable and are recorded rather than fixed. The machine/gate split
  cannot be reconstructed post-hoc — v2.10 stores nothing, batch-3 shows a 21h dead gap and
  module-toggles a 3h30m one, and nothing after the fact distinguishes an owner wait from a
  stalled pipeline. And whether the `⚠ artifact-heavy` flag actually printed on batch-4 is
  unknown for the same reason: no S3 transcript survives a run. Both are the cost of the
  deliberate "stores nothing" decision, which is still the right trade — but a retro can
  only measure what outlives the session, and that is now the binding constraint on
  observability, not the metric definitions.

  **Second pass, same day, four adversarial lenses (stop-criteria · clock forensics ·
  adversarial-on-this-PR · cost/observability).** It found the round's own centrepiece
  weak in the now-customary way, and one class of defect worth naming: **five of the eight
  fixes above were prose or non-executable snippets, and four of those five did not do what
  they said.** The Phase-4 N=5 "shell test" shipped as `#`-comments reading an out-of-scope
  `$N` (empty coerces to `0` under zsh → always rebase; exit 2 under bash → always merge —
  the count is never consulted) with an `A && B || C` fallback that auto-attempts the very
  merge the next paragraph mandates aborting. The mid-run contract re-check was placed
  *before* the fetch that could make it fire, and `$CONTRACT_SHA` was pinned but compared to
  nothing — while being a **tree** sha over **26** files against a five-file, commit-sha
  contract set, contradicting a sentence this same round added ("keep this list identical to
  step 1's"). `/pr-ready` §8's cleanup assertion inverted its own exit code (clean → 1, dirty → 0) and
  reproduced the silent-empty-glob failure it was written to close. And the `$REF` rename
  stranded the orphans it was meant to reap: `/cleanup` row 8 parses the PR number out of
  the directory name, which the new name no longer carries. All four are fixed here, and the
  pattern is the lesson — **a fix stated as prose or as a comment is not a fix**; this round
  wrote "run the branch, do not eyeball it" *inside a comment*.

  **The headline, and the answer to §4.8's own standing promise: the 45-minute bound is
  replaced by progress conditions.** §4.8 said "provisional, recalibrate from the first ten
  runs"; this is run 10, and the evidence is one-sided. Zero `adw:failed`/`adw:blocked` from
  the bound across 34 pipeline PRs — it never reached its own terminal state. Three recorded firings,
  all destroying completions (#807's only review; a first review blocked at **44** min, below
  the threshold; #846's per-file mutation on **31** files); the one real overage unrecorded.
  Observed fix depths are **19** (#828), **4** (#829, a counter reset across resume), **2**
  elsewhere — so the cycle caps are not a redundant backstop that made the clock unnecessary,
  they are the *only* backstop and they were breached once. That is the argument for making
  them countable (Phase 0 step 7) and for adding a boundary cap, not for trusting them.
  The single genuine runaway — **#828, 19 `fix-attempt` commits over ~23h** — was invisible
  to it by construction. And the owner's original complaint ("we skip reviews because of the
  45-minute rule") turned out **false today and never the dominant cause**: `30b0985b` made
  the first review unconditional, and the two PRs that did ship unreviewed (#853; and **#834**,
  merged **26 seconds** after opening at +4135/−629, which the first pass missed entirely)
  are Phase-4 chain closes, outside the bound's scope. #833 was reviewed, so the chain-close
  gap is 2 of 3 — inconsistent execution, which is what the consent gate above fixes. A false
  premise, a real defect underneath it: the clock was quietly taxing the **mutation gate**,
  the one detector §5.2 credits for the failure class this whole design exists to prevent.

  Three seams the swap exposed, all closed here: cycle counts must be **recovered on resume**
  (#829 shipped `fix-attempt-4` against a cap of 3 across a 3-day resume — the one non-time
  metric the pipeline had, silently reset by the same event that reset the clock);
  `owner-wait` must be **subtracted per PR** as §7.1 already does run-wide; and the durable
  record must move to the PR body (adw-core §7.2), because a stop metric nothing preserves is
  precisely how the 45 survived ten runs unfalsified. Also corrected: `reviews: 0` is a false
  signal on this repo — `/code-review` posts an issue comment, never a review object, so all
  34 pipeline PRs report it; the comment is the signal.

  **Third pass, three more lenses (executability · consistency · adversarial), run against
  the amendment itself — and it caught the amendment stating two facts that are false.**
  "Maximum observed fix depth 2" was measured off reachable local refs; the real depths are
  **19** (#828) and **4** (#829), both cited *in the same diff* ten and twenty-five lines
  away, their branches deleted after squash-merge. The inference it carried — "so the cycle
  caps bound first, always" — was the warrant for deleting the only unconditional backstop,
  and it is backwards: the caps are the *only* backstop and they were breached. Condition 4's
  "real precedent" (`515c9310` reverting `083e6d09`) yields **zero** duplicate trees, because
  the implementer bundled the revert with a replacement — so the condition as first written
  was near-dead code citing a case that would not have fired it. Both are now stated as
  measured, and condition 4 is marked precautionary alongside the 4h ceiling.

  Two design holes the same pass found, both now closed: **condition 5 fired on the clean
  happy path** (a green unit's HEAD and gate vector are *supposed* to be unchanged across
  gates→verify and review→re-verify, and `/code-review` with an empty `toFix` pushes nothing)
  — the ideal run would have shipped `adw:failed`; it is now scoped to boundaries closing a
  repeat cycle. And **a unit that reds no gate spends no fix cycle**, so conditions 1–3 never
  evaluate; if it also commits each pass, 4–5 never fire — under the old clock that stopped
  at 45 minutes, and nothing replaced it. Hence condition 6, a boundary cap, sized at 16
  against a legitimate maximum of 10 rather than the 12 first drafted, which would have
  tripped a run that did everything right. Six of #828's 19 fix-attempts were spec/docs/body
  edits: the shape is real.

  The generalisable lesson, and the reason this pass was worth running on a document about
  rigour: **five of v2.12's first eight fixes were prose or non-executable snippets, and four
  of those did not do what they said** — a "shell test" shipped as `#`-comments reading an
  out-of-scope variable, a mid-run check placed before the fetch that could make it fire, a
  cleanup assertion whose exit code was inverted, a pinned sha compared to nothing. The round
  wrote *"run the branch, do not eyeball it"* **inside a comment**. A fix stated as prose is
  not a fix, and the discipline that catches it is the same one §5.3 prescribes for the
  correlated blind spot: a reader who executes the text rather than reading it.

- **v2.12.1 (2026-08-02)** [renumbered from v2.13] — a forensic read of #853's chain-close merge (`0c7a82c6`), the
  exact surface v2.12 had just made mandatory to review. **The resolution was correct**:
  `bodyInset: 'self'` is the only token `git show --cc` marks as present in neither parent,
  and it matches the spec's own audit table for that body (`SharePanel` →
  `.aj-invite-screen`, which owns 16px), all four sibling `SharePanel` push sites, and the
  counterfactual (`'chrome'` would render 32px and inset the panel tint — the regression
  that spec's own table warns about). v2.12's warrant survives intact: merge-created code
  did exist, and no gate could see it (the call site casts `as StageEntry`, so a dropped
  required field is still green tsc).

  One wording fix, and it is the reusable half: v2.12 cited the `TS2352` *error*, which is
  reported on that pre-existing cast, where the merge-created line is its *fix*. Chase the
  body's nouns and you land on a ` +` line and conclude nothing was invented. So Phase 4
  now derives the set from `git show --cc` and reads the body against it — never the
  reverse.

  Phase 4 also gains a *bound*, not more scope: the `++` lines, plus a `git merge-file`
  replay over the files **both** parents touched, proving nothing was hand-edited outside
  the conflict. For #853 that set is 9 files of the 48 it changed, of which 8 replay
  byte-identical — one file to read, not 48. The failure this closes is cost, not laxity:
  "re-review 48 already-reviewed files" is the shape a run rationalizes past, and a
  mandatory review nobody can afford is a mandatory review that does not happen. Same
  discipline as the bullet above — the claim was checked against the parents rather than
  read off the body that made it.

Each round has found the previous round's centrepiece to be its weakest part. That is the
intended behaviour of the process, and the reason nothing expensive has been built yet.

A caution for future revisions, since it already happened once: this document's own
recommendations were cited back at the owner to re-open a decision the owner had made.
**An adoption gate is advice about uncertainty, not a standing veto** — once the uncertainty
it was written to resolve has been resolved by other means, the gate has no remaining
function and removing it is not a loosening of rigour.

**The worked example has now been wrong twice, in the same way**, in a document whose
central rule is the one it violated. That is worth more than the fix: it is direct evidence
that §5.3's correlated-blind-spot problem is real and operating on this very file — the
author, the reviewer, and the rule were all the same model, and the rule was still
misapplied in its own demonstration. v2's example (§3.2) groups u3/u4 into the chain for
that reason, and the §3.2 surface prints the dependency annotations precisely so the human
gate can catch the third occurrence.

- **v2.12.2 (2026-08-15)** [renumbered from v2.14] — run-11 (`team-active-seat-model` u1+u2) retunes two rules, and
  the interesting part is that both were retuned *against* the direction the run itself
  argued for. **(1) The artifact budget was measuring a draft.** Init relayed five specs at
  133/202/210/212/213 and the orchestrator spent three separate main-loop rulings on
  breaches of 2–13 lines. The artifacts actually committed were 239L and 253L spec, 406L and
  688L plan. So the flat 200/300 fired on the harmless case (density in D3 money/authz work)
  and missed the egregious one entirely — a 688L plan, 129% over, reported by no surface at
  all, because Phase 4 counted a pre-revision draft and adw-build §3.5 counted only the
  ratio. A constant that behaves that way is not mis-tuned, it is measuring the wrong thing,
  and raising it to 260/400 (the first proposal) would not have contained 688 either. Fix
  has three parts: the guard rail goes advisory (breach → one `⚠ over-guard-rail` line on
  S2, never a refit round-trip, never a prose ruling), a hard stop lands at 2× where
  "mis-cut" is unambiguous, and §3.5 re-counts the **committed** artifact — the first count
  ever taken on final text. The ratio is untouched: it caught the same unit correctly at
  1.26x, at the only place a real denominator exists. **(2) The shared test database is
  structurally unfixable and is now bypassed by default.** u2 lost four integration tests to
  `infirmary_patients.person_id NOT NULL`, a column on no branch it could see, left behind
  in `plantaopro_test` by `adw/patient-entity-restructure`. The shared DB accumulates the
  union of every branch's schema and Drizzle can never undo it, so isolation-by-convention
  loses eventually; it lost here even though the private-DB override was already documented
  at adw-build §Phase 1, because the run reasoned past it ("`.env.test` is tracked and the
  script hardcodes it") without testing the premise — Node's `--env-file` yields to an
  exported var, and `integration-setup.ts` already read one. Opt-in isolation is the defect.
  `integration-setup.ts` now derives `plantaopro_test_<worktree-dir>` whenever it runs from
  a linked worktree, and publishes it to `process.env.DATABASE_URL` so the app pool cannot
  disagree with the harness. **(3) The `when` high-water is the same failure one blast
  radius up**, and it is not a test-only problem: applying u1's migration moved the shared
  DB's mark to `1785600000000`, and on the same day two *unmerged* branches held `idx 56`
  at the identical `when 1784800000000`. Whichever merges second is silently skipped in
  prod. `scripts/check-migration-order.mjs` (wired into `audit.sh`, every mode) fails on a
  `when` that does not beat the merge target's max, on a reused `idx`/filename prefix, and
  on journal orphans in both directions. Deliberately NOT fixed here: `audit.sh`'s
  idempotency regex still cannot see two-line `ADD COLUMN`, `ADD CONSTRAINT` or
  `CREATE TYPE` (Trello #208) — it needs statement-joining and a grandfathering rule, which
  is its own change, and mixing it in would have hidden it inside this one.

- **v2.13 (2026-08-15)** — context cost, measured for the first time, from the
  `subscription-locks` run (u1 #924, u2 #925, u3 #931, u4–u10 #933–#939, final #940; the
  intervening numbers are concurrent billing work, not this intent's — a range reads as
  contiguous and this one is not). §5.1 dropped token burn because "no source exists";
  a source does exist. **Session transcripts persist on disk** at
  `~/.claude/projects/<cwd-slug>/<session-uuid>.jsonl`, with dispatched subagents' own
  transcripts under the sibling `<session-uuid>/subagents/`. Compaction evicts turns from
  the context window; it does not delete the record. This is inside §5.1's prohibition, not
  an exception to it — the prohibition is on a run *database*, and §7.1 already permits
  reading your own transcript. Nothing is written.

  **What the run's orchestrator window actually held** — 2.7 MB of tool output over 1,478
  calls: `Bash` 809 calls/32% but a 0.5 KB median (volume, not size, and ~98% of the calls
  are already compound); browser 17 `computer` calls/30%, the 11 image-bearing among them
  at a ~79 KB mean (9 screenshots, 1 zoom, 1 click frame) and the other 6 at ~0.4 KB; `Read` 84
  calls/23%, where 11 reads above 20 KB carry half the read bytes and the top quarter carry
  three quarters; `Agent` 125 calls/**10%** at a 1.1 KB median. **Dispatching is not what
  grows the window** — the §4.9 boundary is carrying its weight — which is the finding that
  produced adw-build §3's reading discipline (inline to edit, dispatch to answer, size-check
  first) and killed a drafted rule to route routine lookups through subagents: below ~2 KB a
  dispatch costs more than the read it replaces.

  **Total pipeline spend is a different quantity and inverts the picture:** subagent-internal
  tool output is **5.7× the orchestrator's**, ~85% of the run — almost entirely their own
  `Bash` and `Read`. (v2.15, on a correct dedup and four intents: **4.3×**, 81.2% of the run
  — 234.9M vs the orchestrator's 54.5M, same figures adw-build's reading-discipline
  paragraph cites. The direction held; the figure did not.) Recorded, not ruled on. No rule should be written against it without
  first establishing how much of that reading is necessary; the alternative is the error
  this entry documents below.

  **Two rules that did NOT survive drafting, recorded so they are not re-proposed.** (1) A
  compaction *checkpoint* ("compact at a unit's verdict") — inverted and unsatisfiable:
  `ready` is precisely when an unmerged self-opened sub-PR exists, so compacting there
  strands it; and `blocked`/`failed` PRs stay open by design, so "wait for a merge" can
  never recur. Compaction is also not schedulable from inside the loop. What replaced it is
  survivability, in adw-build's provenance note: if run state was lost with a `ready` sub-PR
  unmerged, do not merge it. (2) A *screenshot budget* in the contract — ADW mandates no
  browser QA anywhere (`review-core.md` records a missing browser as the norm), so the
  contract has no business budgeting it; and the 16× `zoom`-over-screenshot saving that
  motivated it does not survive scrutiny — the one `zoom` in the run fired immediately
  *after* a full screenshot and depended on it for coordinates, and at most 3–4 of 10
  screenshots were plausibly convertible.

  **Method note, and the reason this entry is unusually explicit about its own errors.**
  Three successive drafts of this finding were confident and wrong: the first diagnosed from
  the contract's silence while the data sat on disk; the second measured four sessions that
  merely *mentioned* the slug (billing work, a contract-design session, and a different
  intent's run) rather than the run's own; the third concluded subagent internals were
  unpersisted from a single failed `isSidechain` grep, with 132 subagent transcripts in an
  adjacent directory. Each survived self-review. Each was caught only by adversarial agents
  pointed at raw data and told to refute. That is §5.3's correlated blind spot reproduced
  three times against a document *written to record it*, and it is the strongest local
  evidence for §5.3's own remedy: prose review agrees with plausible prose, and only a
  non-model gate — here, re-derivation from the raw record — constrains it.

- **v2.14 (2026-08-16)** — **absolute token figures below are inflated ~2.3× by a
  per-transcript-record counting defect; see v2.15 for the dedup rule. The ratios — including
  the 91% headline, which recomputes to 91.3% — and every conclusion stand.**
  v2.13 measured context in **tokens**. Re-measured on the
  `team-active-seat-model` run (7 units, #954/#955/#960/#961/#962/#963/#964) with each
  subagent's tokens **weighted by the tier it actually ran on**, and the picture inverts.

  **Snapshot boundary, because it matters for two figures below.** The measurement was taken
  at ~2026-08-16T14:40Z against a session that was still live; it kept running ~1h45m longer.
  Every figure here is as-of that cutoff. Two have since moved — peak window 738,843 → 801,247,
  manual compactions 2 → 3 — and neither moves a conclusion. Say the cutoff when you quote a
  live session; a number from a running transcript has a timestamp whether or not you record one.

  **The dispatch tier is the pipeline's cost structure.** 37 of 83 `Agent` calls carried no
  `model:` and inherited the orchestrator's Opus. Price-weighted (opus 5×, sonnet 1×, haiku
  0.27×) those 37 were **91% of all subagent cost** — 792M of 866M sonnet-equivalents. The
  43 explicitly pinned sonnet dispatches were 8%. This is now adw-core **§8**, one table,
  classified by what the agent *produces*: find / re-execute / look up → pinned; author /
  adjudicate → inherit. adw-init's critical passes and adw-build reference it and do not
  restate it.

  Two narrower pin rules already existed and neither generalised: `pr-ready.md` §4 pins its
  verifier and was honoured on **4 of 9** verifier-class dispatches; `adw-init.md` §Critical
  passes had no pin at all, so 12/12 refute agents ran Opus — **13% of the run's subagent
  cost** for a read-only find-and-report job the same run gave ~35 sonnet/haiku agents on
  code. Nobody argued those reviews were worse. The tier decision had been made and was simply
  not written where every dispatch reads it.

  The review-lens bucket resists an exact count on purpose: 36 to 40 agents depending on where
  you cut between "review lens" and "remediation agent responding to one", and 6–8% of
  price-weighted subagent cost across every boundary tried. Quote the range. A single figure
  here would be a classification choice wearing a measurement's clothes.

  **The review path was bypassed on 4 of 7 PRs.** `/code-review` was invoked on #954, #955
  and #960. #961–#964 were reviewed by ~20 orchestrator-authored lenses instead — findings
  without the §3.1 adjudication bar, the calibration loop, the §7 safety stops or the
  `fix(review):` discipline the cycle counter is recovered from, and they took 25 review-fix
  commits between them. Nothing on any surface distinguished them. adw-build §3.6 now states
  the review path is `/code-review`, and adw-core §7's `note review #NNN` line makes a bypass
  visible on S3.

  **Owner-wait and machine idle are indistinguishable in a transcript, and the first draft of
  this entry conflated them.** ~5.2h of the run was idle with neither orchestrator nor
  subagent activity. Split by whether a human message lands within 2 min of the block ending:
  **1.7h was genuinely the owner** (two halts; the larger, 90 min, was answered `proceed with
  defaults` — a question that should have ridden S3 rather than blocking a chain overnight),
  and **3.45h was the machine**. The single longest block, 1h51m, looks exactly like an owner
  gate — it even opens with a status table posted while units were unbuilt — and ended with a
  `<task-notification>`: a backgrounded `git fetch` that foreground-timed-out at 15.7 min and
  returned two hours later. No human within two minutes either side.

  Most of that 3.45h has one cause. macOS DarkWake had the host asleep from 03:27:38: AC
  `displaysleep 90` + `sleep 1` sleeps 91 min after the last **keypress**, and Claude Code
  activity does not count, so turns take ~15 min and nothing errors. Environment, not contract
  (`sudo pmset -c sleep 0`). The contract consequence is the one adw-build Phase 1 now carries:
  **stamp `owner-wait` from T1/T2 pairs, never infer it from a gap.** §7.1 already defines the
  stamps; this run inferred instead, and inference charged the human two hours of a sleeping
  laptop while the owner's real 90-minute halt went unexamined.

  **Three findings that did not survive re-derivation, recorded so they are not re-proposed.**
  (1) *Cap the PR-review lens fan-out* — aimed at the cheapest part of the pipeline: those
  lenses were already ~35 sonnet/haiku to 1 opus, 6–8% of price-weighted subagent cost. Real
  duplication exists (#963 got both a "git history" and a "focused git-history" lens) and is
  not worth a rule. (2) *Trimming CLAUDE.md saves ~6%* — unestablished. Cold-start prefix is
  bimodal (14.5K/17.1K for two agents, 39.5K–60.6K for the rest); CLAUDE.md at ~18–20K is the
  dominant plausible component of that ~25K jump but could not be isolated from tool schemas.
  Worth doing for maintainability; the number was not earned. (3) *A compaction checkpoint is
  worth ~9% and therefore still not worth it* — the ceiling was right but the reasoning was
  not: the orchestrator runs Opus, so its 419M cache-read is ~210M sonnet-equivalents, 18% of
  the run. v2.13's structural objection stands unchanged (unschedulable from inside the loop;
  `ready` is exactly when compaction strands an unmerged self-opened sub-PR), so the action is
  to hand the owner the number at a safe boundary — adw-core §7's `note window` — never
  to compact unprompted. (The threshold became absolute in v2.15; the 18% here is a
  pre-dedup figure.)

  **Method, and the third consecutive version where the same lesson had to be relearned.**
  Same as v2.13's, plus the weighting. The three withdrawn findings above were produced by the
  *first* pass over this data and all three survived self-review; each died to a direct check
  against the contract files (`code-review.md` specifies **1** agent on the light path — so a
  6-to-8-agent fan-out could not have come from it) or against the raw per-agent `model` field.

  Then the entry was written, committed, and **sent to a `sonnet` refute pass with the raw
  transcript and instructions to default to REFUTED** — the §8 tier its own table prescribes,
  and the first independent check any version of this measurement has had. It confirmed 8 of 15
  claims outright and returned **two material errors already committed to the branch**: `4 of
  10` verifier-class dispatches (one remediation agent misclassified as a verifier by a regex
  matching "independent verifier" in its *body*, not its role — the correct figure is 4 of 9,
  and it had propagated to three artifacts from one bug), and the owner-wait conflation above,
  where the entry claimed ~4h and named as its headline example a block that was a stalled
  background command. It also refused to reproduce the review-lens count under any
  non-arbitrary boundary, which is why that figure is now a range.

  So: v2.13 recorded that prose review agrees with plausible prose and only re-derivation from
  the raw record constrains it. v2.14's first draft reproduced that failure. v2.14's *second*
  draft — written by an author who had just documented the failure, in the section documenting
  it — reproduced it again, and was caught only because the pass was finally dispatched instead
  of described. The rule that follows is not "re-derive": that has been written twice and
  obeyed by neither draft. It is **dispatch the refuter before you commit the number**, because
  the author checking their own arithmetic is the step that has now failed three times running.

- **v2.15 (2026-08-17)** — the same session, now four intents deep
  (`team-active-seat-model` 7 units · `premium-set-reshape` 2 · `comp-and-trial-rollout` 3 ·
  `team-plan-surfaces` 3, PRs #954–#975), re-measured after finding a defect in **how v2.14
  counted**. Snapshot ~2026-08-17T20:25Z, session still live.

  **Two counting rules, and v2.14 got the first one wrong in both directions.** One API
  response is written to the transcript as several records — thinking, text, tool_use — so
  **(a) dedup by `message.id`**, or you count the same call two to eleven times (v2.14 did:
  ~2.3× inflation). But **(b) keep the LAST record of each id, never the first.** The earlier
  records are mid-stream partials — `stop_reason: null` and a placeholder `output_tokens` as
  low as `3` — and only the final record carries the metered figure. `cache_read`,
  `cache_creation` and `input` are identical across a group; `output_tokens` differs in
  **6,359 of 6,910** multi-record subagent groups. The orchestrator happens to have zero such
  mismatches, which is exactly why a first-record dedup looked verified when it was checked
  there: first-record dedup undercuts subagent spend by **14.2%**. Zero usage records lack an
  id, so dedup itself loses nothing.

  Correctly deduped, the four intents cost **1,032.2M sonnet-equivalents** (snapshot
  ~2026-08-17T20:30Z; see the live-session caveat below): orchestrator 26.4%, spec+plan
  authoring 26.0%, implement 21.6%, independent verify 9.7%, refute 6.2%, PR-review lenses
  4.7%, remediation 3.3%. Treat the last four as ±2–3 points — the verify / lens / remediation
  boundaries are genuinely ambiguous (an agent named "Close u6 verification findings" is two
  of them), and an independent recount that drew them differently got 6.2 / 6.2 / 6.8. The
  first three are robust, and the headline is that **authoring has drawn level with the
  orchestrator as the largest single line item**. adw-build's reading-discipline
  paragraph's `5.7×` subagent-to-orchestrator ratio is corrected to **4.3×**.

  **§8's compliance held; the cost drop that followed it is not §8's doing.** Every dispatch
  after the merge carried a `model:` — zero omissions, against 37 of 83 before. But per-unit
  subagent cost ran **A 64.2M → B 62.7M → C 27.7M → D 34.0M**, and `premium-set-reshape` (B)
  is the control that kills the causal story: it was dispatched *entirely after* the rule
  merged and did not drop. What tracks the drop is **depth** — A and B are 100% D3; C and D
  are two-thirds D2. §8 earns its place on the 91%-of-cost invisibility argument alone; the
  per-unit number is not its evidence and §8 no longer cites it as such.

  **The build loop discards a DAG the pipeline already computes.** `after:` is validated
  acyclic at init and then linearised by adw-build Phase 1's "chains build sequentially".
  `team-active-seat-model` is `u1 → {u2,u3,u4} → {u6,u7} → u5` — four levels, built as seven
  steps. Unit build windows sum to **14.29h** serial against **10.87h** on a level schedule of
  the same durations. Both are lower bounds, since they hold each unit's duration fixed. A
  second intent points the same way (`team-plan-surfaces`, ~3.3–3.7h → ~2.3–2.7h) but does
  **not** reproduce to a stable figure: the per-unit windows are recovered by regex-tagging
  agent descriptions on `\bu[1-7]\b`, and 48% of agents carry no unit tag at all — whole
  review batteries are named by PR number (`973 lens:`, `Review 971 …`). Intent A's tagging is
  clean; quote A, treat D as corroboration only. Nothing was choosing this: 12 of 14 implementer dispatches across
  four intents never overlapped another implementer at all, and the wide dispatch bursts
  (mean width 2.20 over 80 bursts, up to 10) are **all** spec authoring, refute passes and
  review lenses. Phase 1 now schedules by level, capped at 2, with migration-authoring and
  file-overlapping siblings serialized — the exclusions matter, and u4's own spec states the
  first one: its `after: [u1]` is a journal `when` dependency, not a code one. The
  file-overlap grep had to be **rooted at a source directory and stripped of `.md`** before it
  meant anything: the loose form matched `CLAUDE.md`, the umbrella docs and every `index.ts`,
  and collided all three L1 siblings — a rule that would have serialized everything while
  reading like a check. Rooted, it clears u2↔u3 and u3↔u4 and flags u2↔u4 on `billing.ts`,
  `PricingContent.tsx`, `TermosAssinatura.tsx` — the same handoff u4's plan declares in prose
  under a *Handoff* heading, found independently.

  **The fix-cycle counter overcounts, and would hard-stop a resumable unit.** Phase 0 step 7
  recovered cycles with `grep -c 'fix-attempt-'`, but one cycle routinely lands several
  commits — §3.2 mandates exactly that. Measured: u4 / u7 / u6 read **7 / 5 / 6** against true
  counts of **2 / 1 / 1**, every one past the cap of 3, so resuming any of them would have
  killed a unit with cycles left. This is the `fix-attempt-4` incident (#829) inverted — that
  fix closed an undercount across a resume and installed an overcount within one. `fix-attempt-N`
  carries its own number, so the counter is now **max N**, which is exact. `fix(review):` has no
  number (`code-review.md` fixes the literal prefix, and a standalone `/code-review apply` has
  no ADW cycle to name), so its commit count is an upper bound and the authoritative count is
  the PR's review submissions, which §3.6 already fetches.

  **The Sonnet-implementer pilot was arithmetically inverted.** It compared **raw token counts
  across tiers** — the exact error §8 exists to correct — and concluded Sonnet "cost more".
  Price-weighted and normalized by diff churn: **5,091** sonnet-equivalents per changed line
  against an Opus range of **7,588–20,775** (median 10,234) over 13 implementers, i.e. below
  the entire Opus range. The quality signal stays unresolved — u4's PR carried the most
  remediation commits of any of the 14 (8) and u4 had the thinnest *spec* of its intent (208
  lines vs 239–296) — so §8 gates the author/implementer tier on the unit's **`depth:`**
  rather than switching wholesale, and deliberately keeps D3 (the depth the one measurement
  was taken at) on Opus. The "thinnest plan" half of that confound was **false** and is
  retracted: u4's plan is 283 lines, u6's is 248. `note tier` and the PR evidence block's
  `tier` row exist so the next answer is a sample.

  **The compaction threshold is now absolute.** ~1,012 orchestrator calls, mean window
  411,748, p50 403,177, peak **801,247**. Every call re-reads the whole window, so the spend
  is the integral of window size over calls and has nothing to do with remaining headroom:
  holding 400k would have cut ~80M cache-read tokens, **3.9%** of the run; 300k, **6.8%**.
  adw-core §7's `note window` fires at **≥400k** and reports `<N>k`, not `<N>%` — 60% of a 1M
  model was 600k, past the point worth acting on.

  A companion claim — *the orchestrator's context is not filled by tool output, since all tool
  RESULTS total only ~0.3M tokens* — is **withdrawn as a non-sequitur**, even though the
  measurement was right. It never checked the two comparable terms on the other side of the
  ledger: `Agent` dispatch prompts alone run ~741K characters (~185K tokens) of tool_use
  *input*, Bash commands another ~100K, and thinking content is stored redacted (`"thinking":
  ""`) while still metering. Ruling out one candidate is not identifying the cause. The 400k
  rule does not depend on this and stands on the integral argument alone.

  **Method — and the first defect a refuter structurally could not have caught.** Dedup by
  `message.id`, keep the last record, before summing anything. v2.14's refute pass verified
  *derivations*, and every claim it saw was internally consistent with an inflated base, so
  the counting defect was invisible to it; it surfaced from a self-review that started at "675
  text-only orchestrator turns is implausible" and interrogated the record structure instead
  of the arithmetic. **Refute the method separately from the numbers.** That pass then caught
  three more of this entry's own claims before publication: "zero implementer overlap" (one
  pair, 15 min), a 40%/32% DAG saving quoted against actual makespan (which includes owner
  gates and DarkWake — not the schedule's to save), and the file-overlap grep being a no-op.
  A fresh `sonnet` refuter on the corrected set then caught three more: the first-vs-last
  record rule above, `premium-set-reshape` as the post-rule control that kills §8's cost
  attribution, and the false "thinnest plan" confound. Two rounds, six material corrections,
  and the direction of every applied change survived all of them.

  **Caveats that apply to every total above, none of which a percentage hides.** (1) The
  session was **still live** while being measured — it grew during the refute pass, which
  observed its own dispatch appear in the transcript. Quote the snapshot time or the number
  will not reproduce. (2) `team-plan-surfaces` was spec'd for **4** units and 3 were built;
  u4's authoring cost sits in the numerator of every per-unit figure for D while u4 sits in no
  denominator. (3) `comp-and-trial-rollout` fused u1+u2 into one PR built by one agent, so
  "per unit" is not a constant measure across intents. All three push the per-unit comparisons
  toward *suggestive*, which is the weight the depth-gate change is built to carry.

- **v2.16 (2026-09-05)** — ergonomics, prompted by the first run by someone who did not
  write the pipeline. Four defects, one of them a real bug.

  **The bug: `approve & build` never once chained.** It was specified in `/adw-init`
  Phase 2 and restated in `adw-core` §7, and executed nowhere. `/adw-init`'s terminal
  phase said only "Print S2 exactly … The report is the whole message", and S2's own first
  line was `Next: /adw-build <slug>` — two stop instructions at the cursor against one
  rule 180 lines above it. The observed run printed S2, wrote "Continuing into the build.",
  and ended the turn. **The lesson generalises past this bug: a behaviour stated only in a
  section the model has already walked past does not bind at the moment of execution.**
  The fix is placement, not emphasis — Phase 5 is now three ordered steps and the chaining
  is step 3, in the phase where the run actually ends.

  **`approve` now builds; `specs only` is the old stopping verb.** Making the chain opt-in
  behind a third verb solved nothing for a first-time user, who has to be told the verb
  exists. What moves with the rename is consent: `approve` used to buy the cut, and design
  §6 collected consent for the code when the human invoked build. Nothing stands there
  now. The merge carve-out (`adw-core` §6) is unchanged — sub-PRs still merge only into
  the intent's integration branch — but the approval surface must say what the verb does
  (`approve → cut + build`), and hazards had to leave the hidden zone (below). The clean-exit
  gate is kept: a non-empty `needs you` stops the run exactly as `specs only` would.

  **The approval surface is brief by default.** `detail` and `fyi` no longer print; a
  `detail` verb re-renders with them. The two-tier scan/skip split introduced pre-v2.8 was
  the same intent and did not carry — an unfamiliar reader does not know which zones are
  skippable. This forced a split that should have existed anyway: `fyi` was carrying
  gate-visibility gaps, shared-file hazards and uncharted territory alongside settled
  decisions, so brief mode would have hidden exactly the lines that matter most now that
  `approve` builds. Hazards are `⚠` lines (always printed), settled decisions are `fyi`
  (hidden). The split is decided when the line is written, not at render.

  **`/adw-build <unknown-slug>` routes to `/adw-init` instead of stopping.** The observed
  failure was a user typing the command that names what they want and getting a list of
  slugs they had never seen. Resolution checks three sources, not one — specs stay
  uncommitted in the main tree, so an empty local grep is not evidence of a new intent when
  the specs live on `adw/<slug>-u1` or in another worktree. A near-match prints
  `did you mean` and stops; only a genuine miss inits.

  **Codes renamed for people who did not write the pipeline.** `S1`–`S4` → `approval` /
  `handoff` / `run report` / `PR body`: the codes never rendered, so they cost the ~95
  cross-references in four files and bought nothing. Depth `D0`–`D3` gains the word each
  one already implied — `express` / `spec` / `plan` / `design`, naming the deepest artifact
  it produces. Surfaces print the word, the contract and the spec header keep the code
  (the specs on disk carry `depth: D<N>`), and the `depth` verb takes either. This is not a
  new convention: D0 has rendered as `express` since it went active. `u1` is unchanged —
  it is embedded in branch names, PR titles and spec filenames, and already reads as
  "unit 1".

  **Known cost, accepted.** Build no longer starts on a fresh context window. The
  `subscription-locks` run compacted 8 times, and adw-build's session-boundary rule turns a
  mid-chain compaction into a halt with a `ready` sub-PR left human-owned. There is no
  clean fix — orchestration cannot move to a subagent (§4.9). The partial mitigation is in
  Phase 5 step 3: enter build with the spec bodies out of context, since build's Phase 0
  reads every spec from disk anyway. Watch the `note window <N>k` line on chained runs; if
  compaction rate rises materially, the answer is to make `specs only` the default again,
  not to add a budget system.

- **v2.17 (2026-09-09)** — depth recalibration and contract slimming, owner-driven after
  the `admin-user-contact-fields` build (PRs #1207/#1208) was correctly taken OUT of ADW
  by hand. Full measurement and reasoning in **§3.6**; the operational changes:
  - **`api/` and `packages/` stop being trap domains.** They were path prefixes on the D1
    negative list and, on a full-stack monorepo, matched nearly every unit — 208 of 245
    specs landed D2/D3 and `express` fired 3 times ever. Replaced by three new grep rows
    naming the `api/` risks the original set missed: `soft delete`
    (`notDeleted|deletedAt`), `transactions` (`db\.transaction|\btx\.`) and `live sync`
    (`pg_notify|fetchEventSource|useSSE`). `api/drizzle/` survives as the one path prefix,
    because migrations genuinely are path-shaped. The trap list is now a table in
    adw-core §3 rather than prose, so both sides read one source.
  - **The D1 file bound moves from "≤2 source files in one feature directory" to "≤4".**
    The old bound could not express shared schema + handler + consumer + test, which is the
    normal shape of a small full-stack unit.
  - **D2 stops producing a separate plan file.** Its plan becomes a mandatory
    `## Implementation` section inside its own spec. D2 keeps the word `plan`; a plan
    *file* is now D3 only. Motivating evidence: 225 plan files / 86,430 lines in one
    two-month window, ~2.4× spec-to-plan on committed pairs, and — decisively — the D2
    plan was the only artifact in the system no critical pass ever read. Guard rail for a
    D2 spec is 250 (hard stop 500), the inherited 200/300 pair collapsed; adw-init Phase 3
    now carries the budget as a per-depth table.
  - **~90% of the run history in the three ADW command files was already duplicated here**
    (evidence-token overlap: adw-core 28/31, adw-init 27/29, adw-build 38/43), while
    51–61% of those files' lines sat in paragraphs carrying it. Those paragraphs are being
    reduced to one rule sentence plus a `design §10 vN.N` pointer — the repo's own comment
    rule (CLAUDE.md §4) applied to the contract. Rules are NOT moved: a rule has to sit at
    the point of execution, so only the narrative moves, and this file stays the home for
    it exactly as the adw-core preamble already claimed.
  - **Explicitly not changed: the do-side.** Gates, the mutation check, the refute passes
    and the `/code-review` loop are untouched. The same worked example that argued against
    the documents argued for those — both bugs it caught came from the mutation check and
    a review agent. Nothing here authorises thinning verification.

- **v2.17a (2026-09-09)** — follow-up to v2.17, same session: the three `superpowers` skills
  ADW dispatches were read line-by-line for the first time rather than assumed. Three
  conflicts, all live, none previously recorded:
  - **`writing-plans` mandates a plan header naming a sub-skill ADW never uses** —
    `superpowers:subagent-driven-development` / `executing-plans`. adw-build §3.1 dispatches
    its own implementer and keeps it across fix cycles. **186 of 230 plan files on disk
    carry the false instruction**, merged into `develop` inside their unit PRs. adw-init
    Phase 3 now overrides the line. O2 removes the exposure at D2 outright (no plan file);
    D3 keeps a plan and needs the override.
  - **`writing-plans` hardcodes a different plan path** (`YYYY-MM-DD-<feature-name>.md`, no
    slug, no unit). Its own text permits the override; the prompt now states it.
  - **`brainstorming` carries a `<HARD-GATE>` requiring human approval before any
    implementation action**, which a fan-out subagent cannot satisfy. The approval surface
    already passed that gate for the whole cut. The prompt now says so, and pins that §3's
    depth wins over brainstorming's own spike/bounded/architectural classifier — two
    ladders that can disagree.
  - **`systematic-debugging` has no conflict** and is not touched. It is 283 lines of
    diagnosis discipline with no path assumptions and no human gate. An earlier proposal in
    this session to vendor a ~30-line summary of it is withdrawn: at D1 the diagnosis *is*
    the deliverable, so compressing it is thinning verification, which v2.17 explicitly
    forbids.
  - **`/code-review` and `review-core` were audited and left alone.** History density is
    15%/21% against the ADW files' 51–61%, shared machinery is already extracted to
    `review-core.md`, and the Phase-4b plugin gate already refuses to fire on a docs-only
    diff — the same "do not run the heavy thing where it cannot help" rule v2.17 applies to
    depth. Nothing to fix.
  - Contract slimming extended into `adw-build.md` (Phase 0 pinning, progress conditions 4
    and 6, the mutation-check block, the evidence block, the `/code-review` and
    composition-review rules). Every rule verified present after the edit; only narrative
    already in this file was removed.
  - **`00-design.md`'s own revision history is repaired here** — a second `v2.13`
    (2026-08-02) and a second `v2.14` (2026-08-15) collided with an earlier pair of the same
    names. Renumbered `v2.12.1` / `v2.12.2` by date, entries sorted into version order, and
    every citation in the command files re-pointed and verified to resolve to exactly one
    entry.

- **v2.17b (2026-09-09)** — artifact root moves to **`docs/adw/`**, owner-requested in the
  same session as v2.17/v2.17a. `docs/superpowers/` was wrong twice over: it names a plugin
  ADW merely *calls* rather than the system that owns the files, and its `specs/` mixes ADW
  output with pre-ADW hand-authored design docs and sits beside hand-authored umbrellas
  (`billing/`, `prototype-port/`, `landing-port/`, `mapa-cirurgico/`, `invite-flow-*`,
  `app-subdomain-split/`) that ADW never produced. `docs/adw/` already held this file, so
  the specs and plans now sit next to their own contract's rationale.
  - Every new intent is born under `docs/adw/specs/` and `docs/adw/plans/`.
    `docs/adw/README.md` states the layout and the legacy rule.
  - **Nothing was migrated, deliberately.** 757 tracked files under `docs/superpowers/`,
    cross-referenced from 309 other files and from merged PR bodies; and the directory is
    not ADW's to empty. Moving them would break every citation to buy tidiness in a
    directory nobody reads twice.
  - **`docs/superpowers/` is frozen, not forbidden.** Nothing already there is moved,
    renamed or rewritten, and no new intent is born there — but an intent that already lives
    there keeps writing its later units there, because one intent never straddles two roots.
    Every path-resolving read checks BOTH roots, `docs/adw/` first — extend (§1.1), resume
    (§5), `/adw-build` Phase 0 step 3 — and the root that answers is the root that unit
    writes to. A slug resolving in both is the same refusal as two dated folders for one slug.
    v2.17d sharpened this from the flat "read-only, never written again" it shipped as, which
    contradicted "later units included" in the same paragraph.
  - Code-diff exclusions widened to `':!docs/adw/**' ':!docs/superpowers/**'` in adw-build
    §3.5 and `/pr-ready` §2, so contract artifacts still score as documents, not code.
    `/spec-review`'s scope gained both `docs/adw/` globs.

- **v2.17c (2026-09-09)** — refute pass on v2.17's own PR (#1211), which found three defects
  in it. Recorded because two of the three were exactly the class v2.17 claimed to have
  verified against:
  - **`adw-init` Phase 0.5's spec-folder recovery queried only the new root** while a
    trailing comment claimed it also checked the legacy one. Extending any pre-cutover
    intent would have found nothing and minted a duplicate dated folder — the one thing
    §1.1 calls a bug rather than a choice. Now a loop over both roots that reports which
    answered, refuses two hits, and treats zero hits as a new intent.
  - **This file contradicted its own new §3.6 in three untouched places** — the §3.3
    fan-out diagram, §4.2's "follows the unit's plan where one exists (D2+)", and §6's S2
    worked example — all still describing D2 as producing a separate plan artifact. The
    command files were updated and the design doc was not, which is the drift the opening
    line of `adw-core.md` exists to forbid. Fixed.
  - **The `soft delete` trap row was measured and removed** (see §3.6). The lesson is the
    generalised rule now recorded there: measure a candidate row against real diffs first.
  - Also fixed from the parallel pass on #1209: `sync-agent-contract.sh` said "five files"
    over a seven-file array and told a new repo the profile spans `§1-§12` when it spans
    `§1-§18`; `push` clobbered a target with uncommitted work under `.claude/` and now
    refuses; `CROSS-REPO.md` undercounted the synced set as six files and the profile as
    `§1–§17`; and two proper nouns (`release/mapa-cirurgico`, a literal Plantoes-app path)
    were still sitting in files that PR declares byte-identical across repos.

- **v2.17d (2026-09-09)** — rebased onto the repo-agnostic contract (#1209) and moved two
  values out of the contract files into the profile, where the whole point of #1209 says they
  belong:
  - **The artifact roots** are `repo-profile §2`'s `specs dir` / `plans dir`, joined by
    `legacy specs dir` / `legacy plans dir`. `adw-core §1` now states the legacy-root RULE
    (read-only, never migrated, every path-resolving read checks both, one intent never
    straddles two) in terms of those placeholders; the values are the profile's. A repo that
    declares no legacy root has one root and drops the second path everywhere.
  - **The trap-domain table** is `repo-profile §11`. `adw-core §3` keeps only what generalises:
    a trap domain is a grep over the diff, never a directory (the `api/`/`packages/` collapse),
    and a candidate row is measured against real diffs before it is added, with a gate that
    executes preferred over a rung on the ladder (the soft-delete measurement). `pg_notify`,
    `db.transaction` and `formatMoney` are Plantoes-app nouns and mean nothing in another repo.
  - Also folded in: the Phase 4 validation bullets that enforce v2.17's D2 shape (a D3 unit
    has a plan file, D0/D1/D2 do not, and a D2 spec carries `## Implementation`) now sit in
    the repo-agnostic `adw-init` Phase 4 list.

  **Refute pass on the resolution itself** (fresh `sonnet`, read-only, prompted to refute)
  found the defects below. Several were inherited from v2.17 rather than introduced by the
  rebase, which is the point of running the pass on the merge and not only on the branch:
  - **The legacy root was described as "read-only, never written to again" two lines above
    "later units included"** — in `adw-core §1`, `repo-profile §2`, `docs/adw/README.md` and
    this file. Both readings ship: one agent refuses to extend a legacy-rooted intent, another
    writes there. Restated as **frozen, not forbidden**, with the three cases separated.
  - **`release/mapa-cirurgico` and a literal `develop`** were still in `adw-build.md`, which
    #1209 declares byte-identical across repos — the same class v2.17c above claims to have
    swept, in a paragraph that used `<default base>` correctly on its very next line.
  - **`api/` and `packages/` were named as literals** in the new `adw-core §3` rule. The rule
    generalises; the two directory names do not. They stay in `repo-profile §11`.
  - **`adw-core §8` cited `design §8`** — which is `## 8. Kill criteria`, about abandoning the
    pipeline, not about tier cost attribution. Both citations now read `design §10 v2.15`.
  - **`pr-ready.md` still said D2's plan is not critical-passed**, describing the artifact
    shape v2.17 deleted. It was the one contract file the rebase produced no diff for, which is
    exactly why nothing flagged it.
  - Three stale spots in this file that the v2.17c sweep missed: §1's objective and §5.1's
    artifact-ratio row still named `docs/superpowers/`, and §3.2's ladder table still ended D2
    on a separate `plan` stage.
  - The `repo-profile.md` header listed five contract files where the synced set is seven.

  The generalisable lesson, and the second time this run has paid for it: **a sweep that fixes
  a class in the files it is already editing does not fix the class.** v2.17c recorded fixing
  the proper-noun leak and the five-vs-seven undercount; both survived in files that sweep did
  not open. Grep the class repo-wide, not the diff.
