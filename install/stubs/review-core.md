---
description: Shared machinery for /code-review and /spec-review. Read by each skill at its Phase 1 — not invoked directly.
---

# review-core — loader

The contract for this command is **not in this repo**. Fetch it, then read it.

1. `bash .claude/adw/fetch.sh` — prints `adw contract <sha>`. Keep that sha; it is `CONTRACT_SHA`.
2. Read `.claude/adw/cache/commands/review-core.md` **in full**. That file is the contract; this file is
   only the loader and binds nothing.
3. While reading it: every `repo-profile §N` resolves to `.claude/repo-profile.md` in THIS repo.
   Every `design §N` resolves to `.claude/adw/cache/docs/00-design.md`.

If step 1 fails and `.claude/adw/cache/` is empty, **stop and tell the user**. Do not run this
command from memory.
