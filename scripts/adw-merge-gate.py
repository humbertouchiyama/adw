#!/usr/bin/env python3
"""adw-merge-gate.py: the auto-merge gate of adw-build §3.7 (design docs/specs/2026-10-30-adw-auto-merge-design.md §4.2).

  python3 adw-merge-gate.py check --repo <owner/repo> --pr <N> --profile <local repo-profile.md>
      --spec-path <repo path> [--spec-path ...]

Every condition is read fresh from GitHub or the profile, never from the run's memory. It prints one line:
`pass` (exit 0), or `hold <n> <reason>` (exit 1) for the first condition that fails, in this order:
1 flag (the specs' `merge: auto`, both profiles' `auto-merge default`, no `adw:hold`), 2 base, 3 verified head,
10 the design sign-off (the evidence block's `visual` row still reads `sign-off pending`, adw-build §3.2a),
4 paths (merge-protected, money lines outside the test sources), 5 GitHub (mergeable, checks), 7 the walk, 8 the screenshots,
9 `Smoke: none` / `Screens: none` against the UI paths. Every input fails closed: the merge-protected,
UI and money rows are read from both the local profile and the base's copy, the stricter wins, and a
missing merge-protected row holds; paths come from the full diff (both sides of a rename); `merge:` and
`base:` are read from the spec header only; a walk `D` row that is not `polish` holds unless a `refuted:`
or `polish:` line clears it. Condition 6 is the base trial:

  python3 adw-merge-gate.py trial --checkout <main checkout> --pr <N> --slug <slug> --base <branch> --head <sha>
  python3 adw-merge-gate.py discard --checkout <main checkout> --tree <path>

`trial` prints `base unmoved` (exit 0) when origin/<base> is still the fork point; `hold 6 overlap: <files>`
(exit 1) when the base's new commits touch a file the PR touches; else it merges origin/<base> into the head
in a detached worktree `.claude/worktrees/adw-trial-<slug>-pr<N>` and prints `tree <path> base <sha>` (exit 0),
or aborts, removes the tree and prints `hold 6 conflict: <files>` (exit 1). The PR head never moves, so
`ready`, the walk and the screenshots still hold. The caller runs the gates in the tree, then `discard`
removes it, never with --force: a tree with any change past the merge stays, and discard exits 1.
The merge itself is the script's too, so no merge into a base runs without the gate:

  python3 adw-merge-gate.py merge --repo <owner/repo> --pr <N> --head <full sha> --base <branch>
      --profile <local repo-profile.md> --spec-path <repo path> [--spec-path ...] [--flag squash|merge|rebase]
  python3 adw-merge-gate.py merge --sub --repo <owner/repo> --pr <N> --head <full sha> --slug <slug>
  python3 adw-merge-gate.py merge --owner --repo <owner/repo> --pr <N> --head <full sha>
      --profile <local repo-profile.md> [--base <branch>] [--flag squash|merge|rebase] [--delete-branch]

The gate mode (independent and final PRs, adw-build §3.7) runs `check` again, then needs the base to equal
--base, the head to equal --head and no `adw:hold` label. `--sub` (a sub-PR into its integration branch)
needs the base `adw/<slug>` and the evidence block's `verified` row to equal the head and --head; it always
squashes. `--owner` (the owner said "merge") needs the head to equal --head, and --base when it is given;
it runs no `check`, because the owner's word overrides the flag. Every mode refuses a base that either copy
of the profile names as the production branch. The merge is `gh pr merge --match-head-commit <head>`, then a
`gh pr view` that must read MERGED (its exit code is not reliable when a worktree holds the branch); a
failed call is retried once, and a read-back that fails three times is never retried as a merge. It prints
`merged <merge sha7>` (exit 0), `hold <n> <reason>` (exit 1), or `hold call — <gh error>` (exit 1) when the
merge call or its read-back fails.
A gh call that fails, or a bad flag, prints `hold 0 gate error: <message>` and exits 2: the contract
treats it as a hold. ADW_GATE_POLL_SECONDS (default 30) spaces the re-queries: 5 for an UNKNOWN
mergeable state, 16 for a pending check, and all polling stops after
ADW_GATE_BUDGET_SECONDS (default 420), so the line prints inside a 600000 ms Bash call.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from urllib.parse import quote

PROFILE_PATH = ".claude/repo-profile.md"
POLL = float(os.environ.get("ADW_GATE_POLL_SECONDS", "30"))
UNKNOWN_QUERIES = 5
PENDING_QUERIES = 16
# All polling stops once this many seconds have passed, so the line prints inside adw-build §3.7's
# 600000 ms Bash timeout with room for the gh calls that follow.
BUDGET = float(os.environ.get("ADW_GATE_BUDGET_SECONDS", "420"))
START = time.monotonic()


def over_budget() -> bool:
    return time.monotonic() - START + POLL > BUDGET


class Hold(Exception):
    def __init__(self, n: int, reason: str):
        super().__init__(reason)
        self.n, self.reason = n, reason


class GateError(Exception):
    pass


def run_gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], capture_output=True, text=True)


def gh(*args: str, missing_ok: bool = False) -> str | None:
    p = run_gh(*args)
    if p.returncode != 0:
        if missing_ok and "404" in p.stderr:
            return None
        raise GateError("gh %s: %s" % (" ".join(args[:2]), (p.stderr.strip().splitlines() or ["exit %d" % p.returncode])[-1]))
    return p.stdout


def contents(repo: str, path: str, ref: str) -> str | None:
    return gh("api", "-H", "Accept: application/vnd.github.raw", "repos/%s/contents/%s?ref=%s" % (repo, quote(path), ref),
              missing_ok=True)


# ---- repo-profile tables --------------------------------------------------------------------------

def glob_re(glob: str) -> re.Pattern:
    """`**/` = any directories (none included), `**` = anything, `*` = within one segment; anchored."""
    out, i = "", 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif glob.startswith("**", i):
            out, i = out + ".*", i + 2
        elif glob[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif glob[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(glob[i]), i + 1
    return re.compile(out + r"\Z")


def ticks(cell: str) -> list[str]:
    return re.findall(r"`([^`]+)`", cell)


class Profile:
    def __init__(self, text: str):
        self.sections: dict[str, dict[str, str]] = {}
        sec = ""
        for line in text.splitlines():
            m = re.match(r"^## §(\d+)\b", line)
            if m:
                sec = m.group(1)
                continue
            if line.lstrip().startswith("|"):
                cells = re.split(r"(?<!\\)\|", line.strip())
                if len(cells) < 4:
                    continue
                role = cells[1].replace("**", "").replace("`", "").strip().lower()
                if role and not set(role) <= set("-: "):
                    self.sections.setdefault(sec, {}).setdefault(role, cells[2].strip())
        s3 = self.sections.get("3", {})
        auto = s3.get("auto-merge default")
        self.auto = auto.replace("`", "").strip().lower() if auto is not None else None
        # A row whose cell holds no glob in backticks protects nothing, so it counts as no row.
        self.has_protected = bool(ticks(s3.get("merge-protected paths", "")))
        self.protected = [glob_re(g) for g in ticks(s3.get("merge-protected paths", ""))]
        ui = s3.get("ui paths")
        self.ui = [glob_re(g) for g in ticks(ui)] if ui is not None and ticks(ui) else None
        # §3 test sources: their added lines are no money lines. No row, or no glob in it, exempts nothing.
        self.tests = [glob_re(g) for g in ticks(s3.get("test sources", ""))]
        self.production = (ticks(s3.get("production branch", "")) or [None])[0]
        convention = s3.get("merge convention", "").replace("`", "").strip().lower().split()
        self.convention = convention[0] if convention else None
        self.default_base = (ticks(s3.get("default base", "")) or [None])[0]
        self.excluded = [glob_re(g) for g in re.findall(r"':!([^']+)'", self.sections.get("2", {}).get("artifact exclusion pathspec", ""))]
        money = self.sections.get("11", {}).get("money", "")
        self.money_unreadable = "money" in self.sections.get("11", {}) and not ticks(money)
        self.money_prefix = ticks(money)[0] if "path prefix" in money and ticks(money) else None
        pattern = ticks(money)[0].replace("\\|", "|") if ticks(money) and not self.money_prefix else None
        self.money = re.compile(pattern) if pattern else None


def matches(globs: list[re.Pattern], path: str) -> bool:
    return any(g.match(path) for g in globs)


# ---- the PR body ----------------------------------------------------------------------------------

def section(body: str, heading: str, stop_marker: str | None = None) -> str | None:
    lines, out, on = body.splitlines(), [], False
    for line in lines:
        if not on:
            if re.match(r"^## %s[ \t]*$" % re.escape(heading), line):
                on = True
            continue
        if line.startswith("## ") or (stop_marker and line.startswith(stop_marker)):
            break
        out.append(line)
    return "\n".join(out) if on else None


# ---- the conditions -------------------------------------------------------------------------------

def header(spec: str) -> str:
    """The spec's header: every line before its first `## ` heading. merge: and base: live there."""
    out = []
    for line in spec.splitlines():
        if line.startswith("## "):
            break
        out.append(line)
    return "\n".join(out)


