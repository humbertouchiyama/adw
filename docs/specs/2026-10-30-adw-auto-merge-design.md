# ADW auto-merge — the run tests, shows, and merges

Status: draft for the owner's approval. Date: 2026-10-30.

`repo-profile`, `adw-core`, `adw-build` and the other names below are the contract's own. "Native
repo" and "web repo" are the two app repos that run ADW. The web repo holds the webapp and its API.

## 1. Why

Data: 87 completed intents since 2026-09-28, read from transcripts and GitHub.

- **The wait is the owner, not the agent.** 75% of an intent's lead time is owner wait, and 24% is
  agent work. 88% of the time the agent is not busy, a PR is open. 38% is at night.
- **Small items show it best.** One unit under 300 lines: lead median 1.4 h, agent 0.7 h. In the
  slowest of them the agent worked about 1 h, and the rest was waiting.
- **The owner waits because the owner tests.** Most of what the owner says after a PR is process
  (464 messages, 88%). What is left is 24 bugs, 16 "not how I pictured it" (12 of them visual:
  padding, icon size, placement) and 6 new asks. A device test with screenshots would catch about
  two thirds of those. That is an estimate. It would miss feel, timing, real-world conditions and
  new ideas.

So the run should do the test the owner does today, show the result, and merge. The owner's own
check moves to after the merge, when it blocks nothing.

Agent build time is a separate problem and a separate design (§10).

## 2. Goals, non-goals, anti-goals

**Goals**

- A PR that passes its own test merges with no owner action.
- The owner sees every changed screen without building the app.
- It works for the native repo and the web repo.
- The owner can hold any intent, and can point an intent at a feature branch.

**Non-goals**

- Shorter agent time. A required walk makes it longer. See §10.
- Any change to releases. `develop` → `main` stays the owner's, on its own schedule.
- Removing the approval gate. `approve` still starts the build, except for a small follow-up (§4.7).
- A change to when sub-PRs merge (`adw-core` §6). Only §4.2's session rule reaches them.

**Anti-goals: this has failed even if it technically works, when**

- A walk that did not run, or could not act, counts as a pass.
- Anything reaches the production branch without the owner.
- A screenshot that leaves the machine shows real user data.
- The owner cannot tell what merged since their last check.
- The owner gets more questions than today.

## 3. What the owner decided

1. The run tests its change on a simulator (native) or in a browser (web), and shows screenshots of
   every changed screen.
2. Auto-merge is a per-intent flag. The owner sometimes holds one intent or points PRs at a feature
   branch.
3. No mock-up or preview before planning. It would guess at a screen the plan has not shaped.
4. The owner checks feel, timing and real-world conditions after one or more intents have merged.
   This is independent of releases. What they find becomes new intents.
5. An unattended staging deploy is acceptable, migrations included. A push to `develop` deploys the
   webapp to staging, and the distributed staging app uses that same environment.
6. The web walk reuses the web repo's `/e2e-sweep`.
7. Screenshots go in a separate branch of the same repo and are linked from a PR comment.
8. The owner changes their own auto-mode rule. Today it allows `gh pr merge` only when the user names
   that PR in the conversation. No run and no PR edits that rule.
9. Fixes that make walks pass are part of this work. The three causes past walks already show are
   fixed in stage 1 (§4.3). The rest come in a second stage, with what holds the most PRs first (§9).
10. A small follow-up skips the approval step, only when the owner marks it a follow-up and it stays
    one small unit (§4.7).

## 4. How it behaves

### 4.1 The flag

- Each intent has `merge: auto` or `merge: hold`, in the spec header beside `base:` (`adw-core` §2). Like
  `base:`, it is intent-wide. `adw-build` Phase 0 refuses a mixed set, and refuses `auto` on the
  production branch. The production branch can never be `auto`.
- **Default, when the spec is written:** `auto` when `base:` is the default base and the repo profile
  says `on`. `hold` for any other base. The owner can set `auto` by hand on a feature branch.
- **Missing means hold.** A spec with no `merge:` line, such as any intent approved before this ships,
  is `hold`. So is a repo profile with no `auto-merge default` row. No run infers `auto` from silence.
- **Setting it:** `--hold` on `/adw-init` (and `/adw` once that alias lands), or at the approval gate.
  It reaches the spec on disk before the build starts. The approval surface always prints the line,
  for example `merge  auto → develop, after a clean walk`. `approve` on a surface that prints it is
  the owner's explicit consent, the same way a printed chain is consent for its sub-PR merges
  (`adw-core` §6, §7). A follow-up's consent is in §4.7.
