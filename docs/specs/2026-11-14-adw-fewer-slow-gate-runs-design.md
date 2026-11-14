# Fewer slow gate runs per unit — design

Date: 2026-11-14. Status: approved by the owner in chat; revised after a critical review (the first
draft moved the independent pass after review; that reorder broke the fix-cycle path, so this
version keeps the order).

## Intent and why

A small ADW unit (under ~300 changed lines) spends 6–8 minutes writing code and 35–75 minutes in
the build stage. Measured over 30 days of runs in two consuming repos:

- The same full gate suite runs three or more times per unit: the implementer's gates (§3.2), the
  pre-PR independence pass (§3.4, `PASS=v1`), the review driver's re-pass (`/pr-ready` §4 inside
  §3.6, `PASS=v2`), and `/code-review apply`'s own gate run before each push (`review-core.md` §4).
- In a mobile repo, one gate (a simulator test suite) takes 10–16 minutes per run. Small units
  whose diff obligates it have a 74-minute median build stage; small units that do not, 44.
- Across ~500 verifier runs, the re-runs found about 10 real defects the implementer's run did not
  report. About 6 were fast style gates. The 3–4 test failures came after the code changed: a
  review fix, a sync with the base, or units composed into a final PR. Re-running the slow suite
  on an unchanged tree found nothing real; its other reds were flakes, sandbox faults, or gates
  already red at the base.
- 20 of 52 small PRs received a commit after the PR opened. In the other 32, `v1` and `v2` ran on
  the same tree.

So an independent pass earns its cost on a tree no pass has seen. A second pass on the same tree
does not, and an implementer-side run of a slow gate duplicates the pass that follows it.

## Goals

1. **No second independent pass on an unchanged head.** When the head the driver would verify
   equals the `$VSHA` of the previous pass of the same unit, the earlier pass stands: its gate
   table, mutation rows and render-grade rows are reused, `verified <sha7>` is that `$VSHA`, and
   `/pr-ready` §4 does not re-execute. A head that moved by any commit still gets a full pass
   (`/pr-ready` §6's void rule is unchanged for a moved head).
2. **Slow gates run where they count.** `repo-profile §5` may mark a gate as slow (the builder
   names the marker). Two roles skip a marked gate: the §3.2 implementer, and `/code-review apply`
   before a push. Every other gate runner runs it: the independent pass, the merge gate's trial
   agent, the §3.3 relay, a §3.8 smoke fix agent's follow-up verify. Exception: in a fix cycle
   started by a marked gate's red, the implementer runs that gate to confirm its fix.
3. **A base red is proven once per unit.** A pass that finds a marked gate red at `$BASE` with the
   same ids hands that result to the next pass of the same unit as its known base red, so the next
   pass does not run the slow gate at `$BASE` again (§3.3's existing "known baseline red" line).

## Non-goals

- No change to the order: implementer → pre-PR pass → PR → review → re-pass. The PR still opens
  only after an independent pass.
- No change to which gates a diff obligates (`repo-profile §6`), review tiers, §3.8's walk, or
  the merge gate's conditions.
- No selective test running inside a gate.
- Making each consuming repo's base branch green is separate work in those repos.

## Anti-goals

- A head reaches `ready` or merges without an independent pass at that exact SHA.
- A reused pass is reused for a head it did not check (the comparison must be the literal `$VSHA`
  against `git rev-parse origin/<head>` after a fetch, never reasoning about what changed).
- A marked gate is skipped by a role this design does not name, so it runs nowhere.
- `/pr-ready` used on its own (not from adw-build) changes behaviour: with no prior pass handed
  in, it runs §4 as today.

## Expected effect

- Review pushed nothing (32 of 52): slow gate runs per unit go from 3 to 1 (the pre-PR pass).
- Review pushed: from 3–4 to 2 (pre-PR pass and re-pass).
- Small units that obligate a slow gate: build-stage median from ~74 toward ~40 minutes.

## Constraints

- adw is a public repo: no app names, consuming-repo PR numbers, local paths or spend.
- Contract prose is executed literally by a cheap model. Every site that states a changed rule must
  agree: `commands/adw-build.md` (§3.2, §3.3, §3.4, §3.6, §3.7 merge-gate trial, §3.8 smoke fix,
  Phase 4), `commands/pr-ready.md` (§1 parameters, §4, §6, §7), `commands/review-core.md` §4,
  `commands/code-review.md` where it states the pre-push gate run, `commands/adw-core.md`,
  `docs/00-design.md`, `docs/repo-profile-EXAMPLE.md`, `README.md`.
- An implementer report that marks a gate `skipped: slow` is not "a report missing an obligated
  gate's row" (that rule is for the verifier's report). Say so where that rule is stated.
- `scripts/adw_analyze` parses the evidence block's `phases` row; a reused pass must leave old and
  new bodies parseable and `python3 -m unittest` in `scripts/` green.
- `scripts/adw-merge-gate.py` must still find the `verified` row and the head equality it checks.

## Left to the builder

- The marker syntax in `repo-profile §5`, and the example profile's rule for when to mark a gate
  (usual run of several minutes; the unit's `verify` command covers what the implementer needs).
- How the driver brief carries the prior pass (its `$VSHA` literal and rows) and how the driver's
  return and the evidence block show a reused pass (for example `reverify reused v1`).
- The consuming repos' own profile edits (which gates to mark), as separate small PRs in those
  repos, chosen from measured gate durations.

## As built

- The marker is `[slow]` at the start of a gate's Notes cell in `repo-profile §5`
  (`docs/repo-profile-EXAMPLE.md`, "Slow gates").
- `/pr-ready` §1 takes an optional `PRIOR` from a caller: the last pass's `PASS` id, its `$VSHA` as a
  literal, and its rows. `/pr-ready` §4.0 compares that literal with `git rev-parse
  origin/<headRefName>` after a fetch. `REUSE` keeps the rows and goes to §5; `RUN` runs §4 in full.
  With no `PRIOR`, §4 runs as before.
- A reused pass prints `pass: reused <PASS id> at <sha7>` above the machine line, and the evidence
  block's `phases` row reads `reverify reused <PASS id>`.
- The evidence block carries `pass <PASS id> <40-char sha>` from the first PR body on, written from
  the pass's own `$VSHA`. `adw-build` §3.6 reads `PRIOR` from that row, never from the branch or
  from memory; a body with no `pass` row gets no `PRIOR`, so its re-pass runs in full.
- A verifier's `baseline red` row counts as the base run for `adw-build` §3.3's
  `known baseline red` line, for any gate, marked or not.