def flag(pr, local: Profile, basep: Profile | None, specs: dict[str, str | None]) -> None:
    labels = {l["name"] for l in pr["labels"]}
    if "adw:hold" in labels:
        raise Hold(1, "the PR has the adw:hold label")
    values = {}
    for path, text in specs.items():
        if text is None:
            raise Hold(1, "spec %s is not at the head %s" % (path, pr["headRefOid"][:7]))
        m = re.search(r"^merge:[ \t]*(auto|hold)[ \t]*(#.*)?$", header(text), re.M)
        if not m:
            raise Hold(1, "spec %s has no merge: line (omitted = hold)" % path)
        values[path] = m.group(1)
    if len(set(values.values())) > 1:
        raise Hold(1, "the specs disagree on merge: (%s)" % ", ".join("%s %s" % (p, v) for p, v in values.items()))
    if "hold" in values.values():
        raise Hold(1, "the spec says merge: hold")
    for where, prof in (("the local profile", local), ("the profile on %s" % pr["baseRefName"], basep)):
        if prof is None:
            raise Hold(1, "%s is missing" % where)
        if prof.auto is None:
            raise Hold(1, "%s has no auto-merge default row" % where)
        if prof.auto != "on":
            raise Hold(1, "auto-merge default is %s in %s" % (prof.auto, where))


