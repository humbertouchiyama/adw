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

One reviewer reading the diff finds one instance of a defect and stops. It does not sweep the
class, check the other open PRs, resolve anchors, or attack its own findings. This skill makes
each of those a separate, required step.

## Procedure

Run this at the top level of a session, never inside a dispatched agent. It waits for the lanes
and the refuter, and a subagent cannot wait for them (`adw-core §8`).

**1. Setup.** From inside the adw repo. `<skill dir>` is the base directory shown when this skill
loads:

```bash
gh pr view <N> --json title,body,headRefOid,baseRefName,commits,files
git fetch -q origin '+refs/pull/*/head:refs/remotes/pr/*'
git fetch -q origin
test "$(git rev-parse pr/<N>)" = "<headRefOid>" || echo "STALE: pr/<N> is not the PR head. Fetch again."
gh pr list --state open --json number,title,headRefName
python3 <skill dir>/check-anchors.py origin/<base> pr/<N>
```

Stop on `STALE`: no lane may read a head that is not the PR head. `check-anchors.py` exits 2 when
it cannot read a ref. That is a failed check, not a pass.

Every `NEW` line from `check-anchors.py` is a `Blocking` finding: a contract that cites an anchor
the reader cannot find stops the run. It is a deterministic gate result, so it skips the refuter
(`commands/review-core.md` §9: gate findings are never claims). `OLD` lines are already broken at
the merge-base. `OPT` lines cite an anchor the contract documents a fallback for. Neither is a
finding. Print both lines once, under Coverage.

**2. Three lanes, in parallel, in ONE message** (`general-purpose`, `model: sonnet`). **Never put
your own suspicions in a brief.** A lane told what to find returns it, and that proves nothing.
Each brief is this text, with the lane's question from the table pasted in:

> Read-only review of pull request #<N> in the adw repo at <repo root> (a repo of prose prompt
> contracts that coding agents execute literally). Base ref: `origin/<base>`. PR head is ref
> `pr/<N>`; other open PR heads are `pr/<M>` (fetched). Use `git show pr/<N>:<path>`,
> `git diff origin/<base>...pr/<N>`, `gh pr view`. Read whole files, not hunks. Do not edit,
> push or comment.
>
> Your question (<lane letter and name>): <the lane's question>
>
> Return as your final message: (1) any table your question asks for; (2) claims, one per line:
> `SEVERITY | file:line | consequence, one sentence | reachable scenario`, where SEVERITY is
> `Blocking` (a run breaks, loops, degrades silently, or a gate lies) or `Warning`; (3) one line:
> `VERDICT: holds` or `VERDICT: does not hold`.

| Lane | Question |
|---|---|
| **A — ripple** | List every rule this diff adds, removes or changes. For each one, search the **whole repo at the PR head** (`commands/`, `install/`, `README.md`, `docs/00-design.md`, `docs/repo-profile-EXAMPLE.md`, `.claude/skills/`) for every site that states, quotes, depends on or should now carry it. Use `git grep -n <pattern> pr/<N> -- <paths>`: a plain `grep` reads the checked-out tree, not the PR head. Quoted `>` prompt blocks count as sites: an agent copies them verbatim, so a requirement missing from one is missing at runtime. Return a table: site `file:line` · consistent / stale / missing. Also report contradictions inside one file. |
| **B — literal execution** | You are a `sonnet` driver. Walk every changed procedure step by step, as written, by reading it. Never dispatch an agent, start a wait loop, or write to the repo or to GitHub. To test whether a command works, run it read-only, or in a scratch repo under `$TMPDIR`. Where do you stall, spin, wait forever, time out, read a field no template ever writes, branch on a fact you cannot know in a fresh session, or silently skip work while the report still claims it ran? Name any dispatch with no pinned `model:`. For each hit give `file:line` and the concrete run that breaks. |
| **C — claims and context** | (1) Match the PR body to the diff, per commit (`git log --stat`): work in the diff the body never names, and body claims the diff does not make. (2) Mark every number and every "X does not work" or "X is ignored" claim as re-derived (show how) or unverified. (3) List repo-specific values a run would consume, added to `commands/`: repo names, paths, branch names, stack nouns. They belong in `repo-profile`. A PR number or repo name cited as the evidence for a rule is provenance, not a value (`README.md`, "Provenance"): leave it out. (4) For every other open PR `<M>`: `git merge-tree --write-tree pr/<N> pr/<M>` (two branches only; exit 1 is a conflict, report it), then read both diffs. Does one reintroduce what the other removes, or depend on text the other changes? (5) Is `docs/00-design.md` now wrong? |

