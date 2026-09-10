# Repo profile — EXAMPLE (`AXCMED/Plantoes-app`)

> **This is a worked example, not a template to ship as-is.** It is the live profile of the
> repository ADW was built in: a full-stack TypeScript monorepo (React 19 + Vite, Hono + PostgreSQL
> 16 + Drizzle, one shared npm workspace). Copy it to `.claude/repo-profile.md` in your repo and
> replace **every** value. Keep the section numbers: the contract cites them as `repo-profile §N`
> and the anchors §1–§18 are frozen.

Every repo-specific value the shared agent contract needs. One of these lives in each repo that
runs `/adw-init`, `/adw-build`, `/pr-ready` or `/code-review`; the contract files themselves
(`adw-core.md`, `adw-init.md`, `adw-build.md`, `pr-ready.md`, `review-core.md`,
`code-review.md`, `cleanup.md`) live in the `adw` repository and are fetched, never copied.

The format is prose and tables, not a parsed config. The reader is an agent, so precision matters
more than syntax.

**Section anchors are frozen** — the contract files cite `repo-profile §1`…`§18` by number. Do not
renumber. Add new sections at the end.

| § | Section | Read by |
|---|---|---|
| §1 | Identity and layout | orientation |
| §2 | Paths | adw-core §1, adw-init Phase 4, adw-build §3.5, pr-ready §2/§5 |
| §3 | Branches | adw-core §2/§6, adw-build Phase 0 |
| §4 | Worktree provisioning | adw-build Phase 2, review-core §1.2, pr-ready §4.3 |
| §5 | Gates | adw-build §3.2, review-core §4, pr-ready §4.3 |
| §6 | Layer map — which gates a diff obligates | review-core §4, adw-build §3.2 |
| §7 | Gate files — the tripwire list | pr-ready §4.2 |
| §8 | Blast-radius paths | review-core §7 |
| §9 | CI coverage | pr-ready §"When to reach for this" |
| §10 | Environment faults | adw-build §3.3 |
| §11 | Trap domains | adw-core §3, adw-build §3.1 |
| §12 | Running a single test | adw-core §2, adw-build §3.2 |
| §13 | Review layers and their standards docs | code-review Phase 2 |
| §14 | Risk scoring | code-review Phase 3 |
| §15 | Review emphasis + Blocking severity classes | code-review Phase 4, 4.5 |
| §16 | Project rule tables | code-review Phase 5.2, 5.3 |
| §17 | Convention doc routing | code-review Phase 6.2 |
| §18 | Disposable state | cleanup Phase 3, 5 |

---

## §1 — Identity and layout

Medical shift-management PWA. React 19 + Vite + TypeScript frontend, Hono.js + PostgreSQL 16 +
Drizzle API, one npm workspace shared package. npm workspaces monorepo.

| Root | What |
|---|---|
| `src/` | frontend |
| `api/` | Hono REST API (its own `package.json`, `tsconfig.json`, vitest configs) |
| `packages/shared/` | `@plantoes/shared` — Zod schemas both sides import; a `composite` TS project whose `dist/` is gitignored |
| `tests/` | Playwright e2e |
| `scripts/` | repo tooling |

`CLAUDE.md` is the human-facing companion to this file; where the two disagree, `CLAUDE.md` wins on
conventions and this file wins on commands.

## §2 — Paths

| Role | Value |
|---|---|
| **specs dir** | `docs/adw/specs/` |
| **plans dir** | `docs/adw/plans/` |
| **legacy specs dir** (read-only — adw-core §1) | `docs/superpowers/specs/` |
| **legacy plans dir** (read-only — adw-core §1) | `docs/superpowers/plans/` |
| **artifact exclusion pathspec** | `':!docs/adw/**' ':!docs/superpowers/**'` — excludes specs+plans from a code diff |
| **ADW design doc** | `docs/adw/00-design.md` |
| **source roots** (a path under one of these is production code) | `src/` `api/` `packages/` `scripts/` `tests/` |
| **subproject roots** (a spec may cite a path relative to one of these) | `api/` `functions/` `packages/shared/` |
| **code extensions** | `.ts` `.tsx` `.sql` `.css` `.json` |
| **non-code paths** (a commit confined to these is not production code) | `*.md` `docs/` `.claude/` `.agent/` |
| **standards docs** — a `<file> §N` citation must resolve to a real heading | `CLAUDE.md` (Gold Standard rules at `###`) · `api/CONVENTIONS.md` (`##`) · `docs/ui_standards.md` (`##`) · `docs/backend_standards.md` (`##`) · `docs/analytics_standards.md` (`##`) |
| **comment rule** | `CLAUDE.md` §4 — one terse line + a spec ref; never a multi-line rationale comment |
| **learning docs** | `.agent/lessons.md` (code patterns) · `.agent/review-calibration.md` (review judgment) |