- **Late stop:** the label `adw:hold` on the PR stops the merge up to the merge call itself. The owner
  can add it from a phone, and it moves no head.
- **Per repo:** a `repo-profile` §3 row, `auto-merge default: on | off`, is the kill switch. The gate
  reads it at merge time, so `off` also stops runs already in flight.

### 4.2 The merge gate

The run merges an independent or final PR only when all of these hold. Each one is read fresh, from
the source it names, never from memory.

1. **Flag.** The spec at the head says `merge: auto`, the profile row says `on`, and the PR has no
   `adw:hold` label.
2. **Base.** The PR's base is the intent's base, and it is not the production branch.
3. **Verified head.** The evidence block's new `verified <sha>` row equals the PR's head, and the PR
   has no `adw:blocked` or `adw:failed` label. `adw-build` §3.7 writes that row when the PR reaches
   `ready`, from the `$VSHA` the driver returned, never from a fresh derivation. A final PR with a
   carried block is `blocked`, so it waits for the owner as it does today (§8, C8).
4. **Paths.** The diff touches nothing in the repo's `merge-protected paths` row (§8, C19). It also
   matches no `money` row of the repo's trap domains (`repo-profile`, `adw-core` §3), on added or
   changed lines, outside the repo's artifact exclusion pathspec (§8, C9).
5. **GitHub.** `gh pr view --json mergeable,mergeStateStatus` says mergeable, and `gh pr checks` shows
   no failed check, read as `repo-profile` §9 says. `UNKNOWN` is re-queried with the bound
   `code-review` step 6 uses. Still `UNKNOWN` means the PR waits.
6. **Base moved.** The check in §4.6 passed, or the base has not moved.
7. **The walk, for a PR with cases.** `## Smoke result` names a walk at that head (`walk <k> at
   <sha7>`), and that walk has:
   - Audit `0`, and no `not run` or `not runnable` line;
   - no `valid` or `unchecked` defect, no `fixed: … unconfirmed` line, and no row the walk called
     `blocking`, whatever the refuter said (§8, C22);
   - no gap row that names an `AC-<n>`, or a device token of §21's Devices row that a case's `Device`
     line needs. Other gap rows print;
   - `polish` rows and non-`blocking` `refuted` rows print and do not stop the merge.
8. **The screenshots, for a PR with cases.** The comment (§4.5) names that head. The PR's `## Screens`
   list (§4.4) exists, and every listed screen has an image on every device listed for it. A missing
   or empty list means the PR waits.
9. **A PR with `Smoke: none — <why>`** has no walk, so 7 and 8 do not apply to it. It passes only when
   the repo has a UI-paths row and the diff touches no path in it. No row means the PR waits. A PR with
   neither cases nor `Smoke: none` waits.

**The merge** is `adw-build` §3.7's procedure, two Bash calls with the sha written out. The first call
also re-reads the `adw:hold` label, so the late stop holds through the base-moved check. The second is
the merge call alone, with no `--auto`, which merges at once on these repos regardless. Its
`description` names the base. Then the run reads `gh pr view --json state,mergedAt` to confirm:
`gh pr merge`'s exit code is not reliable when a worktree holds the branch.

**When any condition fails:** the PR stays open, exactly as a `ready` PR does today. The run-report
line names the first condition that failed, and the owner can merge it by hand. A hold is never an
error. It adds no question and costs no more than today.

