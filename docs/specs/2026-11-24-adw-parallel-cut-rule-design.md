# Parallel units: registry overlap vs semantic overlap — design

Date: 2026-11-24. Status: proposed; the owner merges the PR that carries it.

## Intent and why

A real run in a Kotlin Multiplatform mobile repo cut four units: `u4` independent, then a serial
chain `u5 → u6 → u7` on an integration branch. The owner asked afterwards: "these conflicts don't
seem to be a blocker for the value of implementing twice as fast, and for the ones that touch the
same things shouldn't they be in the same units?"

The facts behind the question:

- `u5` (140-line spec), `u6` (104) and `u7` (89) all touch one new helper that words a payment
  line; `u6` and `u7` consume what `u5` builds. That is a **semantic** overlap: shared new code.
- `u4` and `u5` both edit one parity manifest (a TSV) and the per-host ratchet ceilings in one
  Kotlin file (counts that may only go down). That is a **registry** overlap: shared manifest and
  count files, mechanical.
- An earlier PR of the same intent hit a three-file registry conflict after its sibling merged. One
  merge of the base into the branch, with the ceilings recounted from the real rows, fixed it in
  one pass.
- The host runs one gradle or `xcodebuild` gate at a time (shared gradle locks, shared DerivedData,
  one simulator). Coding in separate worktrees has no such limit; only the gates do.

Today's contract chains the first case and serializes the second: adw-core §4 says units that
touch the same file MUST share a PR, and adw-build Phase 1 serializes level siblings whose plans
name one file. Both rules treat a manifest row like a function body.

## Decided by the owner

- Registry-file conflicts are not a blocker next to the value of coding units in parallel.
- Units that share new code are one unit, not a chain.

## Goals

1. Units that share only registry files code in parallel, and the merge settles the files.
2. Units that share new code are one unit; past a size guard, a producer unit and consumers that
   fan out in parallel after it.
3. No unit hand-writes a count that a command can derive.
4. Gates stay one at a time on a host whose gates share state. Coding does not wait for them.

## Non-goals

- No lock file, lock script or `flock`. The orchestrator orders the gate runs (adw-build Phase 1).
- No change to D-depth criteria, the review tiers, `/pr-ready`, the merge gate's conditions or its
  script.
- The consuming repo's Regenerate script is that repo's work, in its own PR.

## Anti-goals

- A ratchet that goes up because a script recounted it.
- A conflict outside registry paths settled without the owner.
- A head that merges with no pass at its exact sha.

## The rule

### Q1 — the cut rule (adw-core §4.1, adw-init Phase 1 item 3)

**Registry path:** a path `repo-profile §24` lists (new, optional). **Overlap:** two units' file
lists share a path, or one unit's change uses a name the other creates or changes.

| Overlap | Test | Cut |
|---|---|---|
| registry | every shared path is a registry path, and neither uses a name the other creates or changes | no `after:` edge, no shared PR; parallel |
| semantic | anything else: a non-registry shared path, or one uses a symbol, helper, wording or projection field the other creates or changes | one unit, not a chain; past §4.2, producer + consumers `after: [<producer>]` |

How the cutter tells them apart, from file lists (adw-core §4.1, "Telling them apart"):

1. Intersect the two units' file lists: triage's expected files, or after the fan-out the paths in
   the spec's `## Implementation` table or plan.
