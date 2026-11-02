# ADW auto-merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An ADW run walks its change, posts a screenshot of every changed screen, and merges its
independent or final PR into the intent's base when a nine-condition gate passes, in the native
repo and the web repo.

**Architecture:** Two deterministic scripts in this repo carry what a literal reader would get
wrong: `scripts/adw-screens.py` (push images, post the PR comment) and `scripts/adw-merge-gate.py`
(the gate's conditions and the base-moved trial). App repos reach them through the contract cache
(`.claude/adw/cache/scripts/`), as `adw-run-clean.py` is reached today. The prose contract says when
to call them and owns the two merge Bash calls. The app repos change their profile rows, their walk
runners and, on the web repo, add an AI stub and a case-list walk.

**Tech Stack:** Python 3 stdlib (`unittest`, `subprocess`, `json`, `re`), bash, `gh`, `git`,
Maestro and `xcrun simctl` (native walk), Playwright Chromium and Node (web walk and AI stub).

**Spec:** `docs/specs/2026-10-30-adw-auto-merge-design.md`

## Global Constraints

- **Repos.** "This repo" is `humbertouchiyama/adw` (public). "Native repo" is `AXCMED/AXCMedApp`, "web
  repo" is `AXCMED/Plantoes-app`, both with base `develop`. The README already names both, so
  naming them is not a leak.
- **Public repo hygiene.** No local absolute paths, test-account emails or passwords, Firebase
  project ids, spend, transcript text or private report contents in anything committed here or in
  a PR body here. Name an env var or config key, never its value.
- **Owner stops.** Every push, PR open and merge needs the owner's word in the session. The
  executor says "that needs a push to `<branch>`; say push" and waits. The owner merges every PR
  this plan opens. A task that opens a PR ends there, and the next task that depends on it waits
  for the merge.
- **Order of PRs** (design §11 left it to the builder): image test → native PR N1 → web PR W1 →
  native PR N2 → this repo PR A → PR B → PR C → PR D → web PR W2 → first live run. N2 lands before A
  because A makes the relay require the `Build floor` row. W1 lands before N2 because N2's Launch
  starts the web repo's test env with the AI stub.
- **The native walk uses the web repo's main checkout** for `test-env.sh` (`$PLANTOES`). After W1
  merges, that checkout must be at `origin/develop` before any N2 verification.
- Line numbers below are at `origin/main` 43d0a50 here and at `origin/develop` on 2026-11-02 in the
  app repos. They shift. Locate each site by its quote.
- Contract text follows the repo's style: ASD-STE100 plain words, one rule per sentence, a `Why:`
  only where an existing rule has one. Quoted `>` prompt blocks are sites too.
- Python: stdlib only, runs on 3.9, `from __future__ import annotations`. Tests run from `scripts/`:
  `cd scripts && python3 -m unittest -v <module>`. Test files use the fake-`gh`-on-`PATH` pattern of
  `scripts/test_adw_run_clean.py`.
- Each contract PR body carries `predicts` lines in the format `scripts/adw_analyze/predicts.py`
  parses. Baselines come from the 2026-10-29 report (design §7).
- Commit messages: `<area>: <what>`, ending with the session's attribution trailers.

## Shared formats

Every task that writes or reads one of these uses it exactly as written here.

**`## Screens`** (PR body, after the `<!-- /smoke -->` line; §3.5 writes it):

```
## Screens
- SCREEN-1 · <screen title as the app shows it> · iphone17, ipad
- SCREEN-2 · <screen title> · iphone17
```

Device tokens are the repo's §21 Devices tokens. A PR that changes no screen writes the single line
`Screens: none — <why>` in place of the list.

**`## For your check`** (PR body, after `## Screens`):

```
## For your check
### CHECK-1 <what to try>
Checks: AC-<n> — <what only a person or a real device can judge>
<steps, as a case writes them>
```

**`## Smoke result` first line** (§3.8 writes it; the gate reads it):
`<verdict line> · walk <k> at <sha7> · devices <token>,<token> · <m>m`, plus
`· unaudited: <failing check>` when the Audit exit is not 0. `devices` is new.

**Runner images:** `<sweep>/screens/SCREEN-<n>-<device>.png`, one per listed screen and device,
passed or failed. The §21 Evidence row names this directory.

**Lock lines** a runner prints, exactly: `adw-lock: taken <epoch>` when its walk takes the lock, and
`adw-lock: held by <slug> since <epoch>` when another walk holds it (then it exits non-zero).

**Screens comment** (`adw-screens.py` posts it; the gate reads it):

```
<!-- adw-screens head=<40-char sha> walk=<k> -->
**Screens at <sha7>, walk <k>**

#### SCREEN-1 · <screen title>
![SCREEN-1 · iphone17](<url>) ![SCREEN-1 · ipad](<url>)
```

The alt text `SCREEN-<n> · <device>` is the key. `<url>` is the form Task 1 chose.

**Evidence rows** (§3.4 block):
- `verified   <40-char sha>`: written at §3.7 `ready`, from `$VSHA`.
- `merge      merged <merge sha7> · base unmoved` or `· base trial ok at <base sha7>`.
- `merge      hold <n> — <reason> · at <head sha7>`. `<n>` is the condition number 1–9, or `call`
  for a denied or failed merge call.

**Spec header line:** `merge: auto | hold   # OPTIONAL — omitted = hold`.

**Approval surface line:** `merge   auto → <base>, after a clean walk` or `merge   hold — <why>`.

**Profile §3 rows:** `auto-merge default` (`on` | `off`), `merge-protected paths` and `UI paths`
(globs in backticks, space-separated: `**` crosses `/`, `*` does not).

**Profile §21 rows, new:** `Build floor` (a command, exit 0 = the host can build now), `Second
account` (the roles the walk can sign in as and the command that switches), `Lock` (optional: the
take and release commands and the lock file).

**Labels:** `adw:hold` (`FBCA04`, "ADW: the owner holds this PR — the run will not merge it") and
`adw:auto-merged` (`0E8A16`, "ADW: merged by the run after its gate passed").

**Gate output:** one line, `pass` (exit 0) or `hold <n> <reason>` (exit 1). Exit 2 prints
`hold 0 gate error: <message>`, and the contract treats it as a hold.

## Rulings this plan makes

- **The gate is a script, not prose.** Nine conditions read by a literal reader would drift. The
  script reads, the contract merges. The bare `gh pr merge` call stays in the contract, because the
  permission rule matches that command.
- **`UNKNOWN` mergeability:** re-query 5 times, 10 s apart, then hold. `code-review` step 6 has no
  number to reuse.
- **Pending checks:** wait up to 8 minutes inside the gate's Bash call, polling every 20 s, then
  hold. A red check holds, a billing-blocked one included: the gate cannot tell a note from a
  failure. "No checks" passes (`repo-profile` §9: absent, not red).
- **The kill switch** is read from the profile on the PR's base (`gh api`) and from the local
  checkout. `off` in either holds.
- **A gap row holds when it names a device in the result line's `devices` list.** The design's
  "a device a case's `Device` line needs" is that list, which the relay already passes.
- **No `--delete-branch`** on the merge call. A worktree holds the branch, which is why `gh pr
  merge`'s exit code is not trusted. Phase 5's cleanup stays as it is.
- **The AI stub sits behind the API, in the web repo's test env.** The native app reaches AI only
  through the API, so "the walk's build points at a stub" becomes "the walk's stack does".
- **The second account already exists.** Both repos seed owner, editor and viewer accounts. The
  work is a switch command, not a new account.
- **The `merge` evidence row is written on a hold too**, so the reader can count holds per condition
  (design §7).
- **Web walks take their own lock.** Every scratch-DB seed resets the same three accounts in a
  shared Firebase tenant, so a native walk and a web walk at the same time can sign each other out.
  That ends in a gap row and a hold, never a pass. It is accepted.

## Review Focus

1. **A `## Smoke result` from an older head.** A smoke fix cycle moved the head and no new walk ran.
   The gate must hold on condition 7, not pass on the old walk (Task 10 test
   `test_walk_at_old_head_holds`).
2. **`UNKNOWN` mergeability that never settles.** It holds after 5 tries, and never loops (Task 10
   test `test_unknown_mergeable_bounded`).
3. **A diff too large for `gh pr diff`** (HTTP 406). It holds on condition 4 and never skips the
   money scan (Task 10 test `test_diff_too_large_holds`).
4. **The owner turns the switch off on the base while a run is in flight.** The local copy still
   says `on`. It must hold (Task 10 test `test_kill_switch_off_on_base_holds`).
5. **A `blocking` row that the refuter refuted** (C22). It holds (Task 10 test
   `test_refuted_blocking_row_holds`).

---

## Part 0 — First

### Task 1: Image render test (native repo) — needs the owner

Design §4.5 says to stop if this fails.

**Files:** none committed. A scratch branch and the `adw-screens` ref in the native repo.

- [ ] **Step 1:** Ask the owner for push consent to the native repo, for the ref `adw-screens` and
  one scratch PR.
- [ ] **Step 2:** Build one commit with plumbing, holding `test/one.png` (any walk screenshot from
  `~/.claude/e2e-sweeps/`, downscaled with `sips -Z 1000`). Push it twice: to
  `refs/heads/adw-screens` and to `refs/adw-screens`.
- [ ] **Step 3:** Open a draft scratch PR. Post one comment with two images, one per ref, each as
  `![t](https://github.com/AXCMED/AXCMedApp/blob/<commit sha>/test/one.png?raw=true)`.
- [ ] **Step 4:** The owner opens the comment on the web and in the GitHub phone app.
  Expected: at least one image renders in both.
- [ ] **Step 5:** Record the result in the ledger: `Task 1: Ruling: ref <refs/... chosen> — <why>`.
  Prefer `refs/adw-screens` when it renders, because a default `git fetch` does not download it.
  If only the branch renders, record that each app repo needs
  `git config --add remote.origin.fetch '^refs/heads/adw-screens'` (owner's machine, once).
  If neither renders, stop the plan and bring it to the owner.
- [ ] **Step 6:** Close the scratch PR and delete its branch. Keep the chosen ref.

### Task 2: Native §21 Evidence row (native PR N1)

The row never existed. §21 landed in one commit without it. The relay's own check
(`adw-build` §3.8, "checks §21's … Evidence …") stops on a missing row. Relays that walked anyway
skipped their own check. Say both in the PR body.

**Files:**
- Modify: native `.claude/repo-profile.md` §21 (rows near line 1187–1196)

- [ ] **Step 1: Failing check.** Run, at the worktree root:
  `awk '/^## §21/{f=1} f && /^\| \*\*Evidence\*\*/{n++} END{exit n?0:1}' .claude/repo-profile.md`
  Expected: exit 1.
- [ ] **Step 2:** Add the row after Result: ``| **Evidence** | `<sweep>/screenshots/`: a defect
  row's `### F<n>` cites its PNG there, named `<screen>-<state>-<device>.png` |``. Use the table's
  existing bold style.
- [ ] **Step 3:** Re-run Step 1. Expected: exit 0. Then check every row the relay lists is present
  and not empty: Cases check, Devices, Launch, Driver probe, Wait test, Result, Evidence, Audit,
  Max minutes, Abandon.
- [ ] **Step 4:** Commit `docs(profile): §21 Evidence row — the relay's check needs it`. Ask for
  push, open the PR to `develop`, run the repo's `/code-review`, stop.

---

## Part 1 — App repos, walk side

### Task 3: AI stub (web PR W1)

**Files:**
- Create: web `scripts/ai-stub/server.mjs`, `scripts/ai-stub/fixtures/<task>.json`
- Modify: web `scripts/test-env.sh` (flag parsing near line 22; the API env for the slot)
- Test: web `api/src/services/ai/ai-stub.test.ts`

**Interfaces:**
- Produces: `test-env.sh up --scratch-db --ai-stub`, which starts the stub on a free port for the
  slot and points the slot's API at it. The `[test-env]` ready block prints `AI: stub <port>`.

- [ ] **Step 1:** Read `api/src/services/ai/models.ts` and `api/src/services/ai/clients/*`. Record in
  the ledger which env vars select each `TASK_MODELS` task's backend and model, and which tasks a
  walk can reach (chat, draft, identify, read and extract tasks; not transcribe).
- [ ] **Step 2: Write the failing test** `ai-stub.test.ts`: starts `server.mjs` on port 0, sets the
  slot env the way `--ai-stub` will, and calls each reachable task through its real client.
  Assertions: each returns the fixture's answer; each structured task's answer passes that task's
  own schema; a streaming chat call yields at least one delta and a clean end.
- [ ] **Step 3:** Run `( cd api && npx vitest run src/services/ai/ai-stub.test.ts )`.
  Expected: FAIL, server module not found.
- [ ] **Step 4: Implement `server.mjs`** with Node builtins only: an OpenAI-compatible
  `POST /v1/chat/completions`, stream and non-stream. It picks the fixture by the request's
  `model`. `--ai-stub` sets each reachable task's `AI_MODEL_*` override to a stub model named after
  the task, the backend's base-URL env var to the stub, and its key env var to the literal `stub`.
  Write one fixture per reachable task, the smallest answer that passes its schema.
- [ ] **Step 5:** Run the test. Expected: PASS. Then run the api suite: `( cd api && npm test )`.
- [ ] **Step 6:** Live check: `bash scripts/test-env.sh up --scratch-db --ai-stub`. Sign in with the
  printed pair. Call the assistant route once with `curl`. Expected: the fixture's text. Then
  `bash scripts/test-env.sh down <slot>`.
- [ ] **Step 7:** Commit `feat(test-env): --ai-stub — fixed AI answers for walks`. Ask for push, open
  the PR, run `/code-review`, stop.

### Task 4: Native runner — an image of every listed screen (native PR N2, part 1)

**Files:**
- Modify: native `.claude/skills/e2e-sweep/SKILL.md` (flags near line 43), `references/lanes.md`
  (case rows near 77–110), `references/driving-maestro.md` (capture near 48–61)
- Modify: native `scripts/e2e-sweep/verify.sh` (header 1–26, a new check 8)
- Test: native `scripts/e2e-sweep/selftest.sh`, with a fixture under `scripts/e2e-sweep/fixtures/`

**Interfaces:**
- Consumes: the `## Screens` format.
- Produces: `--screens <path>` on the skill; images at `<sweep>/screens/SCREEN-<n>-<device>.png`;
  `verify.sh <sweep> --final --screens <path>` fails when an image is missing.

- [ ] **Step 1: Failing selftest case:** a sweep fixture whose screens file lists `SCREEN-1` on
  `iphone17, ipad` and holds only `SCREEN-1-iphone17.png`. Expected `verify.sh` exit: non-zero,
  output naming `SCREEN-1-ipad.png`. A second case with both images: exit 0.
- [ ] **Step 2:** Run `bash scripts/e2e-sweep/selftest.sh`. Expected: FAIL on the new cases.
- [ ] **Step 3:** Implement check 8 in `verify.sh`, run only with `--screens`: every listed
  `(SCREEN-<n>, device)` pair has its PNG, and its pixel size matches `devices.tsv`, as check 2 does.
- [ ] **Step 4:** Change the skill: `--screens <path>` is copied to `<sweep>/screens.md`. The walk
  captures each listed screen on each listed device to the image path, whether its case passed or
  failed. A listed screen that no case reaches gets a `G<n>` row naming it.
- [ ] **Step 5:** Run the selftest. Expected: PASS, every case.
- [ ] **Step 6:** Commit `feat(e2e-sweep): --screens — an image of every listed screen`.

### Task 5: Native queue, lock line, Wait test and Build floor (native PR N2, part 2)

**Files:**
- Modify: native `scripts/e2e-sweep/provision.sh` (lock near 263–274; usage 18–47)
- Create: native `scripts/e2e-sweep/build-floor.sh`
- Modify: native `.claude/repo-profile.md` §21 (Launch, Wait test; new Build floor and Lock rows)
- Test: native `scripts/e2e-sweep/selftest.sh`

**Interfaces:**
- Produces: the lock lines; `provision.sh --lock --slug <slug>` (take only; exit 3 when held);
  `build-floor.sh` exit 0 when the host can build now.

- [ ] **Step 1: Failing selftest cases** (with `AXCMED_E2E_HOME` pointing at a temp dir):
  - `--fresh` with a lock file present prints `adw-lock: held by other since <epoch>` and exits 3;
  - `--lock --slug a` on a free lock prints `adw-lock: taken <epoch>` and exits 0, and a second
    `--lock --slug b` exits 3;
  - `--release --slug a` removes it;
  - `build-floor.sh` with `AXCMED_E2E_FLOOR_GB=0` exits 0, and with `AXCMED_E2E_FLOOR_GB=100000`
    exits 1 and prints the free memory it read.
- [ ] **Step 2:** Run the selftest. Expected: FAIL on the new cases.
- [ ] **Step 3:** Implement:
  - `provision.sh` prints the lock lines at the existing take and refuse points, and adds `--lock`.
  - `build-floor.sh` reads available memory as (free + inactive + speculative + purgeable pages) ×
    page size from `vm_stat`. It exits 1 when that is below `AXCMED_E2E_FLOOR_GB` (default `6`), or
    when `pgrep -x xcodebuild` finds a build. Two of six walks died of memory or a concurrent build.
    The 6 GiB is this plan's guess; the hold counts tune it.
- [ ] **Step 4:** Run the selftest. Expected: PASS.
- [ ] **Step 5: Profile rows.**
  - Launch: add "Phase 1's `provision.sh --fresh` prints `adw-lock: taken <epoch>` when it takes
    the lock, and `adw-lock: held by <slug> since <epoch>` then exit 3 when another walk holds it."
  - Wait test: `[ -s "<sweep>/SUMMARY.md" ] && ! grep -qsx 'slug=<slug>' "$HOME/.cache/axcmed-e2e/lock"`.
    This walk's own release, not the absence of any lock.
  - Build floor: `bash scripts/e2e-sweep/build-floor.sh`.
  - Lock: take `bash scripts/e2e-sweep/provision.sh --lock --slug <slug>` · release
    `bash scripts/e2e-sweep/provision.sh --release --slug <slug>` · file
    `$HOME/.cache/axcmed-e2e/lock`, whose `started=` line is the holder's start.
- [ ] **Step 6:** Commit `feat(e2e-sweep): lock lines, --lock, build floor, own-release wait test`.

### Task 6: Native second account, AI stub, §3 rows (native PR N2, part 3)

**Files:**
- Create: native `scripts/e2e-sweep/switch-account.sh`
- Modify: native `.claude/repo-profile.md` §3 (lines 152–159), §21 (Data, new Second account row)
- Modify: native `.claude/skills/e2e-sweep/SKILL.md` (test-env call near line 106)

**Interfaces:**
- Produces: `switch-account.sh <device> <role>`, with role `owner`, `editor` or `viewer`. It signs
  the app in as that role's pair from this run's `[test-env]` block.

- [ ] **Step 1:** Implement `switch-account.sh`: terminate the app, `xcrun simctl keychain <udid>
  reset`, reinstall the app recorded in `provision/ready.env`, then run `flows/login.yaml` with the
  role's pair. Firebase Auth keeps its session in the keychain, so an uninstall alone does not sign
  out.
- [ ] **Step 2: Live check** on one simulator after a `--fresh` provision: switch to `viewer`, then
  to `owner`. Expected: each login ends at the screen `login.yaml` waits for, and a viewer-only
  refusal shows as the viewer. Record the run in the ledger.
- [ ] **Step 3:** The skill's test-env call becomes `test-env.sh up --scratch-db --ai-stub`. The
  Data row says so, and says the walk then needs no live AI key.
- [ ] **Step 4:** Rows:
  - §21 Second account: "owner (default), editor, viewer: the pairs in this run's `[test-env]`
    block. Switch: `bash scripts/e2e-sweep/switch-account.sh <device> <role>`. A case that needs
    two users switches in its steps."
  - §3 `auto-merge default`: `on`. Merging this PR turns it on for the native repo.
  - §3 `merge-protected paths`: `` `.claude/**` `.github/workflows/**` `iosApp/ci_scripts/**`
    `iosApp/Configuration/**` `gradle.properties` `` (the build-config files the release reads).
  - §3 `UI paths`: `` `composeApp/src/commonMain/kotlin/**/presentation/**`
    `composeApp/src/androidMain/res/**` `iosApp/iosApp/**` `iosApp/AXCMedRoundWidgets/**`
    `iosApp/AXCMedIntents/**` ``.
- [ ] **Step 5:** Commit `docs(profile): second account, AI stub, auto-merge rows`. Ask for push,
  open native PR N2 (Tasks 4–6) to `develop`, run `/code-review`, stop.

---

## Part 2 — This repo, PR A: walks show every screen

### Task 7: `scripts/adw-screens.py`

**Files:**
- Create: `scripts/adw-screens.py`
- Test: `scripts/test_adw_screens.py`

**Interfaces:**
- Produces:
  `python3 adw-screens.py --repo <owner/repo> --checkout <path> --pr <N> --head <sha> --walk <k>
  --screens <screens.md> --dir <sweep>/screens --ref <ref from Task 1>`.
  It prints `screens <comment url> · <n> images`, or `screens none — <why>`, and exits 0, 1 (push or
  comment failed after one retry) or 2 (bad flag).

- [ ] **Step 1: Write the failing tests.** Use a temp bare remote and a fake `gh` that records its
  calls:
  - `test_pushes_one_commit_under_pr_path`: after a run, the remote ref's tree holds
    `pr-<N>/<sha7>/walk-<k>/SCREEN-1-iphone17.png`, and the commit's parent is the old tip.
  - `test_creates_ref_when_missing`: no ref on the remote → the commit has no parent.
  - `test_retries_once_on_rejected_push`: the remote moves between fetch and push → one re-fetch,
    a commit on the new tip, success. Twice → exit 1, no comment posted.
  - `test_comment_format`: the posted body starts with
    `<!-- adw-screens head=<sha> walk=<k> -->`, and holds `![SCREEN-1 · iphone17](` with the Task 1
    URL form.
  - `test_replaces_existing_comment`: a comment with the marker exists → PATCH, not POST.
  - `test_missing_image_still_posts_others`: a listed pair with no file is left out, and the
    printed line counts only posted images. The gate, not this script, holds the PR for it.
  - `test_no_screens_dir`: prints `screens none — no images in <dir>`, exit 0, posts nothing.
- [ ] **Step 2:** Run `cd scripts && python3 -m unittest -v test_adw_screens`. Expected: FAIL,
  script not found.
- [ ] **Step 3: Implement.** Build the commit without a worktree: a temp `GIT_INDEX_FILE`,
  `read-tree` of the fetched tip, `hash-object -w` and `update-index --add --cacheinfo` per image,
  `write-tree`, `commit-tree`, `git push origin <commit>:<ref>`. Downscale with `sips -Z 1000` into
  a temp dir first. Find the comment with `gh api repos/<repo>/issues/<N>/comments` and match the
  marker.
- [ ] **Step 4:** Run the tests. Expected: PASS. Then run the whole suite:
  `cd scripts && python3 -m unittest`.
- [ ] **Step 5:** Commit `adw-screens: push a walk's images and post one PR comment`.

### Task 8: §3.5 — screens, checks, cases a walk can drive

**Files:**
- Modify: `commands/adw-build.md` §3.5 (lines 913–943), the §3.6 review brief, Phase 4's final PR
  body
- Modify: `docs/repo-profile-EXAMPLE.md` §21 intro (line 659)

- [ ] **Step 1: Failing check.** `grep -c '## Screens' commands/adw-build.md` prints `0`, and
  `grep -c 'one to five cases' commands/adw-build.md` prints `1`.
- [ ] **Step 2: Edit §3.5:**
  - "one to five cases" (913) → "at least one case; more than five only where `## Screens` needs it".
  - After the case template's `<!-- /smoke -->` (927): the `## Screens` and `## For your check`
    sections, in the Shared formats. Each listed screen appears in a case.
  - "has a case" (933) → "has a case or a CHECK". A CHECK does not excuse a changed screen: the
    screen is still listed.
  - "`On <screen>, <screen>: repeat step 2`" (934): only for screens that should match. A screen
    whose change differs gets its own step and `Expected`.
  - After "`Smoke: none — <why>`" (941): `Screens: none — <why>` for a PR that changes no screen.
  - New rule: before the cases are final, check every field, control and screen a step names
    against the code at the PR head. A wrong case is rewritten. Code that lacks what the criterion
    asks for is a defect, fixed before the walk (back to §3.1).
  - Completeness (design §11 left it to the builder): every changed file under the profile's
    `UI paths` renders on at least one listed screen. §3.6's review brief gains one question: "Does
    `## Screens` list every screen a changed UI file renders?" A miss is a finding like any other.
  - Phase 4: a final PR's `## Screens` joins its units' lists, one line per screen, devices merged.
- [ ] **Step 3:** EXAMPLE line 659: "every PR the human merges" → "every independent and final PR".
- [ ] **Step 4:** Re-run Step 1. Expected: `1` and `0`. Then walk §3.5 as a sonnet PR-opener, in
  writing, on a two-screen change with one camera criterion. Every rule must give one answer.
- [ ] **Step 5:** Commit `adw-build §3.5: list every changed screen; checks a walk cannot do`.

### Task 9: §3.8 relay — queue, Build floor, devices, screenshots (then PR A)

**Files:**
- Modify: `commands/adw-build.md` Phase 1 (287–297), §3.8 (1133–1307)
- Modify: `commands/adw-core.md` §8 (812)
- Modify: `docs/repo-profile-EXAMPLE.md` §21 (656–678), anchor table (44)
- Modify: `docs/00-design.md` §4.2 (548)

**Interfaces:**
- Consumes: Task 7's CLI; the lock lines; the §21 rows.

- [ ] **Step 1: Failing check.** `grep -c 'adw-lock: taken' commands/adw-build.md` prints `0`, and
  so does `grep -c 'adw-screens.py' commands/adw-build.md`.
- [ ] **Step 2: Edit §3.8:**
  - **Row check (1194–1195):** add `Build floor` to the required rows. `Lock` and `Second account`
    are optional.
  - **Cases step (1189–1202):** also extract `## Screens` to `<D>/screens.md`, and pass it to
    Launch as `--screens`.
  - **Before Launch:** run Build floor. On non-zero, re-run it every 60 s for up to Max minutes, in
    Bash calls under the 600000 ms limit. Still non-zero → `smoke not run — build floor: <its
    output>`.
  - **`<start>` (1203):** the epoch of the runner's `adw-lock: taken` line. Only a runner that
    prints no lock line uses `date +%s` before Launch, as today.
  - **Queued (1206–1210):** on `adw-lock: held by <s> since <e>`, wait while the §21 Lock file
    exists and `now < e + Max minutes × 60`, re-checking every 30 s in Bash calls under the limit.
    Then Launch once more. Held again, or the bound is reached → `smoke not run — queued behind <s>`.
    Without a Lock row: `smoke not run — lock held`, as today.
  - **Result line (1281–1296):** add `· devices <tokens>`, the devices passed to Launch.
  - **The screenshot relay, new step after the Audit.** A second `sonnet` relay runs
    `adw-screens.py` with the Evidence row's `screens/` directory, then returns its printed line.
    `## Smoke result`'s `evidence:` line gains `· screens <comment url>`. This relay alone pushes
    to the screens ref. The smoke relay still posts nothing.
  - **Data:** a walk whose images leave the machine runs on a scratch DB. A §21 whose Data row
    allows a template clone gets no screenshot relay: `screens none — data row allows real data`.
- [ ] **Step 3: Edit Phase 1 (287–297):** the ban on lock files and wait-for-lock loops does not
  reach a lock §21 names, which this session waits on only as §3.8 and §3.7 say.
- [ ] **Step 4:** `adw-core.md` §8 row: "relay the app smoke and its screenshots (adw-build §3.8)".
- [ ] **Step 5: EXAMPLE §21:** add the Build floor, Second account and Lock rows. Evidence: "where
  the files showing a defect row are, and `screens/`: one image per `## Screens` pair". Launch: "it
  prints the lock lines (adw-build §3.8)". Wait test: "true once THIS walk released what it holds".
  Data: "a scratch DB; a template clone of real data is never allowed for a walk whose images leave
  the machine". Max minutes: "counted from the lock line, or from before Launch when there is no
  lock". Anchor table: add `adw-build §3.7` to §21's uses.
- [ ] **Step 6:** `00-design.md` line 548: "every PR the human merges" → "every independent and
  final PR".
- [ ] **Step 7:** Re-run Step 1. Expected: both ≥ 1. Run
  `python3 .claude/skills/reviewing-contract-prs/check-anchors.py origin/main HEAD`.
  Expected: no `NEW` line.
- [ ] **Step 8:** Commit `adw-build §3.8: queue on the lock, build floor, screenshots on the PR`.
  Ask for push. Open PR A to `main` with `predicts` lines. Run the `reviewing-contract-prs` skill on
  it, apply what survives, stop for the owner's merge.

---

## Part 3 — This repo, PR B: the flag and the gate

### Task 10: `adw-merge-gate.py check`

**Files:**
- Create: `scripts/adw-merge-gate.py`
- Test: `scripts/test_adw_merge_gate.py`

**Interfaces:**
- Produces:
  `python3 adw-merge-gate.py check --repo <owner/repo> --pr <N> --profile <local profile path>
  --spec-path <repo path> [--spec-path …]` → the gate output line.

Conditions, in order. The first that fails is printed:

| n | Reads | Holds when |
|---|---|---|
| 1 | each `--spec-path` at the head (`gh api …/contents?ref=<head>`); the profile on the base (`gh api`) and the local one; labels | any spec lacks `merge: auto`, specs disagree, either profile has no `auto-merge default` row or says `off`, or the PR has `adw:hold` |
| 2 | `baseRefName`; the specs' `base:`; profile §3 | base ≠ the intent's base, or base is the production branch |
| 3 | the body's `verified` row; labels | row missing, ≠ `headRefOid`, or `adw:blocked` / `adw:failed` present |
| 4 | `gh pr diff --name-only`, `gh pr diff`; profile §3, §2, §11 | a path matches `merge-protected paths`; an added line outside the artifact exclusion pathspec matches the `money` row; the diff cannot be read |
| 5 | `mergeable`, `mergeStateStatus`; `gh pr checks` | not `MERGEABLE` after the `UNKNOWN` bound; a failed or cancelled check; a check still pending after 8 min |
| 7 | `## Smoke`, `## Smoke result`, the `smoke` row | cases exist and: no walk line, its sha7 ≠ head, `unaudited`, the `smoke` row's `audit` not `0`, `not run` / `not runnable`, a `valid:` or `unchecked:` line, a `fixed: … unconfirmed` line, a `D<n>` row containing `blocking`, or a `G<n>` row naming an `AC-<n>` or a token in `devices` |
| 8 | `## Screens`; the comment with the marker | cases exist and: no list, an empty list, a marker whose head ≠ head, or a listed pair with no `![SCREEN-<n> · <device>](` |
| 9 | `Smoke: none` / `Screens: none`; `UI paths` | no `UI paths` row, or the diff touches one; or the body has neither cases nor `Smoke: none` |

Condition 6 is `trial` (Task 11). A PR with cases is one whose `## Smoke` has a `### AC-<n>` heading
(match the template at `adw-build.md` 917–927). `Screens: none` on a PR with cases replaces 8 with
9's UI-paths test.

- [ ] **Step 1: Write the failing tests.** A fake `gh` serves a PR fixture (body, labels, files,
  diff, mergeable, checks, comments, contents). One passing fixture, then one test per hold, each
  changing one thing:
  - `test_clean_pr_passes` → `pass`, exit 0;
  - `test_hold_label_holds` → `hold 1`; `test_specs_disagree_hold`; `test_no_merge_line_holds`;
    `test_kill_switch_off_on_base_holds` (base copy `off`, local `on`);
  - `test_production_base_holds` → `hold 2`;
  - `test_verified_row_stale_holds` → `hold 3`; `test_blocked_label_holds`;
  - `test_protected_path_holds` → `hold 4`; `test_money_line_holds`;
    `test_money_line_in_excluded_path_passes`; `test_diff_too_large_holds` (fake `gh pr diff` exits
    1 with `HTTP 406`);
  - `test_unknown_mergeable_bounded` (5× `UNKNOWN` → `hold 5`, and `UNKNOWN` then `MERGEABLE` →
    pass; patch the sleep to 0); `test_failed_check_holds`; `test_no_checks_passes`;
  - `test_walk_at_old_head_holds` → `hold 7`; `test_unaudited_holds`; `test_valid_row_holds`;
    `test_refuted_blocking_row_holds`; `test_gap_naming_ac_holds`;
    `test_gap_naming_unwalked_device_passes`; `test_polish_and_refuted_rows_pass`;
  - `test_missing_image_holds` → `hold 8`; `test_comment_for_old_head_holds`;
    `test_empty_screens_list_holds`;
  - `test_smoke_none_outside_ui_paths_passes`; `test_smoke_none_touching_ui_paths_holds` →
    `hold 9`; `test_no_ui_paths_row_holds`; `test_neither_cases_nor_smoke_none_holds`;
  - `test_gh_failure_is_hold_0` → exit 2, `hold 0 gate error: …`.
- [ ] **Step 2:** Run `cd scripts && python3 -m unittest -v test_adw_merge_gate`.
  Expected: FAIL, script not found.
- [ ] **Step 3: Implement** `check`. Profile tables: the first cell with `**` and backticks stripped
  is the role, compared lowercase. Unescape `\|` in a cell before compiling a regex. Globs: `**` →
  `.*`, `*` → `[^/]*`, anchored. The artifact exclusion pathspec's `':!<glob>'` items become
  excluded globs.
- [ ] **Step 4:** Run the tests. Expected: PASS. Then run the whole suite.
- [ ] **Step 5:** Commit `adw-merge-gate: the auto-merge gate's conditions`.

### Task 11: `adw-merge-gate.py trial` and `discard`

**Files:**
- Modify: `scripts/adw-merge-gate.py`, `scripts/adw-run-clean.py` (the worktree name list in its
  docstring and its matcher)
- Test: `scripts/test_adw_merge_gate.py`, `scripts/test_adw_run_clean.py`

**Interfaces:**
- Produces:
  - `trial --checkout <path> --pr <N> --slug <slug> --base <branch> --head <sha>` prints
    `base unmoved` (exit 0), `tree <path> base <sha>` (exit 0), or `hold 6 overlap: <files>` /
    `hold 6 conflict: <files>` (exit 1). The tree is a detached worktree named
    `adw-trial-<slug>-pr<N>`, beside the run's unit worktrees, with the base merged in.
  - `discard --checkout <path> --tree <path>` removes it. It never uses `--force` on a tree with
    changes other than the merge.

- [ ] **Step 1: Write the failing tests** in temp repos with a bare remote:
  `test_unmoved_base`; `test_moved_disjoint_files_gives_tree` (the tree holds both sides, and the PR
  head ref is unchanged); `test_overlap_holds` (both sides touch `a.txt`); `test_conflict_holds_and_
  leaves_no_worktree`; `test_discard_removes_tree`; and in the run-clean tests,
  `test_trial_worktree_is_cleaned`.
- [ ] **Step 2:** Run both test modules. Expected: FAIL.
- [ ] **Step 3: Implement.** Fork = `git merge-base origin/<base> <head>` after `git fetch origin`.
  Moved = `origin/<base>` ≠ fork. Overlap = `git diff --name-only <fork> origin/<base>` ∩
  `git diff --name-only <fork> <head>`. Merge with `git -C <tree> merge --no-edit origin/<base>`. On
  a conflict, abort, remove the worktree, hold.
- [ ] **Step 4:** Run both modules, then the whole suite. Expected: PASS.
- [ ] **Step 5:** Commit `adw-merge-gate: trial the base merge without moving the head`.

### Task 12: The reader keeps the new rows

**Files:**
- Modify: `scripts/adw_analyze/github.py` (`ROWS`, line 15; `BLOCK_LINES`)
- Test: `scripts/test_adw_analyze_github.py` (class `Block`)

- [ ] **Step 1: Failing test** `test_verified_and_merge_rows_parse`: a block with all 11 rows today,
  plus `verified <sha>` and a `merge hold 7 — … · at abc1234` row placed after `smoke`. Both appear
  in the parsed dict with their values.
- [ ] **Step 2:** Run `cd scripts && python3 -m unittest -v test_adw_analyze_github`.
  Expected: FAIL, `verified` missing.
- [ ] **Step 3:** Add `"verified", "merge"` to `ROWS`. Raise `BLOCK_LINES` to `20`.
- [ ] **Step 4:** Run the module, then the whole suite. Expected: PASS.
- [ ] **Step 5:** Commit `adw-analyze: read the verified and merge rows`.

### Task 13: Contract — the flag

**Files:**
- Modify: `commands/adw-core.md` §2 (99–133), §7 approval block (406–433)
- Modify: `commands/adw-init.md` (frontmatter 2; Input 20–21; triage item 9, 168–176; gate verbs
  238–262; spec-writer preamble 307–312; validation 446–457)
- Modify: `install/stubs/adw-init.md` (line 2)
- Modify: `commands/adw-build.md` Phase 0 step 4 (128–133)

- [ ] **Step 1: Failing check.** `grep -c 'merge: auto' commands/adw-core.md commands/adw-init.md
  commands/adw-build.md` prints `0` for each file.
- [ ] **Step 2: Edit:**
  - §2: the spec header line from the Shared formats. Rules: intent-wide like `base:`, missing means
    `hold`, never `auto` when the base is the production branch. Line 132: the six required fields
    stay six.
  - `adw-init` Input: parse `--hold` before the intent text. It sets `merge: hold`.
  - Triage item 9 proposes `merge:` beside `base:`: `auto` when the base is the default base and
    the profile's `auto-merge default` row says `on`, else `hold`.
  - The approval surface always prints the `merge` line. The gate verbs gain `merge auto` and
    `merge hold`. `approve` on a surface that prints `merge auto` is the owner's consent for that
    intent's merges (§6, Task 14).
  - The spec-writer preamble lists `merge:` among the header lines. The validation list checks every
    unit carries the same `merge:` value.
  - Phase 0 step 4 refuses: `merge:` on some units but not all, differing values, a value that is
    not `auto` or `hold`, and `auto` with a production-branch base.
  - Frontmatter and stub `Usage`: `/adw-init [--hold] <intent>`. Both lines stay identical.
- [ ] **Step 3:** Re-run Step 1. Expected: each ≥ 1. Then walk `/adw-init --hold fix the logo` as a
  sonnet reader, in writing, to the surface it prints.
- [ ] **Step 4:** Commit `adw: merge: auto | hold — the per-intent flag`.

### Task 14: Contract — the gate and the merge (then PR B)

**Files:**
- Modify: `commands/adw-build.md` top (66–88), Phase 0 steps 2, 5, 7 (115, 134–144, 203–208),
  §3.4 (776–856), §3.7 (1077–1130), §3.8 heading and flags (1133, 1148–1154, 1236–1243, 1297–1307),
  Phase 4 (1421–1438), Phase 5 (1567)
- Modify: `commands/adw-core.md` §1.1 (88–89), §4 (284–285), §5 (293–299), §6 (321–363), §7
  (495–499, 572–616), §7.1 (731–732)
- Modify: `commands/review-core.md` §8 (282–294); `commands/pr-ready.md` (24, 619–620);
  `commands/adw-dispatch.md` (141); `commands/adw-init.md` (547–550)
- Modify: `docs/00-design.md` §1 (59, 67), §3.5 (342), §4.1 (448, 456–464), §4.7 (673), §6
  (863–869), §7 (973), plus a revision entry in the archive's style
- Modify: `docs/repo-profile-EXAMPLE.md` §3 (97–107), anchor table (25–26)

**Interfaces:**
- Consumes: Task 10's `check`, Task 11's `trial` and `discard`, the evidence rows, the labels.

- [ ] **Step 1: Failing check.** `grep -c 'adw-merge-gate.py' commands/adw-build.md` prints `0`, and
  `grep -c 'did not open this session' commands/adw-core.md` prints `1`.
- [ ] **Step 2: Session rule (C13).**
  - `adw-build` top, 66–80: the merge rests on durable facts: the flag, the `verified` row, the walk
    line and the labels. Any run building that slug may merge when the gate passes, after a
    compaction or in a new session. The `verified` row lets a chain merge a `ready` sub-PR, or carry
    a `blocked` one with a verified head, the same way. A run never merges a PR of another slug.
    The owner who is testing a PR adds `adw:hold`.
  - Never list, 84–88: drop "merge a PR whose provenance this session did not establish". Change the
    first item to: merge into the production branch, or into the default base without the gate.
  - Phase 0 step 7 (203–208): a still-open PR of this slug goes through §3.7 like any other.
  - `adw-core` §1.1, §6 (325–326, 349–350) and §7.1 (731–732) say the same. `adw-init` 547–550 says a
    compaction no longer leaves a `ready` sub-PR to the owner.
- [ ] **Step 3: Labels.** `adw-core` §5 adds the two creates from the Shared formats, and "MUST list
  all four". Phase 0 step 2: "the four idempotent creates".
- [ ] **Step 4: §3.4.** Add the `verified` and `merge` rows from the Shared formats. Line 855: with
  `merge: auto`, the run owns the residual semantic-conflict risk through §3.7's trial. With `hold`,
  the human merge gate still owns it.
- [ ] **Step 5: §3.7.**
  - `ready` row (1081): write `verified <$VSHA>`. Then, for an independent or final PR, the gate.
    For a sub-PR, the existing procedure.
  - **The gate**, after §3.8 and its screenshot relay. Run `check`, in one Bash call with `timeout:
    600000`, with every unit spec path of the intent. On `hold`, write the `merge` row, leave the PR
    open, and stop. On `pass`, run `trial`. On `tree`, run the §5 gates the PR's diff obligated
    (`repo-profile` §6) in that tree, with `origin/<base>` as the base. On a repo whose §21 has a
    Lock row, take the lock first and release it after, waiting as §3.8's Queued step does. Any red
    gate → `hold 6 gate <name> red`. Then `discard`.
  - **The merge, two Bash calls.** First: `gh pr view <n> --json baseRefName,headRefOid,labels`
    shows the base, the head equal to `$VSHA`, and no `adw:hold`. Second, alone: `gh pr merge <n>
    <flag> --match-head-commit <full sha>`. The flag comes from `repo-profile` §3's merge convention
    (`squash` → `--squash`). No `--auto`, no `--delete-branch`. The `description` names the base.
  - Then confirm with `gh pr view <n> --json state,mergedAt`. Add `adw:auto-merged`. Write
    `merge merged …`.
  - **A denied merge call** on an independent or final PR is a hold: `merge hold call — denied`, no
    `adw:blocked` label. The report line names the command for the owner to run. Sub-PR denial text
    is unchanged.
- [ ] **Step 6: Phase 0 step 5 and §6.**
  - Phase 0 step 5's EXCEPT clause, and `adw-core` §6's opening (321–330): a PR into the intent's
    base or the default base may merge when the spec says `merge: auto` and §3.7's gate passes. The
    production branch never.
  - The standing no-merge paragraph (337–343): an approved `merge auto` line is the owner's word for
    that intent. A standing line still binds an intent whose flag is `hold`.
  - `adw-core` §4 (285): "+1 merge consent" only for a `hold` intent.
- [ ] **Step 7: Report.**
  - `adw-core` §7: states ordered merged → ready → blocked → failed → unbuilt, "five keywords".
  - The `merged` line: `merged   #NNN  <desc> — <units> · walk clean · screens <url> · polish <p> ·
    refuted <r> · ⏱ <N>m`.
  - A `ready` line that the gate held ends `· held <n>: <reason>`.
  - `Next:` with nothing left for the owner: `Next: when you test, gh pr list --state merged
    --label adw:auto-merged`.
  - §7 consent sentence (495–499): the PR to `base:` needs the owner's consent, which the approved
    `merge auto` line gives.
  - `adw-build` Phase 4 (1421–1438) and Phase 5 (1567) match.
- [ ] **Step 8: Other consent sites.**
  - `review-core` §8 (284, 292): merge consent is the word "merge", or an approved `merge auto`
    line, the latter for `adw-build` §3.7's gate only.
  - `pr-ready` 24 and 619–620: the same exception, cited.
  - `adw-dispatch` 141: "…unless the Intent says so in those words, or `adw-build` §3.7's gate
    merges it."
  - §3.8's heading and line 1148: "the PRs the human merges" → "independent and final PRs".
  - The row table (1236–1243) gains: a gap or `blocking` row reported here can still hold the merge
    (§3.7).
- [ ] **Step 9: Docs.** `00-design.md`: each listed sentence states the auto-merge exception.
  "Not in v2: auto-merge" becomes "auto-merge only behind adw-build §3.7's gate; never into the
  production branch". Add the revision entry. EXAMPLE §3: the three rows, in the Shared formats,
  with the web repo's values as the example. Anchor table: §3 also used by `adw-build §3.7`.
- [ ] **Step 10:** Re-run Step 1. Expected: `≥1` and `0`. Then:
  `grep -rn 'did not open this session\|provenance this session' commands/` — each hit is either
  the sub-PR head re-check or archive text. Run `check-anchors.py origin/main HEAD`. Expected: no
  `NEW` line. Run the suite.
- [ ] **Step 11:** Commit `adw-build §3.7: the merge gate`. Ask for push. Open PR B with `predicts`
  lines for `owner.wait_share.v1` (down), `time.intent_lead_hours_median.v1` (down),
  `owner.halts_per_merged_pr.v1` (down) and `outcome.reverts.v1` (no worse). Run the
  `reviewing-contract-prs` skill, apply what survives, stop.

---

## Part 4 — This repo, PR C: follow-ups

### Task 15: `--followup`

**Files:**
- Modify: `commands/adw-init.md` (frontmatter, Input, triage, the gate); `install/stubs/adw-init.md`
- Modify: `commands/adw-core.md` §1.1 (a merged intent is not live), §6, §7

- [ ] **Step 1: Failing check.** `grep -c -- '--followup' commands/adw-init.md` prints `0`.
- [ ] **Step 2: Edit.**
  - Input parses `--followup <slug> <text>`. `<slug>` must name a merged intent. The new slug is
    `<slug>-f<k>`, where `<k>` is one more than the highest `-f<k>` among the repo's branches and
    PRs. The reader counts the false-pass rate from that suffix.
  - Triage runs as usual. The gate is skipped only when triage finds one D0 unit, nothing in `needs
    you`, and no `⚠` line. Otherwise it stops at the gate as usual.
  - On a skip, the run prints the `merge` line when it starts. The typed line is consent to build
    and to merge under §4.1's rules (C21). `adw-core` §6 and §7 say so.
  - Usage: `/adw-init [--hold] [--followup <slug>] <intent>`, the same in the stub.
- [ ] **Step 3:** Re-run Step 1. Expected: ≥1. Walk `/adw-init --followup some-slug logo bigger` as
  a sonnet reader, in writing, for a D0 and a D1 triage.
- [ ] **Step 4:** Commit `adw-init: --followup skips the gate for one small unit`. Ask for push, open
  PR C, run `reviewing-contract-prs`, stop.

---

## Part 5 — This repo, PR D: the reader's numbers

### Task 16: Auto-merge metrics

**Files:**
- Modify: `scripts/adw_analyze/metrics.py` (registry), `scripts/adw_analyze/report.py`
- Test: `scripts/test_adw_analyze_metrics.py`

- [ ] **Step 1: Failing tests:**
  - `test_auto_merged_share`: four independent or final ADW PRs with `merge` rows, two `merged` → `0.5`.
  - `test_auto_merge_false_pass`: an auto-merged slug with a `<slug>-f1` intent, or a revert, within
    7 days counts once.
  - `test_holds_by_condition_table`: `report.md` lists hold counts per `<n>`.
- [ ] **Step 2:** Run `cd scripts && python3 -m unittest -v test_adw_analyze_metrics`. Expected: FAIL.
- [ ] **Step 3:** Add `outcome.auto_merged_share.v1` and `outcome.auto_merge_false_pass.v1` to the
  registry, with a definition, kind, min_n and source as every entry carries. Add the holds table
  to `report.md`.
- [ ] **Step 4:** Run the module, then the whole suite. Expected: PASS.
- [ ] **Step 5:** Commit `adw-analyze: auto-merge share, false passes, holds per condition`. Ask for
  push, open PR D with `predicts  none — adds measures; no metric moves`, stop.

---

## Part 6 — Web repo, PR W2: the web walk

### Task 17: Web §21 and a case-list `/e2e-sweep`

Design §4.8. The native skill is the model: `--cases`, `--screens`, `--devices`, `--lanes L1`, one
result file, a verify script.

**Files:**
- Modify: web `.claude/commands/e2e-sweep.md` (argument line 4; modes 26–37; L1; outputs 628–647)
- Modify: web `scripts/e2e-sweep-verify.sh`
- Create: web `scripts/e2e-sweep/cases-check.sh`, `scripts/e2e-sweep/probe.cjs`,
  `scripts/e2e-sweep/lock.sh`
- Modify: web `.claude/repo-profile.md` §3 (89–96), new §21

**Interfaces:**
- Consumes: the Shared formats; Task 3's `--ai-stub`.
- Produces: `/e2e-sweep <N> --cases <path> --screens <path> --devices desktop,phone-width --lanes L1`,
  unattended, Playwright only. Result: `SUMMARY.md` with the native row ids (`D`, `G`, `S`, `P`,
  `I`) and one `- [x] AC-<n> pass|F<n>|blocked [<devices>]` row per case in `findings-L1.md`.

- [ ] **Step 1: Failing verify cases.** A sweep fixture missing `SCREEN-1-phone-width.png` → verify
  exits non-zero and names it. A case with no row on a device → non-zero. A complete fixture → 0.
- [ ] **Step 2:** Run `bash scripts/e2e-sweep-verify.sh <fixture> 390 --final --cases <c> --screens <s>`.
  Expected: FAIL (flags unknown).
- [ ] **Step 3: Implement.**
  - `cases-check.sh`: the native one's contract (exit 0 prints ids, exit 2 a reason).
  - `probe.cjs`: per device, one Playwright click that must change the page, then a read that proves
    it did. Exit non-zero means not runnable.
  - `lock.sh take|release <slug>`: `$HOME/.cache/plantoes-e2e/lock`, noclobber, the lock lines,
    exit 3 when held.
  - In `e2e-sweep.md`: the case-list mode skips the Haiku lanes and the Chrome pass (the existing
    DEGRADED path). The orchestrator walks each case in Playwright at 1440×900 (`desktop`) and
    390×844 (`phone-width`). It captures every listed screen on each device to `screens/`. It writes
    the result rows. It runs `test-env.sh up --scratch-db --ai-stub`. A second account is a new
    browser context signed in with another pair from the `[test-env]` block.
- [ ] **Step 4:** Run the verify cases. Expected: PASS.
- [ ] **Step 5: Profile.** §21 with every row §3.8 checks, built like the native rows: Launch,
  Cases check, Devices (`desktop`, `phone-width`; no `Device` line → both), Driver probe, Data,
  Wait test (own release), Result, Evidence, Audit, Max minutes (`60`), Abandon, Build floor
  (`true`, with the measured peak memory of one `npm run build` beside a running stack as the
  reason), Second account, Lock. §3:
  - `auto-merge default`: `on`;
  - `merge-protected paths`: `` `.claude/**` `.github/workflows/**` `firebase.json` `.firebaserc`
    `api/drizzle.config.ts` ``;
  - `UI paths`: `` `src/**` `packages/shared/**` `index.html` `public/**` ``.
  - §6: a trial tree (`adw-build` §3.7) obligates the audit gate, so `check-migration-order.mjs`
    runs on the merged tree. A migration whose `when` is at or below the base's maximum goes red
    there, as design §4.6 requires.
- [ ] **Step 6: Live check.** On a real open web PR with cases, run Launch as the relay would. Then
  run Wait test, Result, Audit and Abandon. Expected: a `SUMMARY.md`, images in `screens/`, Audit
  exit 0, the lock released, the slot down.
- [ ] **Step 7:** Commit `feat(e2e-sweep): case-list walk for adw-build §3.8`. Ask for push, open web
  PR W2, run `/code-review`, stop.

---

## Part 7 — Live

### Task 18: First live run — needs the owner

- [ ] **Step 1:** Confirm the owner's prerequisites (design §6): the owner changed the auto-mode
  rule so §3.7's merge call is allowed, and the web project memory has the carve-out (done
  2026-11-02). No run edits either.
- [ ] **Step 2:** The owner runs one small native intent with the default `merge auto`.
- [ ] **Step 3:** Expected: a `## Screens` list, a screens comment that renders on the phone, a
  `merge` row, and either `merged` with `adw:auto-merged` or `ready … held <n>: <reason>`. A hold is
  a valid result. A merge with a missing image, a gap row or a stale walk is a defect in Task 10:
  stop and fix.
- [ ] **Step 4:** Record the result in the ledger, and the first hold reasons for stage 2.
