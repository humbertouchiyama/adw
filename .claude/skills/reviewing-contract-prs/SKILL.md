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

**1. Setup.** From the repo root:

```bash
gh pr view <N> --json title,body,headRefOid,baseRefName,commits,files
git fetch -q origin 'refs/pull/*/head:refs/remotes/pr/*' && git fetch -q origin
gh pr list --state open --json number,title,headRefName
python3 .claude/skills/reviewing-contract-prs/check-anchors.py origin/<base> pr/<N>
```

Every `NEW` line from `check-anchors.py` is a `Blocking` finding: a contract that cites an anchor
the reader cannot find stops the run. Report `OLD` lines once, under Coverage.

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
| **A — ripple** | List every rule this diff adds, removes or changes. For each one, grep the **whole repo at the PR head** (`commands/`, `install/`, `README.md`, `docs/00-design.md`, `docs/repo-profile-EXAMPLE.md`) for every site that states, quotes, depends on or should now carry it. Quoted `>` prompt blocks count as sites: an agent copies them verbatim, so a requirement missing from one is missing at runtime. Return a table: site `file:line` · consistent / stale / missing. Also report contradictions inside one file. |
| **B — literal execution** | You are a `sonnet` driver with the real tools (Agent, Bash, gh, git). Walk every changed procedure step by step, as written. Where do you stall, spin, wait forever, time out, read a field no template ever writes, branch on a fact you cannot know in a fresh session, or silently skip work while the report still claims it ran? Name any dispatch with no pinned `model:`. For each hit give `file:line` and the concrete run that breaks. |
| **C — claims and context** | (1) Match the PR body to the diff, per commit (`git log --stat`): work in the diff the body never names, and body claims the diff does not make. (2) Mark every number and every "X does not work" or "X is ignored" claim as re-derived (show how) or unverified. (3) List repo-specific values added to `commands/`: repo names, paths, branch names, stack nouns. They belong in `repo-profile`. (4) For every other open PR: `git merge-tree --write-tree origin/<base> pr/<N> pr/<M>`, then read both diffs. Does one reintroduce what the other removes, or depend on text the other changes? (5) Is `docs/00-design.md` now wrong? |

**3. Refute.** After all lanes return, dispatch **one** agent with `model: opus`, read-only. Use the
refutation prompt in `commands/review-core.md` §9, adapted to this repo: the claim is about what an
agent executing the text does, not about product code. Hand over each claim as `POSITIVE |
file:line | consequence`, and each lane `VERDICT: holds` as a `NEGATIVE` claim. **Never hand over
the lane's reasoning.** Merge duplicates across lanes first, and pass every lane claim, `Warning`s
included. Also hand over any "no X remains" or "every X is pinned" statement a lane made as a
`NEGATIVE`. Verdicts are `CONFIRMED`, `OVERSTATED` or `REFUTED`. A `REFUTED` must name
the line that breaks the chain. A refuted `NEGATIVE` is a new finding. New defects the refuter
finds are real findings.

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
- anchors: <n> NEW, <n> OLD · lanes: A B C ran · refuter ran · open PRs checked: #x #y
- unverified claims in the PR body: <list, or none>
```

`fix first` means at least one `Blocking` survived refutation. A PR with zero surviving findings
still prints Coverage. **Do not post to the PR, push or edit the branch** unless the user asks.
When they ask to post, post this report as one `gh pr comment`.

## Common mistakes

| Mistake | What to do |
|---|---|
| Report one site of a defect | Lane A sweeps the class. One missing line in a quoted brief means every quoted brief must be checked. |
| Call a cited anchor "unverifiable" | Run `check-anchors.py`. It resolves or it does not. |
| Review the PR alone | Open PRs land in either order. Lane C checks every pair. |
| Trust the PR body's numbers | Unverified numbers go under Coverage, by name. |
| Print lane findings unrefuted | Every finding goes through step 3. A reviewer re-reading its own claim agrees with itself. |
| Put a hypothesis in a lane brief | The lane returns it and it reads as confirmation. Keep briefs to the question. |