**After a merge:** the PR gets the label `adw:auto-merged` and its evidence block gets a `merge` row.
The run report gains `merged` as a PR state, printed with the link to the screenshots. §3.8's `⚠
smoke` flags stay for a PR that waits. A merged line prints the counts of the `polish` and `refuted`
rows instead. Phase 5's cleanup runs after the gate, as usual.

**Across sessions (§8, C13).** Today provenance is keyed on the session, so a run that loses its state
leaves open PRs to the owner (`adw-build`, top; `adw-core` §1.1, §7.1). Long runs compact, and
multi-unit intents are 86% of lead hours, so that rule would stop most of what this design is for. The
gate does not depend on memory: the flag, the `verified` row, the walk line and the labels are all
durable, and the owner approved the merge. So any run building that slug may merge when every
condition holds, after a compaction or in a new session. The `verified` row lets a chain merge a
`ready` sub-PR, or carry a `blocked` one that has a verified head, in the same way. A run still never
merges a PR of another slug, and an owner who is testing a PR adds `adw:hold`.

### 4.3 Walks that can pass

Under the rule above, **none of the last 6 native walks would have passed.** Since 2026-10-01 the
native repo opened 35 ADW PRs to `develop`. 10 had cases and 6 have a walk result. Of those 6, 3 did
not run (2 ran out of host memory during the build, 1 had no verified head) and 3 have gap rows (in
the worst, the camera blocked 12 of 13 cases). The web repo has had no walks.

The first three fixes below do not clear those 3 walks. Each one keeps a gap that names a case: a case
that asks for a form field the app does not have, an account the runner never drove, and a refused AI
key. So stage 1 also fixes those three causes on the native repo (the last three items below). The web
repo gets one only when its own holds show that cause. Other causes, such as the camera, are stage 2
(§9).

- **What a walk cannot do goes outside the cases.** Camera capture, push and real networks go under a
  new `## For your check` section as `### CHECK-<n>` items, each with a `Checks` line. They are not
  `AC` cases, so the relay, the Cases check, `<total>` and the Audit never see them and no runner
  changes. `adw-build` §3.5's rule that a criterion only a look can check "has a case" now reads "a
  case or a CHECK". **A CHECK does not excuse a changed screen:** §4.2 condition 8 still needs an image
  of every one. So a feature whose screens sit behind the camera waits for the owner until the walk
  can reach them.
- **The host running out of memory.** Two of six walks died here. A new §21 row, `Build floor`, is a
  command that exits non-zero when the host cannot finish a build. The relay runs it before Launch. On
  non-zero it waits as a queued walk does and tries once more. If it still fails, the walk is `not
  run` and the PR waits.
- **Walks queue.** Only one native walk can run at a time, and today a held lock returns `smoke not
  run`. With parallel intents that would hold PRs for no reason. So:
  - The relay treats the runner's lock-held exit as queued, and retries in Bash calls under the 600000
    ms limit, for up to the holder's Max minutes. Then it gives up with `smoke not run`.
  - `<start>` is printed when the walk gets the lock, so waiting does not spend its own Max minutes.
  - §21's Wait test must test this walk's own release, not the absence of any lock. Today a finished
    walk keeps waiting while the next walk holds the lock, and it can reach `DEADLINE`.
- **A case the app cannot do.** When `adw-build` §3.5 writes a case, every field, control and screen
  a step names is checked against the code at the PR head. If the case is wrong, it is rewritten. If
  the code lacks what the criterion asks for, that is a defect, fixed before the walk like any other.
  The walk never finds this out on its own.
- **A second account.** §21 gets a `Second account` row: a seeded test account the runner can sign in
  as, and how to switch to it. A case that needs two users signs in as both in its steps.
- **The AI service.** The walk's build points the app at a stub of the AI service that returns fixed
  answers, so no case needs a live key. What a real AI answer looks like goes in `## For your check`.

### 4.4 Every changed screen

Cases today are 1 to 5, written from acceptance criteria (`adw-build` §3.5). They do not promise every
changed screen. So:

- **The list.** The PR body gets a `## Screens` section, after the `<!-- /smoke -->` marker so the
  relay's case extraction is unchanged. It has one line per changed screen, naming its devices. A final
  PR's list joins its units' lists. A PR that changes no screen writes `Screens: none — <why>`, which
  §4.2 treats like `Smoke: none`.
- **The cases.** Each listed screen appears in a case. The limit of 5 cases is lifted where the list
  needs more. §3.5's `On <screen>, <screen>: repeat step 2` carries only screens that should match. A
  screen whose change differs gets its own step and `Expected`.
- **The images.** The walk keeps an image of each listed screen on each listed device, passed or
  failed. Today the runner keeps images for defect rows only. So the native skill, its `verify.sh`, and
  §21's Evidence and Audit rows change: Evidence locates every listed screen's image, and the Audit
  fails when one is missing.

### 4.5 Screenshots

- Each app repo gets a branch, `adw-screens`, with no shared history, holding only images. It is never
  merged.