def base_profile(a, pr) -> Profile | None:
    text = contents(a.repo, PROFILE_PATH, pr["baseRefName"])
    return Profile(text) if text is not None else None


def base(pr, local: Profile, specs: dict[str, str | None]) -> None:
    bases = {m.group(1) for t in specs.values() if t for m in [re.search(r"^base:[ \t]*(\S+)", header(t), re.M)] if m}
    if len(bases) > 1:
        raise Hold(2, "the specs disagree on base: (%s)" % ", ".join(sorted(bases)))
    intent = bases.pop() if bases else local.default_base
    if pr["baseRefName"] != intent:
        raise Hold(2, "the PR's base %s is not the intent's base %s" % (pr["baseRefName"], intent))
    if local.production and pr["baseRefName"] == local.production:
        raise Hold(2, "the PR's base %s is the production branch" % pr["baseRefName"])


def verified(pr) -> None:
    bad = {"adw:blocked", "adw:failed"} & {l["name"] for l in pr["labels"]}
    if bad:
        raise Hold(3, "the PR has the %s label" % sorted(bad)[0])
    m = re.search(r"^[ \t]*verified[ \t]+([0-9a-f]{40})\b", pr["body"], re.M)
    if not m:
        raise Hold(3, "the evidence block has no verified row")
    if m.group(1) != pr["headRefOid"]:
        raise Hold(3, "verified %s is not the head %s" % (m.group(1)[:7], pr["headRefOid"][:7]))


def signoff(pr) -> None:
    """10: the owner signs the design off once per run, before any merge into a base (adw-build §3.2a)."""
    if re.search(r"^[ \t]*visual[ \t]+rows\b.*\bsign-off[ \t]+pending\b", pr["body"], re.M):
        raise Hold(10, "the design sign-off is pending")


def unquote(p: str) -> str:
    """A path as git prints it: plain, or C-quoted ("b/pre\\303\\247o.ts") when it has unusual bytes."""
    if len(p) >= 2 and p[0] == '"' and p[-1] == '"':
        import codecs
        return codecs.escape_decode(p[1:-1].encode("latin-1", "backslashreplace"))[0].decode("utf-8", "replace")
    return p


