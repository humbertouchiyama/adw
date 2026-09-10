---
description: Safely clear stale git worktrees + local branches under .claude/worktrees/, plus whatever disposable state repo-profile §18 declares (servers, ephemeral databases, caches, daemons). Dry-run → confirm.
---

# Cleanup

Reclaim a session's leftovers: merged/closed worktrees + their local branches, and whatever
**disposable state** this repo's `.claude/repo-profile.md` §18 declares (servers, ephemeral
databases, caches, daemons). **Destructive** — so it classifies first, prints a plan, and waits for
your go-ahead.

**This file lives in the `adw` repository and is fetched, not copied** (adw-core §9). It is repo-agnostic: every value that could differ between repos is in the consuming repo's `repo-profile.md`. Read
the consuming repo's `.claude/repo-profile.md` §18 before Phase 3 — it is not auto-included, and
without it Phase 3 has nothing to classify.

**Input**: optional single flag.

| Flag | Effect |
|---|---|
| (none) | dry-run → print the plan → **wait** for `proceed`/`yes` → execute |
| `force` | skip the confirmation prompt **only**. It NEVER overrides a safety check (see Invariants). The "would-lose-commits" bucket is never auto-executed, even with `force`. |

Run from the **main repo root** (or any worktree — the skill resolves the main tree itself). Never `cd` into a worktree you may remove.

**Environment note:** in compound Bash scripts here, `git`/`rm`/`cat`/`wc` intermittently drop off `PATH` (RTK command-rewrite hook + sandbox) → spurious `command not found` / exit 127. Use **absolute binary paths** in this skill's scripts: `/usr/bin/git`, `/bin/rm`, `/bin/cat` (also bypasses the RTK `git`→`rtk git` rewrite). Prefer bash builtins (`[ -z "$(...)" ]`) over `wc`.

---

## Safety invariants (bind always — `force` does not override any of these)

- **Never remove a DIRTY worktree** (`git status --porcelain` non-empty). Report it, skip it.
- **Never remove a branch/worktree that would lose commits** — commits on the branch not reachable from its base and not captured by a MERGED PR (i.e. added *after* the merged head). These go to *Skip — needs you*, never auto.
- **Never touch protected refs**: the main working tree (repo root), the worktree you're running from, any branch currently checked out in a worktree, and every branch `repo-profile §3` names (plus `master`).
- **Never kill live disposable state that isn't tied to a worktree being removed** — that's an active session. `repo-profile §18` defines the liveness probe.
- **Never destroy anything outside §18's name guard.** Each §18 entry states the exact pattern a thing must match before it can be dropped, and the production/dev names that are off-limits. No guard, no destruction.
- **One failure never aborts the rest** — a removal that errors is reported and skipped; the sweep continues.
- Prefer `git worktree remove <path>` **without** `--force` (dirty ones are already excluded); if it errors, skip and report — do not `--force`.

---

## Phase 1 — Resolve context

```bash
MAIN=$(/usr/bin/git worktree list --porcelain | head -1 | sed 's/^worktree //')   # space-safe; main tree is always first
CUR=$(/usr/bin/git rev-parse --show-toplevel)                                       # the worktree we're in (protect)
BASES="origin/<default base> <default base> origin/<production branch> <production branch>"  # repo-profile §3, in that order
/usr/bin/git -C "$MAIN" fetch --prune origin 2>&1 | tail -2                         # refresh [gone] markers
```

> Per the environment note above, git invocations use the absolute `/usr/bin/git` (the RTK hook / sandbox intermittently drops `git` off `PATH` → exit 127). Apply the same to `git`/`rm` in the snippets below when you run them.

Build the PR map in **one** call (resilient — if `gh` is unreachable, note it and degrade to ancestry + `[gone]` signals only):

```bash
gh pr list --state all --limit 300 --json number,state,headRefName,baseRefName,headRefOid
```

Enumerate: `git -C "$MAIN" worktree list --porcelain` (worktrees), `git -C "$MAIN" branch -vv` (local branches + upstream `[gone]`), and each discovery command `repo-profile §18` gives for this repo's disposable state.

---

## Phase 2 — Classify each worktree / branch