- After the relay returns, a second relay (`adw-core` §8's Re-execute and relay row) pushes that walk's
  images and posts one PR comment: one image per listed screen and device, linked by sha, naming the
  head. A later walk replaces the comment. This relay alone may push to `adw-screens`. The smoke relay
  still posts nothing (`adw-build` §3.8).
- On a rejected push it fetches and tries once more. A push that still fails means no comment, so the
  PR waits.
- `## Smoke result`'s evidence line links the comment, not only the local path.
- **Data.** A walk whose screenshots leave the machine uses `test-env.sh up --scratch-db`, so it sees
  seeded accounts only. A template clone carries real dev data, so it is not allowed for a walk. The
  repos are private, and that does not change this rule.
- **First task of the plan:** post one real image on one PR, and check that it renders on the web and
  in the GitHub phone app. If it does not, stop and bring it back to the owner.

### 4.6 When the base has moved

Today a PR is verified at its fork point, and "the human merge gate owns the residual semantic-conflict
risk" (`adw-build` §3.4). With no human at the merge, the run owns it. Most develop PRs get no CI,
parallel intents will now move `develop` often, and 20 of the last 40 merged ADW PRs were already
behind `develop` at merge (GitHub compare, 2026-10-17 to 10-28).

Adding a merge commit to the PR would void `ready`, the walk and the screenshots (`pr-ready` §6, "any
commit voids `ready`"), and every base move would then cost a review. So the run tests the merge
without moving the head. Before merging, when `origin/<base>` has moved past the fork point:

1. Compare files. When the incoming changes touch a file the PR touches, the PR waits.
2. In a detached worktree, merge the base into the head. A conflict means the PR waits. `adw-build`
   already bans resolving a sync conflict unattended.
3. Run the repo's gates on that tree, with `<base>` as the base. On a repo whose §21 has a lock, they
   run under it: parallel builds are what killed two walks. A red gate means the PR waits. A stale call
   into a renamed function goes red here. On the web repo the gates include
   `check-migration-order.mjs`, which must run here: a migration whose `when` is at or below the base's
   maximum is silently skipped, in production as well.
4. Discard the worktree, and record the result in the `merge` evidence row. The head has not moved, so
   `ready`, the walk and the screenshots still hold.
5. Merge. If the base moves again during this check, merge anyway when GitHub says mergeable. That
   leftover risk reaches staging, and reaches production only when the owner releases.

**The cost:** about half of PRs pay for one cold build and one gate run here. The next design (§10)
counts it.

### 4.7 What the owner does after

- **Finding what to check:** `gh pr list --state merged --label adw:auto-merged`. Each PR's body lists
  what it left for the owner under `## For your check`.
- **A finding:** a new intent, typed in any session. Nothing watches PR comments, and this design adds
  no listener: that needs a scheduler that does not exist (design §7).
- A merged intent is no longer live (`adw-core` §1.1), so a follow-up gets a new slug.
- **A small follow-up skips the approval gate.** The owner marks it, for example
  `/adw-init --followup <slug> logo bigger`. That typed line is the consent to build, and to merge under
  the rules of §4.1 (§8, C21). It skips the gate only when triage finds one D0 unit, nothing is in
  `needs you`, and there is no `⚠` line. Anything else stops at the gate as usual. The run prints the
  `merge` line when it starts, so the owner can still add `adw:hold`. §4.2's gate applies unchanged.

### 4.8 The web walk

The web repo has no `repo-profile` §21, so `adw-build` §3.8 does not run there. `/e2e-sweep` exists and
already drives a browser, but it takes no case list and is not unattended end to end. The work:

- A web §21 with every row §3.8 checks: Launch, Cases check, Devices, Driver probe, Wait test, Result,
  Evidence, Audit, Max minutes, Abandon, and the new Build floor.
- A case-list mode for `/e2e-sweep`, the same shape as the native one, with one lane.
- **Devices:** `desktop` and `phone width`, both in Playwright. `/e2e-sweep` already requires Playwright
  for any screenshot that is not desktop width, because Chrome's resize does not change the rendered
  viewport. Only Chromium is installed here, so iPad Safari is not walked. It belongs to the owner's
  check.
- **Driver probe:** one Playwright click on each device that must change the page, then a read that
  proves it did.
- The walk does not need the sweep's Chrome profile. A closed profile stops nothing.

Until this lands, a web PR with cases has no walk, so it waits, and its report line says why.

## 5. Where the contract changes

| Place | Change |
|---|---|
| `adw-core` §1.1, §7.1 | "Never merges a PR it did not open this session", and §6 keyed on the session (§4.2) |
| `adw-core` §2 | `merge:` in the spec header: intent-wide, missing means `hold` |
| `adw-core` §4 | "Each costs +1 merge consent" no longer holds for an `auto` intent |
| `adw-core` §5, `adw-build` Phase 0 | Create `adw:hold` and `adw:auto-merged` where `adw:blocked` is created |
| `adw-core` §6 | The auto-merge clause. The standing no-merge paragraph: an approved `merge` line, or a `--followup` line, is the owner's word for that intent |
| `adw-core` §7 | The approval surface's `merge` line, and "the PR to `base:` still needs explicit human consent" |
| `adw-core` §7, run report | `merged` as a PR state ("these four keywords are the only PR states"), its order, and the line format |
| `adw-core` §8 | Name the screenshot relay under Re-execute and relay |
| `adw-init` | The quoted spec-writer prompt and the validation list carry `merge:`; `--hold`, setting it at the gate, and `--followup`; the note that a mid-chain compaction leaves a sub-PR human-owned |
| `install/stubs/adw-init.md` | The `Usage` line |
| `adw-build` top | The Never list and the session-boundary rule (§4.2) |
| `adw-build` Phase 0 step 4 | Refuse a mixed or invalid `merge:` |
| `adw-build` §3.4 | The `verified` and `merge` evidence rows; "the human merge gate owns the residual…" |
| `adw-build` §3.5 | `## Screens`, `## For your check`, the case limit, the "has a case" rule, the check that a case can be driven at the head |
| `adw-build` §3.7 | The `ready` row; the gate; writing `verified`; the merge procedure (§4.2) |
| `adw-build` §3.8 | Queueing, Build floor, screenshots, the gate's pass test, the report flags |
| `adw-build` Phase 4 | "Waits `ready` for the one human consent", and the final PR's merge |
| `adw-build` Phase 5 | The report's state order |
| `review-core` §8, `pr-ready` §7 | Merge consent can also come from an approved `merge` line |
| `adw-dispatch` | The brief's "Never merge a PR unless the Intent says so" must not stop a merge this gate allows |
| `docs/00-design.md` §1, §3.5, §4.1, §4.2, §4.7, §6, §7 | Each says the human merges or consents to every merge. §7 holds "not in v2: auto-merge" |
| `docs/repo-profile-EXAMPLE.md` §3, §21 | The new rows, or new repos never get them |
| `scripts/adw_analyze/github.py` | Read the `verified` and `merge` rows; check `BLOCK_LINES` still fits |
| Native repo profile | `auto-merge default`, `merge-protected paths`, UI-paths; §21 Evidence, Build floor and Second account; Launch and Wait test for queueing |
| Native `e2e-sweep` skill, `verify.sh`, `provision.sh` | An image for every listed screen, the Audit for it, the queue, signing in as the second account, and the AI stub in the walk's build |
| Web repo profile, `/e2e-sweep` | §4.8, and the same three §3 rows |

The native §21 has no Evidence row today, although the relay's own check requires one. One relay
stopped on that and others walked anyway, so the check is applied unevenly. The row lands first (§9),
and the plan must find out why, because the gate relies on it.

## 6. Prerequisites outside any PR

Both are the owner's, before the first real merge:

- **The auto-mode rule (§3, 8).** Until it changes, the merge call is denied. A denied auto-merge is a
  hold: the PR stays `ready`, with no `adw:blocked` label, and the report line names the command to run
  by hand. In a mode that prompts instead of denying, an unattended pane waits at that prompt, as
  sub-PR merges do today.
- **The saved memory.** The web repo's project memory says never to merge a PR unless the user says
  "merge" for that PR. `adw-core` §6 today makes such a line binding on a PR into the base. The §6
  change above settles the contract, and the memory must change with it, or a session reads two rules
  that disagree. No run edits it.

## 7. How we will know

Each contract PR carries `predicts` lines (self-improving-loop design). Baselines come from the
2026-10-29 report. The builder sets the amounts and dates from it.

| Metric | Direction | Why |
|---|---|---|
| `owner.wait_share.v1` | down | The main claim |
| `time.intent_lead_hours_median.v1` | down | The owner's experience |
| `owner.halts_per_merged_pr.v1` | down | Fewer stops |
| `outcome.reverts.v1` | no worse | The anti-goal: broken merges would show here |

New reader numbers, each from the `merge` row:

- PRs auto-merged, as a share of independent and final PRs.
- Holds per failed condition. This shows what to fix next.
- Auto-merged PRs that got a follow-up intent or a revert within 7 days. This is the false-pass rate.

**Kill test:** if reverts rise, or the false-pass rate stays high, turn the §4.1 row to `off` and
read the holds. The auto-merge share over the first four weeks after both repos are on says whether
the walks are good enough.

## 8. Calls I made, not the owner

- **C6** Auto-merge is on by default for the default base, and off for any other base.
- **C7** Pass means every case was walked and no confirmed defect is left. `polish` and non-`blocking`
  `refuted` rows do not stop it.
- **C8, reversed.** I first said carried blocks should not stop an auto-merge, because the owner chose
  "merge" 8 of 8 times. Those answers were about merging a blocked sub-PR into the integration branch,
  with the final PR's stop still ahead. They say nothing about `develop`. So a carried block now waits
  for the owner. This holds about 10% of PRs (8 of 82 since 2026-10-01).
- **C9** A `money` row hit waits for the owner. My earlier guess also held migrations and anything that
  deletes data. The owner accepted migrations on staging (§3, 5). Deletes have no reliable grep
  (`adw-core` §3 measured this for soft delete), so the walk has to catch them.
- **C10** No trial period where the gate only reports. A hold costs the same as today, and a false pass
  reaches staging until the owner releases. The §4.1 row is the switch.
- **C11** `adw:hold` as a late stop, in addition to the flag.
- **C12** A PR with `Smoke: none` can merge when the repo has a UI-paths row and its diff touches no path
  in it.
- **C13** The gate rests on durable facts, so a compacted run or a new session on that slug may merge,
  and a compacted chain may merge its sub-PRs. This replaces provenance keyed on the session, and it is
  the largest loosening in this design. An owner testing a PR adds `adw:hold`.
- **C14** The web walks cover `desktop` and `phone width` in Playwright only.
- **C17** The base-moved check tests the merge in a throwaway worktree, so the head stays put. When the
  incoming changes touch a file the PR touches, the PR waits. The hold counts will show how often.
- **C18** A changed screen with no image holds the PR, even when part of it is a CHECK. This follows the
  owner's "every changed screen". The cost is that camera features wait until the walk can reach those
  screens.
- **C19** A PR that touches `merge-protected paths` waits. A PR must not be able to change its own safety
  rules or the deploy and then merge itself. The row starts with `.claude/**`, `.github/workflows/**`
  and the deploy config the workflows read (on the web repo, `firebase.json` and `.firebaserc`).
- **C20** A gap row stops the merge only when it names an `AC-<n>` or a device a case needs. The runner
  already must name the `AC` in a blocked case's gap row.
- **C21** A `--followup` line is consent to merge as well as to build, because the owner asked for small
  follow-ups to skip the step where that consent is given today.
- **C22** A row the walk called `blocking` waits for the owner even when one refuter refuted it. No run has
  measured how often that refuter is right, and a hold costs no more than today. Other refuted rows print.
- **C23** A missing `merge:` line or profile row means `hold`.
- **C24** What a walk cannot do goes in `## For your check`, not in a new `Device` value, so no runner has
  to change for it.

## 9. Order of the work

- **First:** the image test in §4.5, then the native §21 Evidence row. Without that row a literal relay
  walks nothing.
- **Stage 1:** the flag, the gate, the `verified` row, screenshots, the base-moved check, `## For your
  check`, queueing and Build floor, the web walk, and follow-ups. Also the three walk fixes the walks
  that already ran call for (§4.3): the check that a case can be driven, the second account, and the
  AI stub. Without them no walk that has run so far would pass, so the first weeks would measure
  nothing.
- **Stage 2:** other fixes that make walks pass, with what holds the most PRs first, read from the
  hold counts in §7. The first candidate is a stub for the camera.

## 10. Not in this design

- **Agent build time.** On small items the agent works about 40 minutes, and review and verify take
  43% of it. A walk adds tens of minutes on top, and the base-moved check adds a build. That is the
  next design.
- A listener for PR comments.
- Any change to the walk's model, its refuter, or its two smoke fix cycles.

## 11. Left to the builder

- The file layout of the `adw-screens` branch, and the image size and format.
- **Keeping `git fetch origin` fast.** Every worktree fetches every branch, and images pile up. The
  builder chooses downscaling, pruning, or a ref outside `refs/heads/`, and shows the size per month.
- The contents of the UI-paths and `merge-protected paths` rows beyond C19's start, for each repo.
- The Build floor's command and value.
- How the AI stub is wired into the walk's build, and its fixed answers. Which seeded account is the
  second account.
- How a reviewer checks that a `## Screens` list is complete.
- The order of the PRs across the three repos.