def side(p: str) -> str | None:
    p = unquote(p.strip())
    if p == "/dev/null":
        return None
    return p[2:] if p[:2] in ("a/", "b/") else p


def parse_diff(text: str) -> list[dict]:
    """Each file of a unified diff: every path it names (both sides of a rename or copy) and its added
    lines. Header lines count only before the file's first hunk, so an added line that reads `++ x`
    is content, never a header."""
    files, cur, hunk = [], None, False
    for line in text.splitlines():
        if line.startswith("diff --git "):
            cur, hunk = {"paths": set(), "path": None, "added": []}, False
            files.append(cur)
            rest = line[len("diff --git "):]
            q = re.findall(r'"(?:[^"\\]|\\.)*"', rest)
            halves = q if len(q) == 2 else ([rest[:len(rest) // 2], rest[len(rest) // 2 + 1:]]
                                            if rest[:len(rest) // 2][2:] == rest[len(rest) // 2 + 1:][2:] else [])
            if not halves:
                m = re.match(r"(a/.+) (b/.+)$", rest)
                halves = [m.group(1), m.group(2)] if m else []
            cur["paths"].update(x for x in map(side, halves) if x)
            continue
        if cur is None:
            continue
        if not hunk:
            if line.startswith("@@"):
                hunk = True
            elif line.startswith(("--- ", "+++ ")):
                p = side(line[4:])
                if p:
                    cur["paths"].add(p)
                    if line.startswith("+++ "):
                        cur["path"] = p
            else:
                m = re.match(r"(?:rename|copy) (?:from|to) (.+)$", line)
                if m:
                    cur["paths"].add(unquote(m.group(1)))
            continue
        if line.startswith("+"):
            cur["added"].append(line[1:])
    return files


def read_diff(a) -> list[dict]:
    d = run_gh("pr", "diff", str(a.pr), "--repo", a.repo)
    if d.returncode != 0:
        raise Hold(4, "the diff cannot be read: %s" % (d.stderr.strip().splitlines() or ["exit %d" % d.returncode])[-1])
    return parse_diff(d.stdout)


def paths(profiles: list[Profile], files: list[dict]) -> None:
    """Every safety row is read from both the local and the base copy of the profile, the stricter wins."""
    for prof in profiles:
        if not prof.has_protected:
            raise Hold(4, "the profile has no merge-protected paths row with a glob in backticks")
        if prof.money_unreadable:
            raise Hold(4, "the profile's money row has no pattern in backticks")
    for f in files:
        for p in sorted(f["paths"]):
            if any(matches(prof.protected, p) for prof in profiles):
                raise Hold(4, "%s is a merge-protected path" % p)
            if all(matches(prof.excluded, p) for prof in profiles):
                continue
            # Every path, either side of a rename, deletions and binary files included: the money row
            # names files too (`money\.ts`), and a change there needs no money word in its lines.
            for prof in profiles:
                if prof.money_prefix and p.startswith(prof.money_prefix):
                    raise Hold(4, "%s is under the money path %s" % (p, prof.money_prefix))
                if prof.money and prof.money.search(p):
                    raise Hold(4, "%s is a money file" % p)
    for f in files:
        path = f["path"]
        if path is not None and all(matches(prof.excluded, path) for prof in profiles):
            continue
        # A test source never ships, so a money word in it (an assertion, a test name) changes no money:
        # AXCMedApp #807 and #768 held for one. Every path of the file (both sides of a move) must be a test
        # source in every profile (the stricter wins); a money file name above still holds.
        if f["paths"] and all(matches(prof.tests, p) for prof in profiles for p in f["paths"]):
            continue
        for line in f["added"]:
            for prof in profiles:
                if prof.money and prof.money.search(line):
                    raise Hold(4, "%s adds a money line: %s" % (path or "a file", line.strip()[:80]))


def github(a, pr) -> None:
    state = pr.get("mergeable")
    for n in range(UNKNOWN_QUERIES):
        if state == "MERGEABLE":
            break
        if state != "UNKNOWN":
            raise Hold(5, "GitHub says the PR is %s" % state)
        if n == UNKNOWN_QUERIES - 1 or over_budget():
            raise Hold(5, "mergeable is still UNKNOWN after %d queries" % (n + 1))
        time.sleep(POLL)
        state = json.loads(gh("pr", "view", str(a.pr), "--repo", a.repo, "--json", "mergeable,mergeStateStatus"))["mergeable"]
    for n in range(PENDING_QUERIES):
        p = run_gh("pr", "checks", str(a.pr), "--repo", a.repo, "--json", "name,bucket")
        if not p.stdout.strip():
            if "no checks reported" in p.stderr:
                return
            raise GateError("gh pr checks: %s" % (p.stderr.strip().splitlines() or ["exit %d" % p.returncode])[-1])
        checks = json.loads(p.stdout)
        failed = [c["name"] for c in checks if c["bucket"] in ("fail", "cancel")]
        if failed:
            raise Hold(5, "check %s failed" % ", ".join(failed))
        pending = [c["name"] for c in checks if c["bucket"] == "pending"]
        if not pending:
            return
        if n == PENDING_QUERIES - 1 or over_budget():
            raise Hold(5, "check %s still pending after %d queries" % (", ".join(pending), n + 1))
        time.sleep(POLL)


def walk(pr) -> None:
    body, head7 = pr["body"], pr["headRefOid"][:7]
    result = section(body, "Smoke result")
    if result is None or not result.strip():
        raise Hold(7, "the PR has cases and no ## Smoke result")
    first = next(l for l in result.splitlines() if l.strip())
    if re.search(r"^\W*(smoke )?not run(nable)?\b", result, re.M) or re.search(r"\bnot run(nable)?\b", first):
        raise Hold(7, "the walk did not run: %s" % first.strip()[:100])
    m = re.search(r"\bwalk (\d+) at ([0-9a-f]{7})\b", first)
    if not m:
        raise Hold(7, "## Smoke result has no walk line")
    if m.group(2) != head7:
        raise Hold(7, "the last walk is at %s, not the head %s" % (m.group(2), head7))
    if "unaudited" in first:
        raise Hold(7, "the walk is unaudited: %s" % first.split("unaudited", 1)[1].strip(" :")[:80])
    rows = re.findall(r"^[ \t]*smoke[ \t]+(walk \d+ .*)$", body, re.M)
    if not rows:
        raise Hold(7, "the evidence block has no smoke walk row")
    audit = re.search(r"\baudit (\S+)", rows[-1])
    if not audit or audit.group(1) != "0":
        raise Hold(7, "the smoke row's audit is %s" % (audit.group(1) if audit else "missing"))
    checked = {}
    for line in result.splitlines():
        m = re.match(r"^[ \t]*(?:(?:[-*+]|\d+[.)])[ \t]+)?(valid|unchecked|refuted|polish|fixed):[ \t]*(\S*)", line)
        if not m:
            continue
        if m.group(1) in ("valid", "unchecked"):
            raise Hold(7, "a defect is not cleared: %s" % line.strip()[:80])
        if m.group(1) == "fixed" and "unconfirmed" in line:
            raise Hold(7, "a fix is not confirmed by a walk: %s" % line.strip()[:80])
        checked.setdefault(m.group(2).rstrip(",:"), set()).add(m.group(1))
    devices = re.search(r" · devices ([^·]+?)[ \t]*(?: · |$)", first)
    if not devices:
        raise Hold(7, "the walk line names no devices")
    tokens = [t for t in re.split(r"[,\s]+", devices.group(1)) if t]
    for line in result.splitlines():
        r = re.match(r"^\s*(?:[-*+]\s+)?\|?\s*([DG])(\d+)\s*\|", line)
        if not r:
            continue
        rid = r.group(1) + r.group(2)
        if r.group(1) == "D":
            if re.search(r"\bblocking\b", line):
                raise Hold(7, "%s was called blocking by the walk" % rid)
            # A defect passes only as polish, or with a refuted: or polish: line; anything else holds.
            if not re.search(r"\|\s*polish\s*\|", line) and not checked.get(rid, set()) & {"refuted", "polish"}:
                raise Hold(7, "%s has no check line that clears it" % rid)
        if r.group(1) == "G":
            ac = re.search(r"\bAC-\d+\b", line)
            if ac:
                raise Hold(7, "%s is a gap on %s" % (rid, ac.group(0)))
            for t in tokens:
                if re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(t), line, re.I):
                    raise Hold(7, "%s is a gap on the walked device %s" % (rid, t))


def ui_test(profiles: list[Profile], names: list[str], why: str) -> None:
    for prof in profiles:
        if prof.ui is None:
            raise Hold(9, "%s, and the profile has no UI paths row" % why)
    for p in names:
        if any(matches(prof.ui, p) for prof in profiles):
            raise Hold(9, "%s, but the diff touches the UI path %s" % (why, p))


def screens(a, pr, profiles: list[Profile], names: list[str]) -> None:
    body = pr["body"]
    listed = section(body, "Screens")
    none = re.search(r"^Screens: none — +\S", listed if listed is not None else body, re.M)
    if none:
        ui_test(profiles, names, "Screens: none")
        return
    if listed is None:
        raise Hold(8, "the PR has cases and no ## Screens list")
    rows = re.findall(r"^- (SCREEN-\d+) · .+ · ([^·\n]+)$", listed, re.M)
    for line in listed.splitlines():
        if re.match(r"^\s*[-*+]?\s*SCREEN-\d+", line) and not re.match(r"^- SCREEN-\d+ · .+ · [^·]+$", line):
            raise Hold(8, "a ## Screens line is not a row: %s" % line.strip()[:80])
    if not rows:
        raise Hold(8, "the ## Screens list is empty")
    out = gh("api", "repos/%s/issues/%d/comments" % (a.repo, a.pr), "--paginate", "--jq", ".[] | {id: .id, body: .body}")
    comments = parse_comments(out)
    marked = [c for c in comments if str(c.get("body", "")).startswith("<!-- adw-screens head=")]
    if not marked:
        raise Hold(8, "no screens comment on the PR")
    text = marked[-1]["body"]
    m = re.match(r"<!-- adw-screens head=([0-9a-f]{40})", text)
    if not m or m.group(1) != pr["headRefOid"]:
        raise Hold(8, "the screens comment is for %s, not the head %s" % ((m.group(1)[:7] if m else "no head"), pr["headRefOid"][:7]))
    for sid, devs in rows:
        for d in [x.strip().lower() for x in devs.split(",") if x.strip()]:
            if "![%s · %s](" % (sid, d) not in text:
                raise Hold(8, "no image for %s · %s" % (sid, d))


def parse_comments(out: str) -> list[dict]:
    out = out.strip()
    if not out:
        return []
    try:
        data = json.loads(out)
        return data if isinstance(data, list) else [data]
    except ValueError:
        return [json.loads(line) for line in out.splitlines() if line.strip()]


def check(a) -> None:
    pr = json.loads(gh("pr", "view", str(a.pr), "--repo", a.repo, "--json",
                       "number,baseRefName,headRefOid,labels,body,mergeable,mergeStateStatus"))
    with open(a.profile, encoding="utf-8") as f:
        local = Profile(f.read())
    specs = {p: contents(a.repo, p, pr["headRefOid"]) for p in a.spec_path}
    basep = base_profile(a, pr)
    flag(pr, local, basep, specs)
    profiles = [local, basep]
    base(pr, basep, specs)
    verified(pr)
    signoff(pr)
    files = read_diff(a)
    names = sorted({p for f in files for p in f["paths"]})
    paths(profiles, files)
    github(a, pr)
    smoke = section(pr["body"], "Smoke", stop_marker="<!-- /smoke -->")
    if smoke is not None and re.search(r"^### AC-\d+", smoke, re.M):
        walk(pr)
        screens(a, pr, profiles, names)
    elif re.search(r"^Smoke: none — +\S", pr["body"], re.M):
        ui_test(profiles, names, "Smoke: none")
    else:
        raise Hold(9, "the body has neither ## Smoke cases nor a Smoke: none line")


FLAGS = {"squash": "--squash", "merge": "--merge", "rebase": "--rebase"}


def merge_flag(a, prof: Profile) -> str:
    word = a.flag or prof.convention
    if word not in FLAGS:
        raise GateError("no merge convention: pass --flag, or give repo-profile §3 a merge convention row")
    return FLAGS[word]


def view(a, fields: str) -> dict:
    return json.loads(gh("pr", "view", str(a.pr), "--repo", a.repo, "--json", fields))


def needs(a, *names: str) -> None:
    missing = ["--" + n.replace("_", "-") for n in names if not getattr(a, n)]
    if missing:
        raise GateError("merge%s needs %s" % (" --sub" if a.sub else " --owner" if a.owner else "", " ".join(missing)))


def merge(a) -> int:
    if not re.fullmatch(r"[0-9a-f]{40}", a.head or ""):
        raise GateError("--head must be a full 40-character sha")
    if a.sub:
        needs(a, "slug")
        pr = view(a, "baseRefName,headRefOid,body")
        if pr["baseRefName"] != "adw/%s" % a.slug:
            raise Hold(2, "the sub-PR's base %s is not adw/%s" % (pr["baseRefName"], a.slug))
        if pr["headRefOid"] != a.head:
            raise Hold(3, "head moved: %s is not %s" % (pr["headRefOid"][:7], a.head[:7]))
        m = re.search(r"^[ \t]*verified[ \t]+([0-9a-f]{40})\b", pr["body"], re.M)
        if not m:
            raise Hold(3, "the evidence block has no verified row")
        if m.group(1) != a.head:
            raise Hold(3, "verified %s is not the head %s" % (m.group(1)[:7], a.head[:7]))
        return do_merge(a, "--squash")
    needs(a, "profile") if a.owner else needs(a, "profile", "spec_path", "base")
    with open(a.profile, encoding="utf-8") as f:
        local = Profile(f.read())
    if not a.owner:
        check(a)
    pr = view(a, "baseRefName,headRefOid,labels")
    basep = base_profile(a, pr)
    production = {prof.production for prof in (local, basep) if prof is not None and prof.production}
    if not production:
        raise Hold(2, "no copy of the profile names the production branch, so the base cannot be cleared")
    if pr["baseRefName"] in production:
        raise Hold(2, "the PR's base %s is the production branch" % pr["baseRefName"])
    if a.base and pr["baseRefName"] != a.base:
        raise Hold(2, "base changed: %s is not %s" % (pr["baseRefName"], a.base))
    if pr["headRefOid"] != a.head:
        raise Hold(3, "head moved: %s is not %s" % (pr["headRefOid"][:7], a.head[:7]))
    if not a.owner and "adw:hold" in {l["name"] for l in pr["labels"]}:
        raise Hold(1, "the PR has the adw:hold label")
    return do_merge(a, merge_flag(a, local))


def do_merge(a, flag: str) -> int:
    cmd = ["pr", "merge", str(a.pr), "--repo", a.repo, flag, "--match-head-commit", a.head]
    if a.owner and a.delete_branch:
        cmd.append("--delete-branch")
    err = ""
    for _ in range(2):
        p = run_gh(*cmd)
        err = (p.stderr.strip().splitlines() or ["exit %d" % p.returncode])[-1] if p.returncode else ""
        state = read_back(a)
        if state is None:
            # The merge may have landed: never call it a gate error, and never merge again blind.
            print("hold call — the merge call %s, and the PR could not be read back: check it before anything else"
                  % ("exited 0" if not err else "failed (%s)" % err))
            return 1
        if state.get("state") == "MERGED":
            print("merged %s" % ((state.get("mergeCommit") or {}).get("oid") or "unknown")[:7])
            return 0
        if not err:
            err = "the PR is %s after the merge call" % state.get("state")
            break
    print("hold call — %s" % err)
    return 1


def read_back(a) -> dict | None:
    """The PR's state after a merge call, or None when gh cannot read it three times."""
    for n in range(3):
        try:
            return view(a, "state,mergeCommit")
        except (GateError, ValueError):
            if n < 2:
                time.sleep(min(POLL, 10))
    return None


def git(checkout: str, *args: str) -> str:
    p = subprocess.run(["git", "-C", checkout, *args], capture_output=True, text=True)
    if p.returncode != 0:
        raise GateError("git %s: %s" % (args[0], (p.stderr.strip().splitlines() or ["exit %d" % p.returncode])[-1]))
    return p.stdout


def changed(checkout: str, a: str, b: str) -> set[str]:
    return {n for n in git(checkout, "diff", "--no-renames", "--name-only", a, b).splitlines() if n}


def trial(a) -> int:
    co = a.checkout
    git(co, "fetch", "-q", "origin")
    if subprocess.run(["git", "-C", co, "cat-file", "-e", a.head + "^{commit}"], capture_output=True).returncode != 0:
        git(co, "fetch", "-q", "origin", a.head)
    tip = git(co, "rev-parse", "origin/" + a.base).strip()
    fork = git(co, "merge-base", tip, a.head).strip()
    if tip == fork:
        print("base unmoved")
        return 0
    overlap = sorted(changed(co, fork, tip) & changed(co, fork, a.head))
    if overlap:
        print("hold 6 overlap: %s" % ", ".join(overlap))
        return 1
    tree = os.path.join(co, ".claude", "worktrees", "adw-trial-%s-pr%d" % (a.slug, a.pr))
    if os.path.exists(tree):
        # a run that died before Phase 5 left it: remove it when clean, never with --force
        if git(tree, "status", "--porcelain").strip():
            raise GateError("%s exists from an earlier trial with changes past the merge; /cleanup it" % tree)
        git(co, "worktree", "remove", tree)
    git(co, "worktree", "add", "-q", "--detach", tree, a.head)
    m = subprocess.run(["git", "-C", tree, "merge", "--no-edit", "-q", tip], capture_output=True, text=True)
    if m.returncode != 0:
        files = sorted(n for n in git(tree, "diff", "--name-only", "--diff-filter=U").splitlines() if n)
        subprocess.run(["git", "-C", tree, "merge", "--abort"], capture_output=True)
        git(co, "worktree", "remove", tree)
        print("hold 6 conflict: %s" % (", ".join(files) or (m.stdout + m.stderr).strip().splitlines()[-1]))
        return 1
    print("tree %s base %s" % (tree, tip))
    return 0


def discard(a) -> int:
    status = git(a.tree, "status", "--porcelain")
    if status.strip():
        print("kept %s: it has changes past the merge (%s)" % (a.tree, ", ".join(l[3:] for l in status.splitlines()[:3])))
        return 1
    git(a.checkout, "worktree", "remove", a.tree)
    print("discarded %s" % a.tree)
    return 0


class Parser(argparse.ArgumentParser):
    def error(self, message):
        print("hold 0 gate error: %s" % message)
        sys.exit(2)


def main(argv: list[str]) -> int:
    p = Parser(prog="adw-merge-gate.py")
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=Parser)
    c = sub.add_parser("check")
    c.add_argument("--repo", required=True)
    c.add_argument("--pr", type=int, required=True)
    c.add_argument("--profile", required=True)
    c.add_argument("--spec-path", action="append", required=True)
    t = sub.add_parser("trial")
    t.add_argument("--checkout", required=True)
    t.add_argument("--pr", type=int, required=True)
    t.add_argument("--slug", required=True)
    t.add_argument("--base", required=True)
    t.add_argument("--head", required=True)
    d = sub.add_parser("discard")
    d.add_argument("--checkout", required=True)
    d.add_argument("--tree", required=True)
    m = sub.add_parser("merge")
    mode = m.add_mutually_exclusive_group()
    mode.add_argument("--sub", action="store_true")
    mode.add_argument("--owner", action="store_true")
    m.add_argument("--repo", required=True)
    m.add_argument("--pr", type=int, required=True)
    m.add_argument("--head", required=True)
    m.add_argument("--base")
    m.add_argument("--slug")
    m.add_argument("--profile")
    m.add_argument("--spec-path", action="append")
    m.add_argument("--flag", choices=sorted(FLAGS))
    m.add_argument("--delete-branch", action="store_true")
    a = p.parse_args(argv)
    try:
        if a.cmd == "merge":
            return merge(a)
        if a.cmd == "trial":
            return trial(a)
        if a.cmd == "discard":
            return discard(a)
        check(a)
    except Hold as h:
        print("hold %d %s" % (h.n, h.reason))
        return 1
    except (GateError, OSError, ValueError, KeyError) as e:
        print("hold 0 gate error: %s" % e)
        return 2
    print("pass")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
