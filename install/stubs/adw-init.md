---
description: "ADW entry point: intent → triage → human-approved unit cut → per-unit specs/plans → builds them. `approve` at the gate runs /adw-build in the same session; `specs only` stops after the specs. Usage: /adw-init <intent>"
---

# adw-init — loader

The contract for this command is **not in this repo**. Fetch it, then read it.

1. Run `bash .claude/adw/fetch.sh` and **read its exit code and its output line**:
   - **exit 0** — `adw contract <sha> (<ref>, fetched)`. Proceed. `<sha>` is `CONTRACT_SHA`.
   - **exit 2** — `adw contract <sha> (<ref>, CACHED — NOT VERIFIED)`. The fetch failed and this is
     a cache of unknown age. Proceed, and carry `⚠ contract from cache, not verified against
     origin (<sha>)` on the run report, the approval surface and the PR evidence block. Do not
     print this sha as if it were verified.
   - **exit 1** — no usable contract. **Stop and tell the user.** Do not run from memory.
2. Read `.claude/adw/cache/commands/adw-init.md` **in full** before doing anything else. That file
   is the contract; this file is only the loader and binds nothing. Reading a summary of it, or
   acting on what you remember of it, is the one failure this design cannot detect.
3. While reading it: every `repo-profile §N` resolves to `.claude/repo-profile.md` in THIS repo.
   Every `design §N` resolves to `.claude/adw/cache/docs/00-design.md`.

Never edit anything under `.claude/adw/cache/` — the next fetch discards it without asking. A
change the contract needs is a PR to the `adw` repo.