**The legacy root.** `docs/superpowers/` was ADW's artifact root until 2026-09-09. It was the
wrong home twice over: it names a plugin ADW merely calls rather than the system that owns the
files, and its `specs/` mixes ADW output with pre-ADW hand-authored design docs and with the
hand-authored umbrellas (`billing/`, `prototype-port/`, `landing-port/`, …) that stay there.
**Nothing was migrated** — 757 tracked files, cross-referenced from 309 others and from merged PR
bodies. The root is frozen, not forbidden (adw-core §1): nothing already in it is rewritten, no
new intent is born there, and an intent that already lives there keeps writing its later units
there. Reads check both roots, `docs/adw/specs/` first.

`docs/ui_standards.md` skips §9 and numbers two sections `## 10.`, so a `§10` citation there is
ambiguous — report every match, never just the first.

Gitignored build output a path check must skip: `packages/shared/dist` and friends — resolve with
`git check-ignore -q` rather than a hardcoded list.

## §3 — Branches

| Role | Value |
|---|---|
| **default base** | `develop` |
| **production branch** | `main` |
| **long-lived integration branches** | `feat/**` |
| **merge convention** | squash |

`develop` is never merged into anything, so "the base branch is still unmerged" never expires for it
(adw-core §1.1 liveness).

## §4 — Worktree provisioning — before any gate

```bash
bash "$MAIN/scripts/link-worktree-deps.sh" "$WT"   # ALWAYS the script, ALWAYS run from $MAIN
( cd "$WT" && npm run pack:shared )                # else TS6305 (missing shared build info)
```

**Never** `ln -s "$MAIN/node_modules" "$WT/node_modules"`, and never repoint
`node_modules/@plantoes/shared` at a worktree to clear a `TS2305`/`TS6305`. `packages/shared` is an
npm workspace: the single-link shape resolves it to *main's* copy, and the intuitive fix writes
**through** the symlink into main's `node_modules`. Green in the worktree, silent corruption in a
directory nobody looks at. CLAUDE.md §8.

**Why `pack:shared` is mandatory even when the diff never touches `packages/shared`.** It is a
`composite` TS project listed under the root tsconfig's `references` and its `dist/` is gitignored,
so a fresh `git worktree add` has none. `tsc --noEmit` then fails **TS6305** on every file importing
`@plantoes/shared`. Symlinking `node_modules` does not fix it — `paths`/`references` resolve to the
*worktree's* `packages/shared`. Verified: fresh worktree → ~100 TS6305 errors; after this step → 0.

`link-worktree-deps.sh` also links the `.env` files, re-pointed at **staging** — `rm .env`
afterwards if the worktree will build a production bundle.

**Run the provisioning script from `$MAIN`, never from `$WT`.** `$MAIN` sits on the base branch, so a
PR rewriting provisioning never provisions the checkout that grades it. That pin is what keeps
`scripts/link-worktree-deps.sh` off §7's tripwire list; break it and the script belongs on that list.

### Conditional provisioning — run when the diff triggers it, before any gate

Setup, not fix cycles. Both faults wear a test-failure disguise.

