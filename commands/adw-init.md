---
description: "ADW entry point: intent → triage → human-approved unit cut → per-unit specs/plans → builds them. `approve` at the gate runs /adw-build in the same session; `specs only` stops after the specs. Usage: /adw-init <intent>"
---

# /adw-init — from intent to contract, and on into the build

> **Phase 0 reads [`adw-core.md`](adw-core.md) first** — artifact paths (§1), spec-header
> schema (§2), depth ladder (§3), packaging rules (§4), approval-surface and handoff templates (§7), dispatch tier
> (§8 — binds every `Agent` call this file makes, the critical passes included), the contract
> source (§9). **Then the consuming repo's `.claude/repo-profile.md`**, which holds every repo-specific
> path, branch, gate and trap domain this file cites as `repo-profile §N`. Design rationale: the
> design doc `repo-profile §2` names, §3. This file owns only the init-specific flow.
>
> **This file lives in the `adw` repository and is fetched, not copied** (adw-core §9). It is
> repo-agnostic: every value that could differ between repos is in `repo-profile.md`.

**Input:** `$ARGUMENTS` — the intent: free text, a bug list, a report excerpt, a Trello
ref. Empty → ask for the intent and stop.

**Hard rules**
- **Phases 0–5 are documents only.** No code edits, no branches, no worktrees — every
  phase in this file runs in the main tree, where all skills exist. **This rule ends at
  Phase 5 step 3**, which hands control to `/adw-build`; that file owns branches,
  worktrees and code, under its own rules. The boundary is the handoff, not the end of
  the session — do not read this rule as a reason to stop there. (It is stated this way
  because the v2.15 contract said "documents only" at the top and "continue into build"
  at the bottom, and the top won every time.)
- Nothing expensive runs before the human approves the cut — the per-unit fan-out can
  cost more than the implementation it produces; burning it on a mis-cut is the failure
  the gate exists to prevent. Since v2.16 the same approval also releases the build, so
  the cut is the only gate in front of the whole run: everything the human might act on
  is a `QN` or a `⚠` line, never `fyi` (adw-core §7).
- Skill references allowed in produced artifacts and dispatched prompts: plugin skills
  (`superpowers:*`) and tracked commands only. Repo-local symlinked skills
  (`.claude/skills/*` → `.agents/`) are absent in worktrees — a spec or plan that
  references one hands `/adw-build` an unresolvable dependency.
- Specs/plans stay UNCOMMITTED in the main tree — `/adw-build` lands each unit's spec
  (and its plan file, D3 only) inside that unit's PR and then deletes the main-tree originals (adw-core §1,
  adw-build §3.1); init never commits them, and nothing lingers after a run.

## Phase 0.5 — new intent or extension? (before any dispatch)

**Pin the contract first:** `CONTRACT_SHA=$(git -C <cache> log -1 --format=%h)` — the loader stub
already fetched it (adw-core §9). Substitute the value as a literal; it goes on the handoff and,
after `approve`, is the value `/adw-build` carries. There is nothing to check: fetching before
reading is what the old freshness check could only report on after the fact.

**Then look for a live intent this belongs to** (adw-core §1.1) — the owner arrives with
"three more bugs I found testing", not with a slug, so detection is the pipeline's job:

```bash
# <specs-dir> and <legacy-specs-dir> are repo-profile §2's values
git status --porcelain <specs-dir> <legacy-specs-dir> | grep '^??'   # UNBUILT specs = in-flight
ls -d <specs-dir>/????-??-??-*/ <legacy-specs-dir>/????-??-??-*/ 2>/dev/null   # both roots
gh pr list --state all --limit 60 --json number,title,headRefName,state,baseRefName \
  --search "adw in:title"                                            # candidate slugs only
```

An intent is **live** while any adw PR for its slug is open, its spec folder still holds
untracked unit specs, or a **non-default** `base:` is unmerged (adw-core §1.1 — a merged
folder returns tracked at the next `git pull`, and the default base is never merged, so neither
bare existence nor a default base ever expires). For each live intent, compare its surface
against the new issues — same files, same feature directory, same base. On a match, resolve
prior state before triage:

- **unit ids**: every id ever used, parsed from PR titles (`[adw <slug> u2+u3]`) plus any
  spec files present — re-enumerate for the matched slug with adw-core §5 resume's query,
  never off the capped `--search` listing above (it sorts by best match, so truncation is
  arbitrary; a low `max` reuses an id and breaks resume). New units start at `max + 1`.
- **`base:`** and packaging topology: from the specs (main tree, else
  `git show origin/<base>:<spec path>` — merged units' specs live in their merged PRs).
- **per-unit state**: merged · open PR (`#NNN`) · unbuilt. An open unit's spec is on its
  own branch only — `git show origin/adw/<slug>-uNN:<spec path>` (adw-core §1.1).
- **spec folder**: the existing dated folder — recover its name from **both roots**
  (`repo-profile §2`), and remember which one answered: an intent born before the artifact-root
  cutover keeps its legacy path for life (adw-core §1).
  ```bash
  for root in <specs-dir> <legacy-specs-dir>; do
    root=${root%/}
    git ls-tree -d --name-only "origin/<base>:$root" 2>/dev/null \
      | grep -E -- '^[0-9]{4}-[0-9]{2}-[0-9]{2}-<slug>$' | sed "s|^|$root/|"
  done
  ```
  Anchor the date — a bare `-<slug>$` also matches `<date>-<other>-<slug>`. `2>/dev/null`
  because `ls-tree` errors on a root that does not exist in that commit, which is the normal
  case for one of the two. **Zero hits and the folder is not in the main tree → it is a new
  intent, not an extension.** Two hits across the two roots is the same refusal as two dated
  folders in one root (adw-core §1.1): one slug lives in exactly one root. A flat-born intent
  has no folder: create one at its BIRTH date, **under the root that intent already uses**, and
  leave the flat spec in place. NEVER mint a second dated folder for one slug.

Extension is **proposed at the approval surface, never assumed** — the `extends` line states it and the verb
menu still governs. A different `base:`, or a different subject, is a new intent: say so in
one `fyi` line and cut fresh. When nothing matches, this phase is silent.

## Phase 1 — triage (one cheap agent)

Stamp **T0** here (`date +%s`, adw-core §7.1) — before the dispatch, so triage counts as
machine time. T1/T2 bracket the Phase 2 gate. **T3 is stamped at each `⏱ run` print, not
once per run** — on a chained `approve` the handoff's `⏱ run` is a PARTIAL (init only) and
the build's run report stamps its own T3 over the same continuing series (adw-core §7.1).
Only `specs only` makes the handoff's T3 the run's last.

Dispatch ONE read-only subagent (Explore-type; it must not write) with **`model:
sonnet`** — "cheap triage" is contract, not vibes: an unpinned dispatch inherits the
session's most expensive tier (run-1 spent 10.5 min of top-tier triage on a one-unit cut):

> Read the design doc named in `.claude/repo-profile.md` §2, its §3.1–§3.2, and
> `.claude/commands/adw-core.md` §2–§4. Read `.claude/repo-profile.md` itself first.
> Intent: `<intent verbatim>`. Explore the repo read-only. Propose:
> 1. the unit cut per §3.1 — vertical by behaviour; a layer cut only when one layer
>    contains the entire behaviour; the rule is symmetric (merge freely — five copy fixes
>    are one unit); sweep-shaped work may legitimately be ONE unit;
> 2. a depth per unit (D1–D3 per adw-core §3);
> 3. packaging per adw-core §4, with `after` edges — remember: a unit that reads another
>    unit's output is NOT independent, no matter how disjoint the file lists look;
> 4. a `verify` COMMAND per unit (adw-core §2 rules — never a prose sentence);
> 5. spec criteria covered by no unit — mandatory, print `none` explicitly if none;
> 6. **three separate lists, split by you, not by the renderer** — questions, hazards, fyi.
>    A **question** is anything the owner must ANSWER (each becomes a numbered `QN` at the
>    approval surface, adw-core §7) and ships with a recommended default; a
>    "confirm X before …" item is a question, never a hazard and never fyi. A **hazard**
>    is anything the owner might act on without being asked: files shared between units,
>    scope=future / fan-out hazards, gate-visibility gaps, uncharted territory — these
>    become `⚠` lines and are the ONE thing that always prints, because the approval
>    surface is brief by default and `approve` builds (adw-core §7). Everything else is
>    **fyi**: decisions you already took with their default applied, underspecification
>    read-ins, boundary calls. When a line could be a hazard or fyi, it is a hazard;
> 7. gate coverage — for each unit, name the trustworthy gate that can see its
>    correctness (integration test, e2e spec, tsc/grep proof); a unit with none gets a
>    `⚠` line (design §2.2: rollout is scoped by gate coverage — the approval surface is
>    where the human decides that targeting, and they cannot decide it from a line the
>    brief surface hides);
> 8. depth rationale — one line per unit (`why-<word>`, the §3 depth word), naming which
>    D1 criteria (adw-core §3) hold or fail. A single-unit intent meeting every D1
>    criterion is proposed `express` (D0) when D0 is active (adw-core §3 status line) —
>    then include the draft
>    flat spec (header + body per adw-core §2) in the proposal itself; its code
>    snippets follow the repo comment rule (`repo-profile §2`): one terse line + spec ref,
>    never a multi-line rationale comment (D0 skips the fan-out, so this is the
>    draft's only exposure to that rule);
> 9. base — when the intent names or requires a branch other than the default
>    (`repo-profile §3`) — a feature/release/chain branch the broken code only exists on —
>    propose `base: <branch>`
>    (adw-core §2) after confirming it exists on origin; when the right base is itself
>    doubtful (e.g. forking off another intent's still-open chain), return it as a
>    question, not a `⚠` or `fyi` line.
> Return the structured proposal, nothing else.

**Extend mode appends this to the prompt** (Phase 0.5 matched a live intent) — without it
the triage re-diagnoses shipped code and mints blind neighbours:

> You are EXTENDING intent `<slug>`, not starting one. Prior units: `<id → title → state
> (merged | open #NNN | unbuilt)>`. Their specs: `<paths — main tree for unbuilt,
> `git show origin/<base>:<path>` for merged, `git show origin/adw/<slug>-uNN:<path>` for
> open ones>`. Read them before proposing anything.
> `base:` is fixed at `<branch>`; new unit ids start at `u<max+1>`. Classify EACH new
> issue before cutting:
> (a) regression in a MERGED unit → new unit whose spec cites it and states what the
> original missed; (b) inside an UNBUILT unit's scope → do NOT mint a unit, return
> `amend: uNN` with the delta (that unit's spec gets revised — one fewer PR);
> (c) inside an OPEN-PR unit's scope → new unit with `after: [uNN]`; that PR is the
> owner's and is never amended by this run; (d) genuinely new → new unit.
> Also report any semantic dependency between a new unit and an unbuilt/open prior unit —
> shared file, shared query, one's design assuming the other's absence. That class is
> invisible to every gate and is the whole reason extension beats a fresh slug.

Render the **approval surface exactly** (adw-core §7) from the proposal and end the turn on the verb menu.
Do not proceed without an answer.

## Phase 2 — the human gate

- `approve` → freeze the proposal (units, depths, packaging, `after`, `verify`) → Phase 3,
  then Phase 5 prints the handoff and **continues straight into `/adw-build <slug>` in the
  same session, same turn** (Phase 5 step 3 — that step, not this sentence, is what
  executes it). Gated on a clean exit: a handoff carrying a non-empty `needs you` stops
  there exactly as `specs only` would — never auto-default a pending critical-pass
  question straight into build.
- `specs only` → as `approve`, minus the last step: Phase 5 prints the handoff and the run
  ends. This is the verb for reading the specs before any code exists.
- `detail` → re-render the approval surface with its `detail` and `fyi` blocks appended
  (adw-core §7). Not an exit — the gate stays open.
- `re-cut "<instruction>"` → send the instruction to the SAME triage agent
  (SendMessage — context intact), re-render the approval surface.
- `regroup` / `depth` → apply mechanically, re-render the approval surface.
- `new intent` (extend mode only) → drop the extension, cut a fresh slug, re-render the approval surface.

Any number of rounds. Only `approve` / `specs only` exits the gate.

**`approve` was the stopping verb until v2.16 and is now the building one.** The rename is
deliberate: the round-trip existed so the human could read specs, and in practice they
approved a cut and then had to type a second command that the handoff's own `Next:` line
told them to type — a step no one skipped on purpose. The consent that moved with it is
real, so the approval surface names it (`approve → cut + build`) and every hazard is a
`⚠` line the brief surface still prints. The merge carve-out (adw-core §6) does not move.

Stamp **T1** immediately before each approval-surface print and **T2** on each answer (adw-core §7.1);
across re-cut rounds the gate total accumulates and the re-render itself is machine time.

## Phase 3 — fan-out (parallel, one subagent per unit)

Dispatch all unit agents in a single message (they are independent — documents only, main
tree, distinct files). Each prompt is composed from the frozen proposal:

**Pin each unit agent by the unit's own `depth:` (adw-core §8):** `model: opus` at D3,
`model: sonnet` at D0–D2. Depth is per unit, not per intent — a mixed intent dispatches
mixed tiers in the same message, which is correct and not a mistake to tidy up. Whichever
tier a unit drew, its spec still goes through the same critical passes below.

**No wave barrier.** If the fan-out is wider than the harness will start at once, dispatch
each remaining unit the moment ANY slot frees — never wait for the whole batch to return.
Run-7 dispatched 4 of 6, then held u5+u6 until the LAST of the four came back: two slots
sat idle from 22:22 to 23:19 waiting on an 82-minute straggler, and the spec phase took
136 min instead of ~85. The straggler is unpredictable by construction (it is the unit
with the most to discover), so blocking on it is a pure loss every time.

**Common preamble (every unit):**

> You are producing the contract for unit `uNN` of intent `<slug>`. Write documents only —
> never code, never a branch. Spec path: `<exact path per adw-core §1>`. The spec MUST
> open with the exact header block (adw-core §2):
> `unit / intent / depth / packaging / after / verify` — values as approved. The spec body
> states: the problem, the change, acceptance criteria, and (bugs) root cause with
> evidence. Reference only plugin skills (`superpowers:*`) or tracked commands.
> Code snippets in the spec/plan MUST follow the repo comment rule (`repo-profile §2`): one
> terse line + spec ref, never a multi-line rationale comment — the implementer copies
> snippets verbatim, so a violating snippet ships a forbidden pattern and buys a review
> round-trip (run-1's only review finding was deleting a plan-dictated comment block).

**Extend mode:** an `amend: uNN` item is not a new unit — dispatch its agent against the
EXISTING spec (unbuilt by construction, so the main-tree file is there) to fold the delta
in, keeping the unit id, header and any plan. New units get the normal preamble plus the
prior-unit table, so their specs can cite what shipped.

**By depth:**
- **D0 (adw-core §3):** no fan-out — the triage agent's draft IS the spec;
  write it to the flat path, then straight to Phase 4. No plan, no critical pass.
- **D1 (bug):** "Use superpowers:systematic-debugging to reach a reproduced root cause —
  no fix without a failing observation; your diagnosis is load-bearing, the spec goes
  straight to build. Then write the spec."
- **D2:** "Bug → superpowers:systematic-debugging; feature → superpowers:brainstorming.
  Write the spec. It MUST close with a `## Implementation` section (adw-core §3) — a
  numbered table of exact files, exact changes and exact commands, following
  superpowers:writing-plans' discipline (bite-sized steps, no placeholders) but written
  into the spec, NOT a second file. Do not create a plan file at D2."
- **D3:** "superpowers:brainstorming first; record the chosen direction and rejected
  options as a Design section in the spec. Then the spec. Then a separate plan file at
  `<exact plan path per adw-core §1>` following superpowers:writing-plans (bite-sized
  steps, exact files, exact commands, no placeholders). D3 is the only depth that gets
  its own plan file."

**Two `superpowers` defaults ADW overrides — state both in the D2/D3 prompts, because the
skill text asserts them and the skill text is what the agent has at the cursor:**

- **Path.** `writing-plans` saves to `docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md` —
  wrong root AND wrong filename shape.
  ADW's path is adw-core §1's, with the intent slug and unit id. Its own text grants this
  ("user preferences for plan location override this default"), but say it explicitly.
- **The `REQUIRED SUB-SKILL` header.** `writing-plans` mandates a plan header telling the
  reader to execute it with `superpowers:subagent-driven-development` or
  `executing-plans`. **ADW uses neither** — adw-build §3.1 dispatches its own implementer
  and keeps it across fix cycles. So the header is a false instruction that ships into a
  PR and merges: **186 of 230 plan files on disk carry it.** Replace that line with
  `> **Executed by:** /adw-build §3.1 implementer.` and keep the rest of the header
  (Goal / Architecture / Tech Stack / Spec), which is useful.

**`brainstorming`'s `<HARD-GATE>` cannot be satisfied inside the fan-out** — it forbids
implementation until "your human partner has approved", and a unit agent has no human. That
approval already happened, at the approval surface (adw-core §7), which is why the fan-out
runs at all. Say so in the prompt: "the human gate for this unit is already passed; produce
the artifact and stop — do not ask for approval, and do not write code." Also pin the path:
brainstorming classifies spike/bounded/architectural on its own, which is a second depth
ladder that can disagree with §3's. **§3's depth wins; the unit's `depth:` is not
re-litigated by the authoring agent.**

**Artifact budget (D2/D3, append to the prompt) — proportional first, capped second:**
"Artifacts scale with the change, not with the form. **Every artifact this unit produces
must together be shorter than the diff they produce** — measured against your own estimate
of that diff (nothing upstream records one; adw-build §3.5 measures the real thing at PR
open). At D3, additionally: the spec shorter than the plan. That ratio is the real bound.
Behind it sits a flat ceiling — an **advisory guard rail** against a wrong estimate, never a
target to fill:

| Depth | Artifacts | Guard rail | Hard stop (2×) |
|---|---|---|---|
| D0/D1 | spec | ≤200 | >400 |
| D2 | spec incl. `## Implementation` | ≤250 | >500 |
| D3 | spec + plan | ≤200 / ≤300 | >400 / >600 |

Clearing a guard rail by a margin is reported, not paid for, and nothing load-bearing is
ever cut to reach it. At a **hard stop** the unit is mis-cut rather than merely dense: report
it as ONE `needs you` split question instead of writing past it. Count the artifact you will
COMMIT, not a draft — critical-pass revisions land after the count. Check the ratio and your
`wc -l` **once**, last, on the final text; re-counting while you draft is the tell that the
number has become the target this paragraph just said it is not. Write the artifact, then
count it. writing-plans' no-placeholder rule binds decisions, interfaces, ACs and the
genuinely tricky diffs — NOT full-code transcription: the build-side implementer re-derives
routine code from ACs cheaply, so transcribing the implementation pays for the code twice."

**Why the ratio leads and the constant follows.** A constant fires on size, and size is
exactly what a hard unit legitimately has — it flagged a genuine routing change while
passing 451 doc lines written for a one-line CSS diff (design §10 v2.12 + v2.12.2). The ratio
scales itself and needs no calibrated number. **Every constant in the table above is
inherited, not derived** — 200/300 came in with the original contract, and D2's 250/500 is
that pair collapsed on the reasoning that a merged artifact drops the second file's
restatement of problem, ACs and context. Retune from run evidence, and until then treat a
guard-rail breach as one `⚠ over-guard-rail` line and nothing else.

**Critical passes** (D2: spec; D3: design + spec + plan) — for each artifact, dispatch a
FRESH subagent **pinned `model: sonnet`**. A refute pass finds and reports; the orchestrator
adjudicates. That makes it a finder, not an author, which is adw-core §8's line. All 12
critical passes of the `team-active-seat-model` run were unpinned and so inherited Opus,
costing 13% of that whole run's subagent spend for the same job the same run handed to 33
sonnet agents on code. The prompt:

> Refute this <artifact> at `<path>`. Attack: wrong premises, missing units of work,
> acceptance criteria no command can check, a `verify` that passes vacuously, a `verify`
> blind to production files the plan touches (narrow ≠ vacuous — run-2's verify covered
> 1 of 7 files and passed every check), redundancy past the artifact budget (plan
> restating spec; full-code transcription), packaging that hides a cross-unit
> dependency. Also name every trap domain this change touches that no acceptance
> criterion mentions — every domain `.claude/repo-profile.md` §11 declares, plus the
> date-only-vs-timestamp distinction inside the date/TZ one. Report findings only — do not edit.

Send accepted findings to the unit's authoring agent (SendMessage) to revise in place.
A finding only the owner can settle gets ONE plain-language question with a recommended
default, carried to Phase 5's `needs you` — never buried in the artifact.

**Relay budget:** while unit agents author and revise, surface ONE line per unit event
(`u3 revised — 8 findings fixed, 0 questions`) — never per-finding lists. Full reports
live in the task outputs; the specs and the handoff carry everything that matters. Run-6's five
~15-line relays buried the surfaces between them — design v2.8.

## Phase 4 — validate the contract (mechanical, before exit)

Fix in place on any failure, except where a bullet says it only reports:
- every approved unit has a spec at its expected path, opening with all six required
  header fields (`base:` optional — when the intent overrides it, every unit carries the
  same value, adw-core §2);
- `intent:` equals the slug everywhere; `unit:` ids are unique **against every id the
  intent has ever used**, merged units included (extend mode: re-check `max` from the PR
  titles — a reused id collides in a PR title and breaks resume); `after:` references only
  existing units — prior units of the intent are legal targets — and is acyclic;
- extend mode: exactly ONE dated spec folder for the slug (adw-core §1) and every new
  spec carries the intent's `base:`;
- every `verify:` is a non-empty command whose first token is on `repo-profile §5`'s allowlist;
  any other tool wraps in `bash -c '…'`;
- **every D3 unit has a plan file; D0/D1/D2 units have none** — a plan file next to a D2
  spec is a contract violation, not a bonus (adw-core §3);
- **every D2 spec carries a `## Implementation` section** — `grep -c '^## Implementation'`
  returns 1. A D2 spec without it has no build input and goes back to its authoring agent;
- `wc -l` every **D2/D3** spec and plan against the artifact budget table (Phase 3) — the
  guard rail, then the hard stop, and at D3 also spec < plan (ratio). The artifact-vs-diff
  ratio cannot be checked here (no diff yet); adw-build §3.5 measures it. Only a **ratio
  inversion or a hard-stop breach** goes back to its OWN authoring agent to fit — never trim
  it yourself from the orchestrator: the author holds the context that decides what is
  load-bearing, and a trim done here re-reads the artifact into the main loop for nothing. A
  guard-rail breach between the two is carried to the handoff as one
  `⚠ over-guard-rail: uNN <spec>L[/<plan>L]` line and nothing else: no refit, no prose ruling.
  It stays advisory here because this check runs on a draft; adw-build §3.5 re-counts the
  committed artifact (design §10 v2.12.2);
- every repo path the spec/plan cites resolves — these artifacts are committed inside the unit's
  PR (adw-build §3.1), so a dead citation never becomes code and no downstream gate ever sees it.
  Collect tokens from **both** the backticked spans rooted at one of `repo-profile §2`'s source
  roots (no space inside; no `[MODIFY]`/`[NEW]` markers — those are the hand-authored umbrellas'
  convention, not `/adw-init`'s) **and** the `verify:` frontmatter value, where they sit unquoted —
  those are the ones that become the executable gate command. Then, per token: skip any containing
  `*`, `?`, `…` or `{` (a glob, not a citation) · strip a trailing `:` line-spec — `:NN`,
  `:NN-NN`, `:NN–NN` (en dash, and it is live in the corpus), comma lists like
  `factories.ts:20,69,189`, and any mix of those — plus trailing `).,;:"'` · skip what
  `git check-ignore -q` matches (gitignored build output is never committed) ·
  resolve with **`test -e`**, not `test -f` (directories get cited too), retrying under each of
  `repo-profile §2`'s subproject roots (specs cite subproject-relative paths, e.g. a test-runner
  arg after a `cd`) and with each of its code extensions appended
  (an extensionless `…/someModule` resolves once `.ts` is appended). **Report the survivors as a list; this check does not
  block** — most of them are files the unit is about to create, which is why the old "exempt a path
  the artifact names as CREATED" clause never executed mechanically. Skipping any of the
  normalisation steps buries the real hits: unnormalised, the corpus yields far more false
  positives than true ones;
- every `<standards doc> §N` citation resolves to a real heading. `repo-profile §2` lists the docs
  and the heading level each numbers at; check with `grep -nE '^#{2,4} <N>\.' <file>`. Report
  **every** match, never just the first — a doc that skips a number or reuses one makes a citation
  ambiguous and the author has to say which (`repo-profile §2` names the live instance). Fix a
  merely-wrong citation in place. A heading citation you cannot fix carries
  to the handoff `needs you` — never a silent pass; unresolved **paths** are reported only, per the
  bullet above;
- `grep -l 'superpowers:'` is fine; a reference to any repo-local symlinked skill name is
  a failure.

## Phase 5 — handoff, then build

**This phase is where the run ends, so the decision to keep going is made HERE.** It was
stated only in Phase 2 for one version and never executed once: a run printed the handoff,
wrote "Continuing into the build.", and ended the turn — because the two instructions at
the cursor (`the report is the whole message`, and the handoff's own
`Next: /adw-build <slug>`) both say stop, and a rule 180 lines up does not beat them.
Three ordered steps, no discretion:

1. **Decide the exit first, before printing anything.** Build unless either holds:
   the gate verb was `specs only`, **or** `needs you` is non-empty. Either → stopping exit.
2. **Print the handoff exactly** (adw-core §7) in the variant step 1 chose — `Next: nothing
   — building <units>` for the building exit, `Next: /adw-build <slug>` for the stopping
   one. Rest of the surface is identical: specs line · plans line · `⏱ run` · `needs you`
   items aggregated from Phase 3 (or `none`). The report is the whole message: **nothing
   follows the last line — no summary of what the critical passes found, no explanation of
   a question already printed, no announcement of what you are about to do.** A run that
   narrates after this block has violated adw-core §7 rule 2 no matter how good the
   narration is; the same material belongs in the spec, where the build reads it.
3. **Building exit only: invoke `/adw-build <slug>` now**, in this turn, with no message
   between it and the handoff. Not "next I will run" — run it. **Enter build with the spec
   bodies OUT of context:** do not re-read, quote or summarise them at the boundary, and
   drop the Phase 3 agents' returned text. Build's Phase 0 resolves every spec from disk
   itself, and the whole cost of collapsing the round-trip is that build no longer starts
   on a fresh window — the `subscription-locks` run compacted 8 times, and adw-build's
   session-boundary rule (§ "Session-boundary provenance") turns a mid-chain compaction
   into a halt with a `ready` sub-PR left human-owned. Carrying init's spec text into build
   buys nothing and pays that cost directly.

Unanswered `needs you` items ship with the recommended default, recorded in the spec — but
note that an unanswered item is exactly what step 1 stops on, so this applies to a later
`/adw-build` the human starts after reading them.
Extend mode: the `specs` line counts only the units THIS run added or amended, and names
the intent's total (`3 new · u1–u5 prior`) — `/adw-build` skips the merged ones anyway.