For each worktree under `.claude/worktrees/` (and each **branchless** local branch), decide its bucket. **Precedence matters** — evaluate top-down, first match wins:

| # | Condition | Bucket |
|---|---|---|
| 0 | Protected (root / current / a checked-out branch named in `repo-profile §3`, or `master`) | **Skip — protected** |
| 1 | Worktree DIRTY (`git -C <wt> status --porcelain` non-empty) | **Skip — dirty** |
| 2 | Branch's PR is **OPEN** | **Skip — open PR** |
| 3 | Branch's PR is **MERGED** AND `git rev-list <mergedHead>..<branch>` is **empty** (no commits added after the merge) | **Remove** (capture confirmed against the *merged head*, not base — squash-safe) |
| 3b | Branch's PR is **MERGED** with commits **past** `<mergedHead>` (added after merge) | **Skip — needs you** ("merged PR, N commits added after merge would be lost") |
| 4 | Branch's PR is **CLOSED** AND `git rev-list origin/<base>..<branch>` is **empty** | **Remove** (nothing lost) |
| 5 | Branch's PR is **CLOSED** with commits not on base | **Skip — needs you** ("closed PR, N commits would be lost") |
| 6 | **No PR**, upstream `[gone]`, AND `rev-list <base>..<branch>` empty | **Remove** |
| 7 | **No PR**, upstream `[gone]`, commits not on base | **Skip — needs you** ("remote gone, N local-only commits") |
| 8 | **Detached HEAD** worktree (e.g. `pr-<N>`), clean, AND (HEAD is ancestor of `origin/<base>` OR PR #`<N>` from the dir name is MERGED/CLOSED) | **Remove** (no branch to delete) |
| 8b | **Detached HEAD** `pr-ready-*` worktree, clean, AND last modified > 2h ago (`[ -n "$(find <wt> -maxdepth 0 -mmin +120)" ]`) | **Remove** (no branch to delete) |
| 9 | Anything else (ahead of base, no merge signal, unknown) | **Skip — not stale** |

- `<base>` = the PR's `baseRefName` when a PR exists, else the first of `$BASES` that resolves.
- **Row 8b** deliberately consults **no PR state**. A `pr-ready-*` worktree is `/pr-ready`
  §4.3's throwaway verify checkout — detached at a head that already exists on origin, so it
  holds zero unique commits and nothing can be lost by removing it. Keying it on "no open PR
  has this OID" would be wrong in both directions: `blocked`/`failed` units keep their PR
  **open** at that head (so the rule would never fire for the case that most needs it), and
  the `v1` pass runs *before* the PR exists (so during that window it would reap a live one).
  The 2h mtime guard is what separates a dead session's leftover from a running one; a wrong
  removal costs a re-run, never work, and the dry-run gate still shows it first.
- `<mergedHead>` = the MERGED PR's `headRefOid` (from the PR map). For a squash merge the capture check is `<mergedHead>..<branch>`, **not** base ancestry — squash rewrites, so base ancestry always flags a merged branch (Rows 3/3b check the merged head instead). If `gh` is unreachable so `headRefOid` is unknown, a MERGED branch with **any** commit ahead of base falls to *Skip — needs you* (fail safe — never blind-`branch -D`).
- Ancestry-empty check: `[ -z "$(git -C "$MAIN" rev-list origin/<base>..<branch> 2>/dev/null)" ]`, or `git merge-base --is-ancestor <branch> origin/<base>`.
- A branch checked out in a worktree being **Removed** becomes deletable *after* the worktree is gone (order below).

---

## Phase 3 — Classify each piece of disposable state

**`repo-profile §18` declares what exists in this repo, how to detect it, how to tear it down, and
the name guard each destruction must satisfy.** Read it; do not guess, and do not carry a copy here.
A repo whose §18 says "none beyond worktrees" skips this phase entirely and says so in the plan.

Whatever §18 lists, classify each instance the same way:

| Condition | Action |
|---|---|
| An orphan with no state record (a log-only leftover) | its worktree is being removed → goes with it; else delete the leftover |
| A state record present, worktree **being Removed** | tear down **first**, then remove the worktree |
| A state record present, worktree **kept**, the thing is **dead** (§18's liveness probe says so) | tear down (stale) |
| A state record present, worktree **kept**, the thing is **live** | **Skip — live** (active session; never auto-kill) |
| Shared/global state owned by no live instance (§18's sweep) | drop it, once, at the end of Phase 5 |

Two invariants bind here regardless of what §18 says:

- **Liveness is probed, never assumed.** A thing that looks abandoned because its worktree is gone
  may still be running.
- **Every destruction passes §18's name guard first.** The guard is what separates an ephemeral
  artefact from the developer's real database, cache or daemon. If §18 gives no guard for a thing,
  it is not eligible for automatic removal — report it instead.

---


## Phase 4 — Plan (dry-run gate)

Print the plan, grouped into buckets (lead with what will be removed; skips explain *why*). Example:

```
Cleanup plan
────────────
Remove (3 worktree + branch):
  pr-694            (detached)          PR #694 MERGED
  invite-fix        [feat/invite]       PR #701 MERGED   · <§18 state> → tear down first
  spec-x            [feat/spec-x]       remote gone, 0 commits ahead of <base>
Clear (N leftover <§18 orphans>):
  <names>                               (no state record)
Drop (N orphan <§18 shared state>):
  <names>                               not owned by any live instance
Skip — needs you (1):
  old-refactor      [feat/refactor]     PR #650 CLOSED — 4 commits not on <base> (would be lost)
Skip — live (1):
  team-invite-flow  [feat/team-invite]  <§18 liveness evidence> (active session)
Skip — protected: <base>, <current worktree>
```

The `Clear` and `Drop` rows print only when `repo-profile §18` declares state of that kind. A repo
with none prints neither, and says `no disposable state beyond worktrees (§18)` once.

- **No flag** → STOP here. Ask: *"Proceed with the Remove/Clear/Drop above? (`proceed` / `yes`, or name items to exclude)"* Wait for the reply.
- **`force`** → skip the prompt and execute the Remove/Clear/Drop set. The *Skip — needs you* bucket is **still not executed**.

---

## Phase 5 — Execute (order matters)

Per **Remove** worktree, in this order (so `branch -D` doesn't hit "checked out at worktree"):
1. If it owns live or stale §18 state → tear it down (Phase 3).
2. `git -C "$MAIN" worktree remove "<path>"` (no `--force`; on error, report + skip this item).
3. If it had a branch and the branch is now free → `git -C "$MAIN" branch -D "<branch>"` (force `-D` is correct: squash-merged branches aren't base ancestors, but capture was confirmed in Phase 2 via `<mergedHead>..<branch>` empty).

> Anything a worktree keeps **inside its own directory** — build output, caches — is reclaimed by
> `git worktree remove` along with the directory. `repo-profile §18` says which of this repo's state
> is in that category and therefore needs no separate sweep, and which lives outside the worktree
> and does.

Then:
4. **Branchless** stale branches (Remove bucket, no worktree) → `git -C "$MAIN" branch -D "<branch>"`.
5. **Clear** orphan §18 leftovers in kept roots (no state record → nothing to tear down).
6. **Shared-state sweep** — run §18's sweep once, at the end, excluding everything owned by a
   kept LIVE instance. §18 gives the command and the name guard; skip the sweep silently when its
   precondition is absent (the container/daemon is not running, the directory does not exist).
7. `git -C "$MAIN" worktree prune`, then `rm -rf` any `.claude/worktrees/*` dir git no longer tracks.

---

## Phase 6 — Report (bucketed)

Lead with outcomes, then anything left for the user:

```
Cleaned:
  Worktrees removed:  pr-694, invite-fix, spec-x
  Branches deleted:   feat/invite, feat/spec-x
  <§18 kind> torn down: invite-fix (<what was dropped>)
  Leftover dirs:      <names>
  Orphan <§18 kind>:  <names>
Left for you:
  old-refactor — closed PR, 4 commits not on <base>. Keep or `git branch -D feat/refactor` to discard.
  team-invite-flow — live <§18 state>. <§18's own teardown command> when done.
Nothing committed. This skill only mutates local worktree, branch and §18 state.
```

Rows for a §18 kind this repo does not have are omitted, not printed empty.

Never commit as part of `/cleanup` — it only reclaims local state.