2. Drop every path a §24 glob matches. No §24 → drop nothing (today's behaviour).
3. Nothing left and no created name crosses → registry. Otherwise → semantic.

**Unsure is semantic.** A missing file list, a name that could be either, one manifest row both
might change. The cost of a wrong "semantic" is lost parallelism; the cost of a wrong "registry"
is caught at the merge, where Regenerate refuses a row changed on both sides and the merge stops
as any conflict does.

adw-core §4's first MUST bullet becomes "the same file or function, a registry path (§4.1)
excepted"; its MAY clause "no shared files (registry paths excepted, §4.1)". Triage item 3 now lists
each unit's expected files and production-file count and classifies every overlapping pair. Item 6
marks a registry overlap as `fyi`, not a `⚠` hazard: nothing about it is the owner's to act on.

### Q2 — packaging and `after:` (adw-core §2, §4.1, §1.1)

- `after:` names a unit whose output this unit uses, or a migration order. **A registry overlap
  alone is never an `after:` edge** (adw-core §2 rules).
- Registry-overlapping units that would be two independent PRs go on **one chain level** instead.
  Reason: an independent PR merges into a base, so the run never moves its head after `ready` (a
  moved head voids its walk and screenshots, adw-build §3.8). Two such PRs with conflicting registry
  files would wait for the owner at the second merge. As sub-PRs, the second one's merge is
  automated (Q3). An independent unit beside a chain stays independent: chain close settles the
  file (adw-build Phase 4).
- Semantic overlap with shared new code: one unit. Split by §4.2: producer sub-PR on one level,
  consumers as siblings on the next. They chain because consumers consume (adw-core §4).
- **Extend mode** (adw-core §1.1, §4.1; adw-init extend prompt): a unit's scope is its semantic
  overlap. Semantic with an UNBUILT unit → amend it (that is "one unit"). Semantic with an OPEN-PR
  unit → a new consumer unit, `after: [<that unit>]`; the open PR is never amended. Semantic with a
  MERGED unit → a new unit citing it. Registry overlap with any prior unit → case (d), a new unit
  with no `after:` on it. New ids continue from `max + 1` as today.
- **The registry sync is not an amend.** It changes no spec and no scope, and it runs only at a
  merge the run may already make (adw-core §6). A PR the owner holds (`adw:hold`, `merge: hold`)
  is never merged by the run, so never synced either.

### Q3 — derived counts (repo-profile §24, adw-build §3.1, §3.7, Phase 4)

Yes, counts can be derived, and the profile must say how. New optional `repo-profile §24 —
Registry files`, three rows:

- **Paths** — pathspec globs of files whose every line is a row or a count Regenerate owns. Never
  a §7 gate file.
- **Regenerate** — one command: rewrites every count from the rows; inside a stopped merge, first
  settles conflicted registry files row by row (per key, the side that changed it from the merge
  base; same key on both sides → non-zero). **A ceiling only goes down:** it writes the lowest of
  the recount and every value the file holds, so a unit that adds a baseline row stays red. Files
  only: no build, no test, so it needs no gate slot.
- **Check** — the §5 gate that reds when a registry file disagrees with its sources. It runs after
  every resolution, obligated or not.

Where it is used:

- **Implementer** (adw-build §3.1): never writes a count by hand, even if the spec says to; runs
  Regenerate after its last edit and before each gate run, and commits the result with its work.
- **Sub-PR merge** (adw-build §3.7, step 0 and "The registry sync"): the overlap test classifies
  the base's new commits against the PR. Registry-only → tree, `git merge --no-commit`, the
  registry resolution block (Regenerate, then three proofs: no conflict outside registry paths, no
  marker left, nothing changed outside registry paths), push. The head moved, so the PR runs §3.4
  and §3.6 again with fresh counters (`/pr-ready` §6, as after a smoke fix), Check included. At most
  two syncs per PR. Any `stop` halts the chain `blocked` with a default the owner can run.
- **Merge gate**, independent or final PR (adw-build §3.7 step 2): a registry-only `hold 6 overlap`
  builds the merge-result tree, runs the gates plus Check, and merges with no re-review when green.
  A registry conflict holds for the owner, with a default that names Regenerate.
- **Owner's word** ((c), (d)): registry files leave the overlap re-review list; a registry-only
  conflict's default names the mechanical fix.
- **Chain close** (adw-build Phase 4): a sync that conflicts only in registry paths takes the
  merge path with the resolution, then the final PR's full loop. Anything else is judgement work, as
  today.
- adw-build's "Never" list: "resolve a sync conflict unattended" gains the registry exception.

A repo can avoid the stored ceiling entirely: have the ratchet test compare its count with the
base's count. Then only the manifests are registry paths, and the count files never conflict.

### Q4 — host constraint (adw-build Phase 1)

"The orchestrator is the lock" becomes run-wide:

- Where `repo-profile §10` says gates share state, **one gate-running agent across the whole run**,
  independent units and chain siblings alike (it was written for level siblings only).
- Every implementer brief written while another unit is in flight says `implement, commit, then
  return before you run any gate`, and the unit's `verify` counts as a gate there (it builds).
  Without the slot, an implementer only reads and writes code.
- **Order:** first a unit another unit's `after:` names that has not merged (a producer: its merge
  starts the next level), then first come, first served. An agent holds the slot from its dispatch
  or resume to its return; a fix cycle queues again, last.
- **Shared DerivedData, gradle locks, simulator:** one slot means one build; the run adds nothing
  else. A §10 remedy that resets a shared resource (`./gradlew --stop`, deleting DerivedData) runs
  only while no agent holds the slot. Phase 5's cleanup already removes the DerivedData of the run's
  worktrees.
- The file-overlap sibling check drops registry paths (`git ls-files -- <globs>`), so a registry
  overlap never serializes two siblings.
- The level cap of 2 concurrent units stays.

### Q5 — size guard (adw-core §4.2)

A unit cut as one under §4.1 stays one while it is expected to change **at most 8 production
files** and its spec stays under its depth's **hard stop** (adw-init Phase 3).

