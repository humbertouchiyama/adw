# Tracker intake — ADW reads the card and builds the intent

Status: settled, contract edits written. Date: 2026-11-14.

## 1. Problem

adw-core §10 keeps a card's status up to date, but only for a card the owner already pasted into
the intent text. ADW never reads the card. A consuming repo built a wrapper (`linear-adw`) to do
the missing part, and the wrapper still does four things ADW does not:

1. Read the issue and build the intent from it.
2. Refuse issues that are Done or Canceled.
3. Stop on a product question in the issue.
4. Take designs (`--design`) as input.

A tracker integration that cannot read the issue is half built. These four jobs belong in ADW so
every repo gets them and no wrapper is needed.

## 2. Goal

`/adw <ref>` (or `/adw-init <ref>`) where `<ref>` is a card ref (adw-core §10) reads the card, builds
the intent from it, and goes on as a normal intent. The wrapper can be deleted.

## 3. Behaviour

Runs in `/adw-init` Phase 0.5, after the §10 connection read, only when the **whole** intent text is
one ref (a Trello URL/shortlink, a `linear.app` URL, `Linear <KEY>`). A ref inside longer free text
keeps today's behaviour: the text is the intent, the ref is only tracked.

| # | Rule |
|---|---|
| T1 | **Read.** Fetch title, description, labels, status, comments and attachments through the §10 read tools. Not connected → stop: `⚠ card <ref>: cannot read — paste the intent as text`. This is the one place a tracker problem stops the run, because there is no intent without the read. |
| T2 | **Intent.** Title plus description, newest decision comments after them. Attachments and links are listed, not followed. The intent text printed on the approval surface is the built text, so the owner sees what triage saw. |
| T3 | **Refuse closed.** Card status equals `repo-profile §22` `done`, or is a Canceled/archived state (Linear `Canceled`/`Duplicate`, Trello archived) → stop: `⚠ card <ref>: already <status> — nothing to build`. `--force-closed` overrides and is printed. |
| T4 | **Product question.** No special stop. The built intent goes to triage like any intent; a product question in the issue becomes a `needs you` row at the approval gate, and the owner is asked there only if triage cannot settle it. The card is not moved to `started` until `/adw-build` starts, as today. |
| T5 | **Designs.** `--design <path-or-url>` (repeatable), plus image/Figma attachments on the card, go into the intent as a `designs:` list. Triage and the specs cite them; a port unit (§20) takes them as its visual reference. |
| T6 | **Header.** `card:` is written as today (adw-core §2). Nothing else is added to the header. |

## 4. Files

| File | Change |
|---|---|
| `commands/adw-core.md` §10 | Add the "Intake" bullet: T1–T3 and T6, one paragraph. |
| `commands/adw-init.md` | Input: add `--design`, `--force-closed`; Phase 0.5: run intake before triage. |
| `commands/adw-core.md` §7 approval | Print `card` line with status and the `designs` list. |
| `docs/repo-profile-EXAMPLE.md` §22 | Add the Canceled status names the repo's tracker uses; no new section. |
| `install/stubs/adw.md` | Usage line takes `<intent or card ref>`. |

No new repo-profile section. Status names stay §22; tracker tool names stay §10.

## 5. Out of scope

- Writing back to the card beyond the three §10 moves.
- Following links inside the card.
- Intake for a bare `ABC-123` (still not a ref, §10).
- Batch intake of a whole board or cycle.

## 6. Decisions (settled 2026-11-14)

- **C1** No separate stop for product questions. Triage evaluates them and the existing approval gate escalates.
- **C2** `--force-closed` is allowed.
- **C3** Consuming repo deletes `linear-adw` in its own PR after this merges.