- **Diff adds an npm dependency** → `npm install <dep>` from **`$WT`'s root**, never from `$WT/api`
  (that wipes the hoisted root tree). Skipped, the new import fails **TS2307** and reads as if the PR
  were broken (PR #743, `dompurify`). A later re-run of `link-worktree-deps.sh` leaves that install
  alone — it skips any entry that is already a real directory.
- **Diff touches `packages/shared/`** → nothing beyond the `pack:shared` above. Do **not** repoint
  `@plantoes/shared`: the script already points both trees' copies at `$WT/packages/shared`.

## §5 — Gates, cheapest first

Run in the worktree. `<BASE>` is the caller's diff anchor.

| # | Command | Runs when | Notes |
|---|---|---|---|
| 1 | `npx tsc --noEmit` | frontend layer | |
| 2 | `npm run lint` | frontend layer | A live test stack writes `.cache/vite-s<slot>/`, which eslint then lints and reports as ~44 phantom errors. Delete the cache; never edit `eslint.config.js`. |
| 3 | `CI=1 npm test` | frontend layer | **Never** `npx vitest run` — the root script is `cross-env TZ=America/Sao_Paulo vitest` with no `run`, so bypassing it drops the TZ pin on a repo with four documented UTC-3 date-boundary regressions. `CI=1` forces run mode; a bare `npm test` enters watch and hangs. Gate on the reported **file count**: the runner can skip whole files and still print all-passed. |
| 4 | `npm run build` | frontend layer | Catches Vite/Rollup errors `tsc` cannot see. |
| 5 | `( cd "$WT/api" && npx tsc --noEmit )` | api layer | `api/tsconfig.json` **excludes test files**, so fixture type drift is invisible to this gate. |
| 6 | `( cd "$WT/api" && npm test )` | api layer | The DB is fully mocked (`vi.mock('../../lib/db.js')` per file). Anything asserting what was *persisted* does not belong in this suite. |
| 7 | `( cd "$WT/api" && npm run test:integration )` | persistence diffs | Real Postgres. Needs `cd api && npm run db:up`. From a linked worktree this targets its own `plantaopro_test_<dir>` database. |
| 8 | `npx playwright test` | UI-touching units only | Narrow the spec selection; never drop the gate. |
| 9 | audit — see below | any code layer | |

**Gate commands with `cd` run as subshells** against the worktree path — never a bare persistent `cd`.

### The audit gate

Two invocations, one script, and the argument depends on who is calling:

| Caller | Invocation |
|---|---|
| `/adw-build` (a branch diff exists) | `( cd "$WT" && bash scripts/audit.sh --diff <BASE> )` |
| `/code-review`, `/pr-ready` (a detached unstaged checkout) | `( cd "$WT" && bash scripts/audit.sh --all )` |

`audit.sh` audits the **current directory**, not its own location. Invoking it by path
(`bash "$WT/scripts/audit.sh"`) from elsewhere runs the PR's copy against the *calling* tree: no
error, a healthy non-zero run count, a confident green over the wrong file set. Always the subshell.
`--all` is required in the review case — without it the script audits only `git diff --cached`, and a
detached unstaged checkout has nothing staged.

**Empty-scope rule (`--diff` only).** When `git diff --name-only <BASE>...HEAD` contains no
`.ts`/`.tsx`/`.sql` file matching `AUDITED_PATHS` — `^(src/|api/src/|api/drizzle/migrations/|packages/)`,
grep the variable in `scripts/audit.sh`, line numbers rot — append `--allow-empty`. Otherwise a
zero-check run must fail. Path match alone is not enough: a CSS-only diff under `src/` audits zero
files. `audit.sh --diff` compares a **commit range**, so it is blind to uncommitted work — read the
`Scope: N` line.

### The `verify:` command allowlist

A spec's `verify:` first token must be one of: `cd` `npx` `npm` `CI=1` `bash` `grep` `git` `node`.
Any other tool wraps in `bash -c '…'`.

## §6 — Layer map — which gates a diff obligates

Computed from `git diff --name-only <BASE>...HEAD`, **never judged**. A gate the diff reaches is not
optional because it looks unrelated to the change.

| Diff contains | Gates |
|---|---|
| `src/` | §5 gates 1–4 |
| `api/` | §5 gates 5–6 |
| `packages/shared/` | `npm run pack:shared` **then** both frontend and api `tsc` (both consume the built artifact) |
| a migration (`api/drizzle/`, `api/src/db/schema/`) | **static** idempotency + `_journal.json` check — the blocking gate. The runtime `( cd "$WT/api" && npx tsx --env-file=.env src/db/migrate.ts )` is opt-in, only when `$WT/api/.env` exists, because it mutates the dev DB. |
| anything that persists or reads state | §5 gate 7 (`test:integration`) — `CLAUDE.md` §5 obligates it for state-transition diffs |
| `.github/workflows/` | **static parse, per changed file**: `python3 -c "import sys,yaml;print(sorted(yaml.safe_load(open(sys.argv[1]))['jobs']))" <file>` — must exit 0 and list the jobs. This is the layer's ONLY gate: no compiler, linter or audit reads these files, and a plain scalar that truncates on a ` #` stays green everywhere until a release runs. **Never report this layer as `N/A — docs-only`.** |
| any of `src/` `api/` `packages/` | the §5 audit gate — always, covers both layers |
| docs / `.claude` / `.agent` only, and no `.github/workflows/` | skip all code gates; say so explicitly: `verification: N/A — docs-only, no code gates apply` |

**Frontend gates always run for a `src/` diff; the api gates cannot be reached by a `src/`-only diff.**
For `/adw-build`, gates 5–7 run when the diff touches `api/`, `packages/`, or a §7 gate file.

**Browser smoke (UI changes only):** click through the affected flow if you can. In this environment
the reviewer typically has no browser, so a **declared** skip is the norm, not a failure — it blocks
auto-merge (routes visual QA to the human), never apply/verify/stage. An **undeclared** skip is a stop.

## §7 — Gate files — the tripwire list

Every file a §5 gate command reads. A PR that edits one of these cannot earn a green under them
(pr-ready §4.2). Extend it together with §5 and §6, or the hole reopens.

```
package.json  api/package.json  packages/shared/package.json
scripts/audit.sh  scripts/version.ts  scripts/run-e2e-parallel.sh
vite.config.ts  api/vitest.config.ts  vitest.setup.ts
api/vitest.integration.config.ts  api/src/test/integration-setup.ts  api/.env.test
eslint.config.js
tsconfig.json  tsconfig.node.json  api/tsconfig.json  packages/shared/tsconfig.json
playwright.config.ts  tests/fixtures/auth.setup.ts  tests/fixtures/global-teardown.ts
```

`package.json` is the easiest miss: there is no root `vitest.config.ts` — the frontend test gate **is**
the `test` script line (`cross-env TZ=America/Sao_Paulo vitest`).

**Never enter a directory — name the files.** A directory entry blocks every PR that adds an
unrelated file under it, and `blocked` is unappealable, so the cost lands on PRs the rule was never
aimed at. `scripts/` sat here whole and blocked PR #922 for adding `scripts/link-worktree-deps.sh`,
which no gate command runs. Of the files under `scripts/`, these three are gate files — **no tally
here on purpose**: a count is drift surface no gate checks, and the list is what is load-bearing.

- `scripts/audit.sh` — §5 runs it from inside `$WT`, so it is the PR's own copy grading itself.
- `scripts/version.ts` — the non-obvious one: `vite.config.ts` imports `resolveVersion` /
  `resolveCommitSha` from it, so `npm run build` reads it. The blanket `scripts/` covered this by
  accident; narrowing without walking the imports would have dropped it.
- `scripts/run-e2e-parallel.sh` — the body of `test:e2e:suite`.

Everything else under `scripts/` is read by no gate command. A test file is a gate's **subject**,
never its harness; otherwise every `src/**` test would belong here too. A file added to `scripts/`
later is excluded by default and only earns a place by being read by a gate command.

**A config's setup/teardown target is itself a gate file** — the config merely names it, the target is
what runs. Listing the config and omitting its target is the subtlest form of the hole:
`vitest.setup.ts` was here from the start while its api-integration twin,
`api/src/test/integration-setup.ts`, was not. PR #894 rewrote exactly that file and matched no entry;
it tripped only because it also touched `vite.config.ts`.

**Resolve the target, do not grep for `setupFiles`.** The key is named differently per runner and
sometimes not named at all — four distinct forms appear in this list: `setupFiles`
(`vite.config.ts` → `vitest.setup.ts`; `api/vitest.integration.config.ts` →
`api/src/test/integration-setup.ts`), `globalTeardown` (`playwright.config.ts` →
`tests/fixtures/global-teardown.ts`), a **project** dependency (`playwright.config.ts`'s `setup`
project, `testMatch: /auth\.setup\.ts/`, named in `chromium`'s `dependencies` →
`tests/fixtures/auth.setup.ts`), and TS project `references` (`tsconfig.json` →
`packages/shared/tsconfig.json`). A **script body** counts too: `pack:shared` is
`npm run build -w packages/shared`, so `packages/shared/package.json`'s own `build` is what compiles
the artifact every `tsc` gate consumes. Open each config you add and follow every path it points at.

The closure is **finite and was walked** on 2026-08-07 — `packages/shared/tsconfig.json` declares no
further `references`, no listed tsconfig uses `extends`, and `packages/shared/package.json`'s `build`
is a leaf. Re-walk it when you add a config, not on a schedule.

`scripts/link-worktree-deps.sh` is deliberately **off** this list: §4 pins provisioning to `$MAIN`,
so a PR's own copy never provisions the checkout that grades it. The pin and the omission move
together.

## §8 — Blast-radius paths

When applied remediation touched any of these, fall back to comment-only — do not push or merge —
and document the stop reason (review-core §7).

- `api/src/db/schema/`, `api/migrations/`, `api/drizzle/` — DB rollout coordination.
- `packages/shared/` — front + back consume; needs `npm run pack:shared` + version bump.
- `api/src/middleware/` — auth / security.
- Root configs — `package.json`, `tsconfig*.json`, `vite.config*`, `drizzle.config*`.
- `.claude/commands/*.md`, `.claude/skills/**`, `.claude/*.md` — every future agent run. The root
  glob is what covers this file, the per-repo gate and environment-fault contract read at runtime —
  same blast radius as a command file.
- `.github/workflows/**` — ships to an environment. No gate reads these files, and the two failure
  modes are releasing broken code and stopping every release, both landing after review is over.
- Any standards doc named in §2.
- `.agent/lessons.md` — a learning doc; edits are surfaced for sign-off, never auto-landed.
- `.agent/review-calibration.md` — the append is drafting only; never pushed as part of remediation.

## §9 — CI coverage

`.github/workflows/ci.yml`. **If this section ever stops matching that file, the file wins** —
re-read it rather than trusting this list.

**`ci` is opt-in.** The `validate` job is gated on the PR carrying the `ci` label (Actions minutes are
reserved for `deploy-hosting`), so the default is that nothing ran and `gh pr checks` reports **no
checks: absent, not red**. Add the label with `gh pr edit <N> --add-label ci` for a hosted run.

On a labelled PR the job runs on a clean runner at the pushed SHA: the worktree-hook tests, `lint`,
`npm test`, `build`, api `tsc`, api `npm test` — every §6-obligated gate for a full code diff except
the audit.

| | in `ci.yml`? |
|---|---|
| **any PR without the `ci` label** | **no** — opt-in. This is the DEFAULT; assume no CI until you have checked |
| the migration-order job | **yes, mandatory** — it carries no label gate |
| `scripts/audit.sh` | **no** — in no workflow. The one §6-obligated gate CI never runs |
| api `test:integration` | **no** — needs Postgres; `ci.yml` says so in a comment |
| review posted after the last code commit | no |
| verified-SHA == merged-tree | no |
| **any PR whose base is not `main`/`develop`/`feat/**`** | **no** — `branches: [main, develop, 'feat/**']` |
| draft PRs | no — the job is gated on `draft == false` |
| a PR whose whole diff is `**/*.md`, `docs/**` or `.agent/**` | no — `paths-ignore` filters the event before the job's `if` |

**`/code-review` posts an issue comment (`### Code review …`), never a GitHub review object**, so
`gh pr view --json reviews` reports `0` on every pipeline PR. The comment is the signal; keying on
`reviews` scores every PR unreviewed.

**A red status check is a note, not a gate — but never a silent one.** This repo's GitHub Actions
were billing-blocked from ~2026-07-13, and those runs fail in seconds with an empty `steps` array.
Confirm which it is — `gh run view <id> --json jobs` shows the empty-`steps` shape; `gh pr checks`
returns only the rollup and cannot tell you. Once billing is restored this paragraph must not license
attributing genuine red CI to it.

## §10 — Environment faults — abort, never consume a cycle

- Connection-refused on `test:integration` → Postgres is down. `cd api && npm run db:up`. **Never
  from a worktree agent** — it recreates the shared container and kills every concurrent run.
- `test:integration` hanging to the 600s timeout with empty output is Docker being down, not a slow
  gate.
- Disjoint failure sets plus hook timeouts across runs is Postgres memory pressure. Restart the
  container; do not start a fix cycle.
- Missing `api/.env` in the worktree → provisioning did not complete.
- A cross-worktree `.vite` / vitest cache flake. Worktrees symlink main's `node_modules`, so those
  caches are shared even though the test DBs are not.
- `TS2307` / `TS2305` / `TS6305` — §4's provisioning did not run, or ran wrong. Never the PR's defect.

### Parallel-gate isolation

`test:integration` from a **linked worktree** derives its own database (`plantaopro_test_<dir>`)
automatically — `integration-setup.ts` detects the worktree and publishes the URL the app pool reads,
so a bare declared `verify:` is already isolated and needs no env prefix. That closes both
cross-worktree deadlocks (40P01: one run's `afterEach` `TRUNCATE` vs the other's inserts) and schema
contamination (the shared DB accumulates the union of every branch's migrations and no migration can
undo it). `/cleanup` drops stray `plantaopro_test_*`; `PLANTAOPRO_TEST_DB_SHARED=1` opts back into
the shared DB and must not be used inside a run. The MAIN checkout still uses shared
`plantaopro_test`, so two agents gating there still need serializing.

Stateless gates may run in parallel. If they still flake each other, serialize the whole gate stage:
implement in parallel, gate one PR at a time.

## §11 — Trap domains

The D1 negative list (adw-core §3) and the build-side depth envelope (adw-build §3.1). Mechanical on
both sides: one path prefix, then greps over the diff's added/changed lines.

| Domain | Match |
|---|---|
| migrations | path prefix `api/drizzle/` |
| money | `formatMoney\|money\.ts\|cents` |
| date/TZ | `date\.ts\|fromDateKey\|toDateKey\|toISOString\|getUTC\|new Date\(` |
| authz | `resolve\w*Access\|middleware/` |
| scope/fan-out | `scope.*(future\|all)\|applyTo` |
| settings allowlist | `SETTINGS_ALLOWLIST\|UserSettings` |
| transactions | `db\.transaction\|\btx\.` |
| live sync | `pg_notify\|fetchEventSource\|useSSE` |

Deliberately coarse proxies — a false hit costs a bounce to D2, the cheap direction. Tune from run
evidence, never toward judgment calls.

**`api/` and `packages/` were prefixes here until 2026-09-09 and are not any more** — the general
rule and the measurement are adw-core §3. `transactions` and `live sync` are the `api/` risks the
original grep set missed, which is why that was a swap rather than a removal. `packages/shared`
needs no row: a schema widening is the best gate-covered surface in this repo (`tsc` catches a
missing `pack:shared`, the integration test catches a silent strip), and the real trap it proxied
for — a DB column with no shared-schema field — is an *absence* no path match can see.

**Soft delete is deliberately not a row** despite being a real trap — measurement and reasoning in
adw-core §3. `api/CONVENTIONS.md` §13/§37 and the mandatory `test:integration` rule cover it.

Additional trap domains a critical pass names even when nothing above matches: analytics events.

## §12 — Running a single test

`npm run test:integration -t "name"` **drops the flag** and fails always. It needs `--`:
`npm run test:integration -- -t "name"`. And `-t` with a stale name exits 0 with everything skipped,
which reads as green.

Prefer file paths over `-t`, but a path list is not proof either. Vitest reports `No test files found`
(exit 1) only when **every** path argument misses; one stale path among several live ones, or a
directory argument, still reports the live ones as passed and silently drops the missing file.

A verify that must prove a unit's added files survived a later mutation needs an existence guard
before any gate runs:

```bash
for f in <paths>; do [ -f "$f" ] || { echo "VERIFY missing $f"; exit 1; }; done && <gates>
```

Modified files don't need this guard — a revert leaves the file on disk, so an existence check can
never fire on one. What covers them is the per-file mutation sweep (adw-build §3.2).

An aggregate-mutation red can be a database-state artifact rather than real proof. A reverted
migration `.sql` doesn't drop the index it already created in the worktree's test DB, so a fixture can
collide and red for the wrong reason. Confirm why a mutation red happened before banking it.

## §13 — Review layers and their standards docs

Read by `/code-review` Phase 2. Classify each changed file; the union is `layers[]`.

| Pattern | Layer | Ref |
|---|---|---|
| `api/src/db/schema/` | DB schema | `api/CONVENTIONS.md`, `docs/backend_standards.md` |
| `api/src/handlers/`, `api/src/services/` | Business logic | `api/CONVENTIONS.md` |
| `api/src/middleware/` | Auth/middleware | `api/CONVENTIONS.md` |
| `api/src/routes/` | Route definitions | `api/CONVENTIONS.md` |
| `packages/shared/` | Shared schemas | `CLAUDE.md` |
| `src/components/`, `src/pages/`, `src/features/` | Frontend | `docs/ui_standards.md` |
| `src/hooks/`, `src/services/`, `src/stores/` | Frontend logic/state | `CLAUDE.md` |
| `api/migrations/`, `api/drizzle/` | DB migrations | `CLAUDE.md` §7 (idempotency) |
| `.github/workflows/` | CI/CD workflows | no standards doc — the workflow file IS the contract |

**Ignore** (these produce no layer): lockfiles, `assets/`, `*.svg`/`*.png`, `.md` docs (except
`.agent/tasks/**`), `.json` configs unless schema or migration.

## §14 — Risk scoring

Read by `/code-review` Phase 3. Each row scores at most once.

| Signal | Pts | Detection |
|---|---|---|
| Auth/middleware code | +4 | Files in `api/src/middleware/` or matching `*auth*`/`*security*` |
| `api/src/db/schema/` touched | +4 | Schema = migration risk |
| `api/migrations/` or `api/drizzle/` touched | +4 | Migration DDL — idempotency required (CLAUDE.md §7) |
| `packages/shared/` touched | +3 | Cross-boundary schema change (front+back consume) |
| `api/src/handlers/` or `api/src/services/` | +3 | Business logic changes |
| `api/src/routes/` touched | +2 | Route/endpoint changes |
| Root config touched (`package.json`, `tsconfig*.json`, `vite.config*`, `drizzle.config*`) | +3 | Build/type/migration tooling |
| `.github/workflows/` touched | +5 | Ships to an environment, and NO other gate reads these files. Crosses the threshold alone, deliberately |
| `.claude/commands/`, `.claude/skills/` or a root `.claude/*.md` | +3 | Affects every future agent run — the root glob covers `.claude/repo-profile.md`, this file |
| New feature (>3 added files) | +2 | `git diff --diff-filter=A --name-only` |
| >500 lines changed | +2 | `--stat` |
| >10 files changed | +1 | `--name-only` count |

**Why `.github/workflows/` scores +5 and not +3.** It is the only file class here that no gate reads:
`tsc` does not parse it, `eslint` does not lint it, `audit.sh` does not grep it, and a YAML scalar
that silently truncates on a ` #` is green everywhere until a release runs. Its two failure modes
are shipping broken code to production and stopping every release, and both land after review is
over. +5 crosses the `full` bar unaided so the tier never depends on the diff also happening to be
large — a deploy-workflow change is typically a handful of lines. Scored 0 before 2026-09-03: PR
#1134 rewrote the production deploy job and took the light path. The matching §13 layer row lands
with it and is not optional — without a layer, `layers[]` stays empty and the plugin is skipped.

## §15 — Review emphasis

Read by `/code-review` Phase 4.

**Stack context to hand a review agent:** production npm-workspaces monorepo — React 19 / Vite
frontend (`src/`), Hono.js + PostgreSQL API (`api/`), shared Zod schemas (`packages/shared/`).

**Weight above style polish:** bugs and logic errors · `CLAUDE.md` / `api/CONVENTIONS.md` /
`docs/ui_standards.md` violations · cross-boundary schema sync (a DB column with no
`packages/shared/` field) · soft-delete misuse · transaction misuse (`db` instead of `tx`) ·
missing `notDeleted()` on management reads · missing analytics events on user-facing actions ·
missing TanStack Query keys · SSE listener cleanup.

**Composition check — read whole files, not only hunks.** For every changed file under
`api/src/handlers/**` or `api/src/services/**`, read its current full contents and ask what the new
code does to code it did not change. Two locally-correct hunks in one file can break each other: an
upstream block that resolves an omitted field to its current value makes a downstream
`=== undefined ? {} : …` no-op unreachable. That is #751's H2 — ~30 lines apart, both halves
correct, third occurrence of the class.

### Blocking severity classes

A finding is upgraded from `Warning` to `Blocking` when its description names any of:

- migration without `IF NOT EXISTS`
- transaction using `db` instead of `tx`
- missing `notDeleted()` on a management read
- auth/middleware regression
- `any` type in production code
- secret/credential leak
- **a write path that persists a field the request did not mention** (an omitted field resolved to
  its current value, then written)
- **a fan-out or recurrence update** (`scope: 'future'`, bulk `.set()` over sibling rows, cascade
  writes)
- **a discharge / close / terminal-state transition**

The last three cover **silent data corruption** — the class that reaches no crash reporter and no
gate. Added 2026-07-18 because #751's H2 (`scope: 'future'` rewriting `end_date` on every forward
occurrence) would otherwise be graded `Warning`, and only `Blocking` is protected from calibration
suppression (`review-core.md` §6.6) and from unilateral rejection by the fixer.

