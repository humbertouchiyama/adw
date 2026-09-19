---
name: reviewing-contract-prs
description: Use when reviewing, critiquing, refuting or approving a pull request to the adw repository (commands/*.md, install/, docs/), or before merging any change to the ADW prose contract.
---

# Reviewing contract PRs

## Overview

A PR here is a production change in every consuming repo at once, and no linter reads it. The
reader is a cheap model that follows the text **literally**. So the question is never "is this
well argued?" It is: **what does an agent do when it executes this text word for word, and what
does every other file still say?**

One reviewer reading the diff tends to find one instance of a defect and stop. Nothing makes it
sweep the class, check the other open PRs, resolve anchors, or attack its own findings. This skill
makes each of those a separate, required step.

## Procedure

Run this at the top level of a session, never inside a dispatched agent. There an `Agent` call runs
in the background and each completion arrives as a notification: dispatch, end your turn, and act
only when every dispatched agent has reported. Never poll.

**1. Setup.** From inside the adw repo. `<skill dir>` is the base directory shown when this skill
loads. `<N>` is the PR number in the skill's argument: strip a leading `#`, or take it from a URL.

```bash
git fetch -q origin '+refs/pull/*/head:refs/remotes/pr/*'
git fetch -q origin
gh pr view <N> --json title,body,baseRefName,commits,files
gh pr list --state open --limit 100 --json number,headRefName,headRefOid \
  --jq '.[] | "\(.number) \(.headRefOid) \(.headRefName)"' |
  while read -r n oid branch; do
    echo "#$n $branch"
    test "$(git rev-parse --verify -q pr/$n)" = "$oid" || echo "STALE: pr/$n is not the PR head"
  done
PRDIR="$(mktemp -d)" && git archive pr/<N> | tar -x -C "$PRDIR" && echo "pr dir: $PRDIR"
python3 <skill dir>/check-anchors.py origin/<base> pr/<N>
```

On any `STALE` line, run the first two lines and the loop once more. If it persists, stop: no lane
may read a head that is not the PR head. `<pr dir>` below is the printed `$PRDIR`. `<M>` is each
other `#` number the loop printed. `check-anchors.py` exits 2 when it could not run (unreadable ref,
no contract files, no merge-base): the anchor check `failed`. That is not a pass.

Every `NEW` line from `check-anchors.py` is a `Blocking` finding: a contract that cites an anchor
the reader cannot find stops the run. It is a deterministic gate result, so it skips the refuter
(`commands/review-core.md` §9: audit findings are never claims). The exception is an anchor in
`OPTIONAL` in `check-anchors.py`: the contract documents a fallback for it, so a `NEW` line for it
is a `Warning` when the citing line itself carries that fallback, and `Blocking` when it does not.
`OLD` lines were already broken at the merge-base. `OPT` lines are old citations of an `OPTIONAL`
anchor. Neither is a finding. Print both under Coverage.

**2. Three lanes, in parallel, in ONE message** (`general-purpose`, `model: sonnet`; a retry keeps
the pin). **Never put your own suspicions in a brief.** A lane told what to find returns it, and
that proves nothing. Each brief is this text, with the lane's question from the table pasted in:

> Read-only review of pull request #<N> in the adw repo at <repo root> (a repo of prose prompt
> contracts that coding agents execute literally). Base ref: `origin/<base>`. The PR head is
> extracted, whole, at `<pr dir>`: read whole files there, not hunks. The checked-out tree is not
> the PR head. Other open PR heads are refs `pr/<M>` (fetched). Also available: `git diff
> origin/<base>...pr/<N>`, `gh pr view`. Do not edit, push or comment. Never dispatch an agent,
> start a wait loop, or load the `reviewing-contract-prs` skill.
>
> Your question (<lane letter and name>): <the lane's question>
>
> Return as your final message: (1) any table your question asks for; (2) claims, one per line:
> `SEVERITY | file:line | consequence, one sentence | reachable scenario`, where SEVERITY is
> `Blocking` (a run breaks, loops, degrades silently, or a gate lies) or `Warning`; (3) one line:
> `VERDICT: holds` or `VERDICT: does not hold`.

| Lane | Question |
|---|---|
| **A — ripple** | List every rule this diff adds, removes or changes. For each one, search the **whole repo at the PR head** (`commands/`, `install/`, `README.md`, `docs/00-design.md`, `docs/repo-profile-EXAMPLE.md`, `.claude/skills/`) for every site that states, quotes, depends on or should now carry it. Use `grep -rn <pattern> <pr dir>/<paths>`. Quoted `>` prompt blocks count as sites: an agent copies them verbatim, so a requirement missing from one is missing at runtime. Return a table: site `file:line` · consistent / stale / missing. Also report contradictions inside one file. |
| **B — literal execution** | You are a `sonnet` driver. Walk every changed procedure step by step, as written, by reading it. To test whether a command works, run it read-only, or in a scratch repo under `$TMPDIR`. Where do you stall, spin, wait forever, time out, read a field no template ever writes, branch on a fact you cannot know in a fresh session, or silently skip work while the report still claims it ran? Name any dispatch with no pinned `model:`. For each hit give `file:line` and the concrete run that breaks. |
| **C — claims and context** | (1) Match the PR body to the diff, per commit (`git log --stat`): work in the diff the body never names, and body claims the diff does not make. (2) Mark every number and every "X does not work" or "X is ignored" claim as re-derived (show how) or unverified. (3) List repo-specific values a run would consume, added to `commands/`: repo names, paths, branch names, stack nouns. They belong in `repo-profile`. A PR number or repo name cited as the evidence for a rule is provenance, not a value (`README.md`, "The split"): leave it out. (4) For every other open PR `<M>`: `git merge-tree --write-tree pr/<N> pr/<M>` (two branches only; exit 1 is a conflict, report it), then read both diffs. Does one reintroduce what the other removes, or depend on text the other changes? (5) Is `docs/00-design.md` now wrong? End your report with two lines: `PRS CHECKED: <the #M whose merge-tree ran>` and `UNVERIFIED: <the body claims you marked unverified, or none>`. |

A lane that errors, returns no `VERDICT:` line, or returns `does not hold` with no claim line is
dispatched once more. If it fails again, Coverage says `failed` for it.

**3. Refute.** After all lanes have reported, number every claim: `P1`, `P2`, … for defects and
`N1`, … for assurances. Merge duplicates across lanes first. **Never hand over the lane's
reasoning.** Hand over as `POSITIVE | P<n> | file:line | consequence`: every lane claim, `Warning`s
included, and every `stale` or `missing` row of lane A's table. Hand over as `NEGATIVE | N<n> |
file:line | assurance`: each lane `VERDICT: holds`, every "no X remains" or "every X is pinned"
statement a lane made, and lane A's `consistent` rows, one claim per rule with its sites listed.

Dispatch one agent per 40 claims, all in one message: `model: opus` (the top tier in `adw-core
§8`), read-only. Use the quoted prompt block in `commands/review-core.md` §9, not its dispatch
rules, with three changes. The claim is about what an agent executing the text does, not about
product code. The sentence "Your cwd is the review worktree at the PR head" becomes: "Read-only:
do not edit, push or comment. The PR head is extracted at `<pr dir>`: read whole files there."
And add: "Output one line per claim id, `<id> | verdict | chain`, then one line per new defect you
find: `NEW | Blocking or Warning | file:line | consequence | run`."

A claim id with no verdict line means that refuter `failed`: dispatch it once more with the
missing ids. If it fails again, Coverage says `failed`.

Verdicts are `CONFIRMED`, `OVERSTATED` or `REFUTED`. A `REFUTED` must name the line that breaks
the chain. What each does:

| | `CONFIRMED` | `OVERSTATED` | `REFUTED` |
|---|---|---|---|
| **POSITIVE** (a defect is asserted) | the finding stays | it stays at the refuter's consequence: a `Blocking` that is not a run that breaks, loops, degrades silently or lies becomes a `Warning` | it moves to Refuted |
| **NEGATIVE** (safety is asserted) | nothing to report | a `Warning` | a new finding: `Blocking` if it names a run that breaks, loops, degrades silently or a gate that lies, else `Warning` |

A `NEW` line is a finding at the severity it names. This differs from `commands/review-core.md`
§9, which takes severity from a repo profile and pins it to an apply step: this repo has neither,
so the table above is the whole rule.

**4. Report.** Print this, and nothing else:

```
PR #<N> — <merge | fix first | do not merge | incomplete>   (<one clause: why>)

Blocking
- file:line — defect — the run that breaks — fix
Warning
- file:line — defect — fix
Refuted (<n>)
- file:line — claim — the line that breaks it
Coverage
- anchors: <n> NEW, <n> OLD, <n> OPT (output lines of check-anchors.py), or `failed` · lanes: A <ran|failed> B <ran|failed> C <ran|failed> · refuter <ran|failed> · open PRs checked: <lane C's PRS CHECKED line>
- OLD and OPT lines: <the lines from check-anchors.py, verbatim, or none>
- unverified claims in the PR body: <lane C's UNVERIFIED line>
```

`merge` means no `Blocking` survived and nothing `failed`. `fix first` means at least one
`Blocking` survived and an edit to this PR fixes it. `do not merge` means a `Blocking` survived
that no edit to this PR fixes: it needs another PR to land first, or the approach is wrong.
`incomplete` means the anchor check, a lane or the refuter `failed` and no `Blocking` survived:
re-run before merging. A `failed` component never allows `merge`. A PR with zero surviving
findings still prints Coverage. **Do not post to the PR, push or edit the branch** unless the user
asks. When they ask to post, post this report as one `gh pr comment`.

## Common mistakes

| Mistake | What to do |
|---|---|
| Report one site of a defect | Lane A sweeps the class. One stale site of a rule means every site that states or quotes the rule must be checked. |
| Call a cited anchor "unverifiable" | Run `check-anchors.py`. It resolves the citation forms listed in its docstring; a form it does not read is not checked. |
| Review the PR alone | Open PRs land in either order. Lane C checks every pair. |
| Trust the PR body's numbers | Unverified numbers go under Coverage, by name. |
| Print lane findings unrefuted | Every lane finding goes through step 3. A reviewer re-reading its own claim agrees with itself. |
| Put a hypothesis in a lane brief | The lane returns it and it reads as confirmation. Keep briefs to the question. |