- 8, because adw-build §3.2's per-file mutation sweep checks at most 8 files. Past 8, some file
  loses its own red-on-revert check, and the merged unit is no longer fully verifiable.
- Triage applies the file bound (it already counts production files for D1). The author meets the
  hard stop, and its existing split question now defaults to the seam split.

**A seam** is one new thing (symbol, helper, wording, projection field) whose definition and tests
sit on one side and only its uses on the other. Producer = the definition side. Each set of uses
with its own files = one consumer, `after: [<producer>]`. A cut at a seam leaves no path in two
units except registry paths. No seam → the unit stays whole and its size is reported as today.
§3's D1 criteria judge the merged unit whole, so merged D1 parts past 4 production files are D2.

### Q6 — per-file changes

| File | Section | Change |
|---|---|---|
| `commands/adw-core.md` | header | §24 joins the optional anchors |
| | §1.1 | scope = semantic overlap; the registry sync is not an amend |
| | §2 rules | what `after:` names; never a registry overlap alone |
| | §4 | registry carve-out on MUST and MAY |
| | §4.1 (new) | overlap table, the three-step test, unsure → semantic, extend mode |
| | §4.2 (new) | size guard, seam |
| | §6 | a registry sync that stops is a chain stop |
| `commands/adw-init.md` | Phase 1 item 3, item 6 | file lists, classification, one unit, seam split; registry = fyi |
| | extend prompt | scope = semantic; registry-only → (d) |
| | Phase 3 artifact budget | the split question's default is the seam split |
| `commands/adw-build.md` | Never list | registry exception to "resolve a sync conflict unattended" |
| | Phase 1 | registry paths drop out of the overlap check; run-wide slot, order, shared state; sibling-merge exception |
| | §3.1 | implementer runs Regenerate, never hand-writes a count |
| | §3.7 | sub-PR step 0; the registry sync (overlap test, resolution, sub-PR sync); merge gate step 2/3; owner's word (c), (d) |
| | Phase 4 | registry-only close conflict takes the resolution |
| `docs/repo-profile-EXAMPLE.md` | header, table, §24 (new) | the §24 sketch |
| `README.md`, `docs/00-design.md` §3.5 | | anchor lists; one paragraph pointing here |

Kept coherent with: extend-mode ids (unchanged), open-PR units never amended (the sync is not an
amend, and runs only where the run may merge), D-depth (criteria judge a merged unit whole), the
§3.7 merge gate (conditions and script unchanged; step 2 gains one branch), protected files (a §7
gate file can never be a registry path; merge-protected paths still hold at condition 4).

## Adopting it by hand in a run already in flight

State of the run that prompted this, read-only: `u4` has an open PR; the integration branch is
open; `u5`, `u6`, `u7` have no PR yet.

Safe now, before this PR merges:

1. **Gate order.** Already contract (one gate at a time, the orchestrator orders). Nothing to do.
2. **`u4` beside `u5`.** Let both build. Whichever merges second gets the registry conflict; settle
   it as the earlier PR was: merge the base into its branch, recount the ceilings from the rows
   (they only go down), then `/pr-ready` and one review cycle. This is the registry sync done by
   hand. For `u4`, an independent PR, the walk runs again too.
3. **Fan out `u6` and `u7`.** If `u7` uses only what `u5` creates (not what `u6` creates), change
   `u7`'s `after: [u6]` to `after: [u5]`. Both then build as siblings after `u5`. Safe only while
   neither has started building: it is an amend of an unbuilt spec, so the owner approves it.

Not safe in flight:

- **Merging `u5`–`u7` into one unit.** `u5` is building; merging now discards its run, and the
  contract has no verb that retires two unit ids. Take step 3 instead.
- **Automated registry syncs.** They need a §24 and a Regenerate script, which the repo does not
  have yet.

## Expected effect

On a cut like `u4..u7`: `u4` and `u5` code at once; `u6` and `u7` code at once after `u5` merges.
Coding wall-clock goes from four serial units to two rounds of two. Gate time does not shrink (the
host still runs one gate at a time), but coding overlaps it. Each registry sync costs one re-pass
and one review cycle on the PR that merges second.

## Left out

- A review exemption for a registry-only sync. It would save the review cycle, but `/pr-ready` §5
  dates the review against the last code commit and a merge commit is one; exempting it safely
  needs §5 and §6 to recognise the sync. Measure syncs first.
- Syncing an independent PR by the run. It would void the walk and screenshots; the cut rule avoids
  the case instead.
- A run-report line per sync. The `chore(registry): sync` commit on the PR is the record.
- The consuming repo's §24 and Regenerate script, as its own PR.