## §16 — Project rule tables

Read by `/code-review` Phase 5.2 (grep-shaped rules) and Phase 5.3 (structural, sub-agent).

### 16.1 — Backend (`api/`) — ref `api/CONVENTIONS.md`, `docs/backend_standards.md`

| # | Anti-pattern | How to detect | Severity |
|---|---|---|---|
| 1 | `db.` inside `db.transaction(tx)` callback | Grep `db\.(select\|insert\|update\|delete)` inside `db.transaction` blocks | Blocking |
| 2 | Missing `notDeleted()` on management read of soft-deletable table | SELECT on `users`/`teams`/`professionals`/`templates`/`fontes_pagadoras`/`infirmary_lists` without `notDeleted()` in management context | Blocking |
| 3 | `notDeleted()` in display JOIN | LEFT JOIN on soft-deletable table for embed should omit `notDeleted()` and add `isDeleted` flag (CONVENTIONS §37) | Warning |
| 4 | `:id` path param without validation | Missing `if (!id)` or `z.string().min(1)` | Blocking |
| 5 | `Record<string, unknown>` for update payload | Should be `Partial<typeof table.$inferInsert>` | Warning |
| 6 | Hidden field uses `.optional()` not `.nullish()` | Role-hidden fields need `.nullish()` + `!= null` diff (CONVENTIONS §38) | Blocking |
| 7 | Spread + denylist for public response | Should be allowlist of safe fields (CONVENTIONS §42) | Warning |
| 8 | Migration DDL without `IF NOT EXISTS` guard | `ADD COLUMN`/`CREATE TABLE`/`CREATE INDEX` lacking `IF NOT EXISTS` — CLAUDE.md §7. **`CREATE TYPE` and `ADD CONSTRAINT` also require guards but `audit.sh` does not grep them** — check those by reading the `.sql`, not by trusting the audit's green | Blocking |
| 9 | Missing `.js` extension in relative API import | `from '\.\./[^']+'` without `.js` suffix in `api/src/**` | Blocking |
| 10 | Response not using helpers | Returns raw `c.json` instead of `sendSuccess`/`sendCreated`/`sendNoContent` | Warning |

