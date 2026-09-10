# adw

An agentic development workflow. Intent goes in, reviewed pull requests come out, and a human
approves exactly once — at the unit cut, before any code is written.

This repository holds **the contract**: the prompt files a coding agent reads to run the pipeline,
and the design document that explains why each rule is there. It holds no product code and belongs
to no product. Repositories that run ADW fetch it; they do not copy it.

## What is here

| Path | What |
|---|---|
| `commands/adw-core.md` | The shared contract. Spec headers, naming, the depth ladder, packaging, the approval and handoff surfaces. Read at Phase 0 by both commands below. |
| `commands/adw-init.md` | Intent → triage → human-approved unit cut → per-unit specs. |
| `commands/adw-build.md` | Specs → worktrees → gates → independent verification → PRs → review loop. |
| `commands/pr-ready.md` | Independently verify an open PR is actually mergeable. |
| `commands/review-core.md` | Shared machinery for the two review skills. |
| `commands/code-review.md` | Review a PR against the consuming repo's conventions. |
| `commands/cleanup.md` | Clear stale worktrees, branches and disposable state. |
| `docs/00-design.md` | The design, and a frozen archive of every contract change up to the extraction. |
| `docs/repo-profile-EXAMPLE.md` | A filled-in `repo-profile.md` from a real repository, to copy and edit. |
| `install/` | The loader stubs and the fetch script a consuming repo drops in. |

## The split

Nothing in `commands/` **reads** a repo-specific value. Every value that could differ between two
repositories — paths, branch names, gate commands, trap domains, review emphasis — lives in a
`repo-profile.md` **in the consuming repo**, cited from the contract as `repo-profile §N` against
frozen anchors §1–§18. The test for whether a value belongs here is simple: could this sentence be
true in a repo with a different stack? If not, it names a value, and the value belongs in the
profile.

`commands/` does still carry **provenance**: rules are justified by citing the Plantoes-app PRs and
intents that produced them (`PR #751`, `team-active-seat-model`, and so on). Those are evidence for
why a rule exists, not values a run consumes, so they do not break portability — but they are noise
in another repo, and moving them into `docs/00-design.md` is an open cleanup.

## Installing it in a repo

```bash
# from the root of the consuming repo
mkdir -p .claude/adw .claude/commands
curl -fsSL https://raw.githubusercontent.com/humbertouchiyama/adw/main/install/fetch.sh \
  -o .claude/adw/fetch.sh && chmod +x .claude/adw/fetch.sh
bash .claude/adw/fetch.sh
cp .claude/adw/cache/install/stubs/*.md .claude/commands/
echo '.claude/adw/cache/' >> .gitignore
```

**If `.claude/commands/` already holds real command files, diff before you overwrite.** The `cp`
above replaces them. A repo that had customised one of these — a `code-review.md` carrying its own
convention rules, say — loses that content silently. AXCMedApp's was 297 lines of Kotlin rules; they
had to be rehomed into its `audit.sh` and `repo-profile §16` before the stub could land.

Then write `.claude/repo-profile.md`. Start from `docs/repo-profile-EXAMPLE.md` and replace every
value; the section numbers are anchors and must not be renumbered. A contract file that cites a
section your profile does not answer will stop the run, which is the intended failure.

### The loader is a copy, and copies drift

`fetch.sh` and the stubs are the one part of ADW that is **not** fetched — they are tracked files in
your repo mirroring `install/` here. So they drift exactly the way the contract used to. AXCMedApp
ran a revision-old loader for a day: its stubs did not know exit 2 existed, so an unverified cache
would have run as verified.

`fetch.sh` now compares itself and your stubs against the freshly-fetched `install/` on every
successful fetch and prints one line when they differ. It never rewrites them — diff first, then
copy. This is a report, not a gate: it is the honest residual of keeping a bootstrap out-of-band.

## How a run resolves the contract

The stub in `.claude/commands/` is a short loader. It runs `fetch.sh`, which clones or updates
`.claude/adw/cache/` (gitignored), and then tells the agent to read the real file out of that
cache. **The fetch happens before the contract is read.** A run pins one commit sha at Phase 0 and
finishes on it; the cache is not re-fetched mid-run.

`fetch.sh` exits **0** when it fetched, **2** when the fetch failed and it fell back to an existing
cache of unknown age, and **1** when there is no usable contract at all. The stub branches on all
three: exit 2 proceeds but must carry `⚠ contract from cache, not verified against origin` onto
every surface the run prints; exit 1 stops. `ADW_REPO` and `ADW_REF` are honoured on every run, not
only the first clone.

The previous design copied these files into each repo and compared them against `origin` at
Phase 0. That check ran *after* the text had loaded, could not correct itself, and shipped inside
the file that might be stale. Two runs executed a superseded contract with it in place. Fetching
first moves the question to a point where the answer still changes what happens.

## Changing the contract

One PR here. It is live in every consuming repo on their next run — no staging step, no per-repo
sync. That is the benefit and the risk in one sentence, so review a contract PR as a production
change everywhere at once.

These files are prose contracts, and no linter reads them. What has actually caught defects is a
fresh subagent, read-only, prompted to **refute** the change rather than approve it. Three such
passes have each found blocking defects. Run one.

## Provenance

ADW was built inside `AXCMED/Plantoes-app` and ran ~250 units there before it was extracted. Every
measurement in `docs/00-design.md` was taken on that repository: a full-stack TypeScript monorepo.
The reasoning is meant to be portable. The numbers are not — re-measure before inheriting a
threshold.