A lane that errors, or returns without a `VERDICT:` line, is dispatched once more. If it fails
again, Coverage says `failed` for it and the headline cannot be `merge`.

**3. Refute.** After all lanes return, dispatch **one** agent with `model: opus`, read-only. One,
even when there are more than four claims: this overrides the split in `commands/review-core.md`
§9. Use the quoted prompt block in that section, not its dispatch rules, with two changes. The
claim is about what an agent executing the text does, not about product code. The sentence "Your
cwd is the review worktree at the PR head" becomes: "Read-only: do not edit, push or comment. Your
cwd may not be the PR head: read it with `git show pr/<N>:<path>` and `git diff
origin/<base>...pr/<N>`."

Hand over each claim as `POSITIVE | file:line | consequence`, and each lane `VERDICT: holds` as a
`NEGATIVE` claim. **Never hand over the lane's reasoning.** Merge duplicates across lanes first,
and pass every lane claim, `Warning`s included. Also hand over as `NEGATIVE` every "no X remains"
or "every X is pinned" statement a lane made, and every `consistent` row of lane A's table.

Verdicts are `CONFIRMED`, `OVERSTATED` or `REFUTED`. A `REFUTED` must name the line that breaks
the chain. What each does:

| | `CONFIRMED` | `OVERSTATED` | `REFUTED` |
|---|---|---|---|
| **POSITIVE** (a defect is asserted) | the finding stays | it stays at the refuter's consequence: a `Blocking` that is not a run that breaks, loops, degrades silently or lies becomes a `Warning` | it moves to Refuted |
| **NEGATIVE** (safety is asserted) | nothing to report | a `Warning` | a new finding: `Blocking` if it names a run that breaks, loops, degrades silently or a gate that lies, else `Warning` |

New defects the refuter finds are real findings. A refuter that fails is dispatched once more. If
it fails again, Coverage says `failed` and the headline cannot be `merge`.

**4. Report.** Print this, and nothing else:

```
PR #<N> — <merge | fix first | do not merge>   (<one clause: why>)

Blocking
- file:line — defect — the run that breaks — fix
Warning
- file:line — defect — fix
Refuted (<n>)
- file:line — claim — the line that breaks it
Coverage
- anchors: <n> NEW, <n> OLD, <n> OPT (output lines of check-anchors.py) · lanes: A <ran|failed> B <ran|failed> C <ran|failed> · refuter <ran|failed> · open PRs checked: <the #M whose merge-tree ran>
- OLD and OPT lines: <the lines from check-anchors.py, verbatim, or none>
- unverified claims in the PR body: <list, or none>
```

`merge` means no `Blocking` survived. `fix first` means at least one `Blocking` survived and an
edit to this PR fixes it. `do not merge` means a `Blocking` survived that no edit to this PR fixes:
it needs another PR to land first, or the approach is wrong. A `failed` lane or refuter rules out
`merge`. A PR with zero surviving findings still prints Coverage. **Do not post to the PR, push or
edit the branch** unless the user asks. When they ask to post, post this report as one
`gh pr comment`.

## Common mistakes

| Mistake | What to do |
|---|---|
| Report one site of a defect | Lane A sweeps the class. One stale site of a rule means every site that states or quotes the rule must be checked. |
| Call a cited anchor "unverifiable" | Run `check-anchors.py`. It resolves or it does not. |
| Review the PR alone | Open PRs land in either order. Lane C checks every pair. |
| Trust the PR body's numbers | Unverified numbers go under Coverage, by name. |
| Print lane findings unrefuted | Every lane finding goes through step 3. A reviewer re-reading its own claim agrees with itself. |
| Put a hypothesis in a lane brief | The lane returns it and it reads as confirmation. Keep briefs to the question. |