### 16.2 — Frontend (`src/`) — ref `docs/ui_standards.md`, `CLAUDE.md`

| # | Anti-pattern | How to detect | Severity |
|---|---|---|---|
| 11 | `if (!open) return null` before Dialog/Drawer | Early-return unmounts Radix tree → leaks `aria-hidden`/scroll-lock | Blocking |
| 12 | Flex/`<fieldset>` without `min-w-0` | Shrinkable child of flex/form layout missing `min-w-0` | Warning |
| 13 | Manual JS truncation (`substring + '...'`) | Should use CSS `truncate` class | Warning |
| 14 | New form using `useState` + custom debounce | New forms should use `react-hook-form` + `useFormAutoSave` | Warning |
| 15 | New user action without analytics event | Action handler in changed file calls API but no `analyticsService.trackEvent` after success | Warning |

### 16.3 — Cross-boundary (`packages/shared/`)

| # | Anti-pattern | How to detect | Severity |
|---|---|---|---|
| 16 | New DB column without shared Zod field | Column added in `api/src/db/schema/` not present in matching `packages/shared/src/schemas/*.ts` (frontend `Schema.parse()` silently strips) | Blocking |
| 17 | Fan-out update writes a field the request never mentioned | In any `scope === 'future'` / bulk-update block: an upstream line assigning `updateData.<field> = <existing/base value>` on **every** branch, feeding a downstream `<field> === undefined ? {} : …` no-op. The assignment makes the no-op unreachable, so a PATCH of an unrelated field rewrites `<field>` on every sibling row. Both halves read correct alone. Third occurrence of this class (`2205d105`, PR #751 H2, still live — Trello #167) | Blocking |
| 18 | State-transition assertion in a mocked handler test | A test under `api/src/handlers/__tests__/*.test.ts` (not `*.integration.test.ts`) that stubs the pre-state, stubs the post-state, then asserts the handler's `.set()`/`.values()` payload against that stub. It asserts the author's own belief back at itself and cannot detect divergence. Must be an integration test reading rows back from Postgres — CLAUDE.md "State-transition changes" | Blocking |

### 16.4 — Structural checks (sub-agent verification, not grep)

- **For new endpoints** (new files in `api/src/handlers/`): handler exists, route registered in
  `api/src/routes/`, Zod schema in `packages/shared/` if a new resource. User-facing actions have a
  corresponding analytics event (`docs/analytics_standards.md`).
- **For new SSE listeners** (`fetchEventSource` / `useSSE` / `useEnfermariaSSE` in changed files):
  the `useEffect` return calls `.abort()` on the `AbortController` (`src/hooks/useSSE.ts`). This app
  has no `new EventSource` — cleanup is abort, not close.
- **For new TanStack Query mutations:** `onSuccess` invalidates the relevant query key(s), or the
  query keys are documented in the PR.
- **For new Drizzle migrations** (`api/drizzle/migrations/*.sql`): DDL is idempotent
  (`IF NOT EXISTS` / `DO $$ EXCEPTION`); multi-table operations wrapped in a transaction whose body
  uses `tx`, not `db`.
- **For new shared Zod schema fields:** `npm run pack:shared` artifacts committed, or the PR notes
  it must be re-packed.

## §17 — Convention doc routing

Read by `/code-review` Phase 6.2 — where a convention `Insert` draft is targeted.

| The finding's surface | Target doc |
|---|---|
| `api/` | `api/CONVENTIONS.md` |
| `src/` | `docs/ui_standards.md` |
| cross-cutting / a forbidden-pattern table entry | `CLAUDE.md` |
| analytics | `docs/analytics_standards.md` |
| backend architecture | `docs/backend_standards.md` |

## §18 — Disposable state

Read by `/cleanup` Phase 3. Everything a session can leave behind **besides** worktrees and
branches, which `/cleanup` handles on its own.

### 18.1 — Inside the worktree — reclaimed for free

A worktree's Vite/Vitest/tsc caches live in its own `.cache/` (`scripts/cache-dir.ts`, Trello #228),
which is gitignored. `git worktree remove` reclaims them with the directory. **No separate sweep,
and no leaked directory per worktree.**

### 18.2 — test-env stacks

| | |
|---|---|
| **Discovery** | `find "$MAIN" -type d -name .test-env` |
| **State record** | `<dir>/state.env`, keys `ST_apiPort ST_frontPort ST_apiPid ST_frontPid ST_testDb ST_envLocal …` |
| **Liveness probe** | `lsof -tiTCP:"$ST_apiPort" -sTCP:LISTEN` (and the front port) — any hit ⇒ live |
| **Teardown** | `bash "<root>/scripts/test-env.sh" down` — no preflight; safe even with a missing `.env` or docker down. It also restores `.env.local` and drops the guarded DB |
| **Name guard** | `^plantaopro_test_[A-Za-z0-9_]+$` |
| **Off-limits** | the dev DB `plantaopro` |

Fallback when the script errors or the worktree is already gone — read `state.env` and do it by hand:

```bash
source "<dir>/state.env"
for p in "$ST_apiPort" "$ST_frontPort"; do [ -n "$p" ] && kill $(lsof -tiTCP:"$p" -sTCP:LISTEN 2>/dev/null) 2>/dev/null || true; done
[[ "$ST_testDb" =~ ^plantaopro_test_[A-Za-z0-9_]+$ ]] && \
  docker exec plantaopro-db psql -U plantaopro_user -d postgres -c "DROP DATABASE IF EXISTS \"$ST_testDb\" WITH (FORCE)" 2>/dev/null || true
```

### 18.3 — Shared sweep: orphan test databases

Run **once**, at the end of `/cleanup` Phase 5, excluding every DB owned by a kept LIVE stack.
Skip silently when the `plantaopro-db` container is not running.

```bash
KEEP=<'|'-joined ST_testDb of every kept LIVE stack>   # glob alternation for the `case` below
docker exec plantaopro-db psql -U plantaopro_user -d postgres -tAc \
  "SELECT datname FROM pg_database WHERE datname LIKE 'plantaopro_test_%'" \
| while read db; do
    case "$db" in $KEEP) continue;; esac
    [[ "$db" =~ ^plantaopro_test_[A-Za-z0-9_]+$ ]] && \
      docker exec plantaopro-db psql -U plantaopro_user -d postgres -c "DROP DATABASE IF EXISTS \"$db\" WITH (FORCE)"
  done
```

`docker exec … psql` with a heredoc needs `-i`; without it the heredoc runs nothing and exits 0.
The form above passes `-c`, so it is unaffected — keep it that way.
