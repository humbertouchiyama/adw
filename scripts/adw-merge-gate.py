#!/usr/bin/env python3
"""adw-merge-gate.py: the auto-merge gate of adw-build §3.7 (design docs/specs/2026-10-30-adw-auto-merge-design.md §4.2).

  python3 adw-merge-gate.py check --repo <owner/repo> --pr <N> --profile <local repo-profile.md>
      --spec-path <repo path> [--spec-path ...]

Every condition is read fresh from GitHub or the profile, never from the run's memory. It prints one line:
`pass` (exit 0), or `hold <n> <reason>` (exit 1) for the first condition that fails, in this order:
1 flag (the specs' `merge: auto`, both profiles' `auto-merge default`, no `adw:hold`), 2 base, 3 verified head,
4 paths (merge-protected, money lines), 5 GitHub (mergeable, checks), 7 the walk, 8 the screenshots,
9 `Smoke: none` / `Screens: none` against the UI paths. Condition 6 is the base trial (`trial`).
A gh call that fails, or a bad flag, prints `hold 0 gate error: <message>` and exits 2: the contract
treats it as a hold. ADW_GATE_POLL_SECONDS (default 30) spaces the re-queries: 5 for an UNKNOWN
mergeable state, 16 (8 min at the default) for a pending check.
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
        self.protected = [glob_re(g) for g in ticks(s3.get("merge-protected paths", ""))]
        ui = s3.get("ui paths")
        self.ui = [glob_re(g) for g in ticks(ui)] if ui is not None else None
        self.production = (ticks(s3.get("production branch", "")) or [None])[0]
        self.default_base = (ticks(s3.get("default base", "")) or [None])[0]
        self.excluded = [glob_re(g) for g in re.findall(r"':!([^']+)'", self.sections.get("2", {}).get("artifact exclusion pathspec", ""))]
        money = self.sections.get("11", {}).get("money", "")
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

def flag(a, pr, local: Profile, specs: dict[str, str | None]) -> None:
    labels = {l["name"] for l in pr["labels"]}
    if "adw:hold" in labels:
        raise Hold(1, "the PR has the adw:hold label")
    values = {}
    for path, text in specs.items():
        if text is None:
            raise Hold(1, "spec %s is not at the head %s" % (path, pr["headRefOid"][:7]))
        m = re.search(r"^merge:[ \t]*(auto|hold)\b", text, re.M)
        if not m:
            raise Hold(1, "spec %s has no merge: line (omitted = hold)" % path)
        values[path] = m.group(1)
    if len(set(values.values())) > 1:
        raise Hold(1, "the specs disagree on merge: (%s)" % ", ".join("%s %s" % (p, v) for p, v in values.items()))
    if "hold" in values.values():
        raise Hold(1, "the spec says merge: hold")
    for where, prof in (("the local profile", local), ("the profile on %s" % pr["baseRefName"], base_profile(a, pr))):
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
    bases = {m.group(1) for t in specs.values() if t for m in [re.search(r"^base:[ \t]*(\S+)", t, re.M)] if m}
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


def paths(a, local: Profile, names: list[str]) -> None:
    for p in names:
        if matches(local.protected, p):
            raise Hold(4, "%s is a merge-protected path" % p)
    d = run_gh("pr", "diff", str(a.pr), "--repo", a.repo)
    if d.returncode != 0:
        raise Hold(4, "the diff cannot be read: %s" % (d.stderr.strip().splitlines() or ["exit %d" % d.returncode])[-1])
    path = None
    for line in d.stdout.splitlines():
        if line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else None
            continue
        if path is None or not line.startswith("+") or matches(local.excluded, path):
            continue
        if local.money_prefix and path.startswith(local.money_prefix):
            raise Hold(4, "%s is under the money path %s" % (path, local.money_prefix))
        if local.money and local.money.search(line[1:]):
            raise Hold(4, "%s adds a money line: %s" % (path, line[1:].strip()[:80]))


def github(a, pr) -> None:
    state = pr.get("mergeable")
    for n in range(UNKNOWN_QUERIES):
        if state == "MERGEABLE":
            break
        if state != "UNKNOWN":
            raise Hold(5, "GitHub says the PR is %s" % state)
        if n == UNKNOWN_QUERIES - 1:
            raise Hold(5, "mergeable is still UNKNOWN after %d queries" % UNKNOWN_QUERIES)
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
        if n < PENDING_QUERIES - 1:
            time.sleep(POLL)
    raise Hold(5, "check %s still pending after %d queries" % (", ".join(pending), PENDING_QUERIES))


def walk(pr) -> None:
    body, head7 = pr["body"], pr["headRefOid"][:7]
    result = section(body, "Smoke result")
    if result is None or not result.strip():
        raise Hold(7, "the PR has cases and no ## Smoke result")
    first = next(l for l in result.splitlines() if l.strip())
    if re.search(r"\bnot run(nable)?\b", result):
        raise Hold(7, "the walk did not run: %s" % first.strip()[:100])
    m = re.search(r"\bwalk (\d+) at ([0-9a-f]{7})\b", first)
    if not m:
        raise Hold(7, "## Smoke result has no walk line")
    if m.group(2) != head7:
        raise Hold(7, "the last walk is at %s, not the head %s" % (m.group(2), head7))
    if "unaudited" in first:
        raise Hold(7, "the walk is unaudited: %s" % first.split("unaudited", 1)[1].strip(" :")[:80])
    row = re.search(r"^[ \t]*smoke[ \t]+(.*)$", body, re.M)
    audit = re.search(r"\baudit (\S+)", row.group(1)) if row else None
    if audit and audit.group(1) != "0":
        raise Hold(7, "the smoke row's audit is %s" % audit.group(1))
    for line in result.splitlines():
        if re.match(r"^(valid|unchecked):", line):
            raise Hold(7, "a defect is not cleared: %s" % line.strip()[:80])
        if re.match(r"^fixed:.*unconfirmed", line):
            raise Hold(7, "a fix is not confirmed by a walk: %s" % line.strip()[:80])
    devices = re.search(r"\bdevices ([\w,.-]+)", first)
    tokens = [t for t in devices.group(1).split(",") if t] if devices else []
    for line in result.splitlines():
        r = re.match(r"^\|\s*([DG])(\d+)\s*\|", line)
        if not r:
            continue
        rid = r.group(1) + r.group(2)
        if r.group(1) == "D" and re.search(r"\bblocking\b", line):
            raise Hold(7, "%s was called blocking by the walk" % rid)
        if r.group(1) == "G":
            ac = re.search(r"\bAC-\d+\b", line)
            if ac:
                raise Hold(7, "%s is a gap on %s" % (rid, ac.group(0)))
            for t in tokens:
                if re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(t), line, re.I):
                    raise Hold(7, "%s is a gap on the walked device %s" % (rid, t))


def ui_test(local: Profile, names: list[str], why: str) -> None:
    if local.ui is None:
        raise Hold(9, "%s, and the profile has no UI paths row" % why)
    for p in names:
        if matches(local.ui, p):
            raise Hold(9, "%s, but the diff touches the UI path %s" % (why, p))


def screens(a, pr, local: Profile, names: list[str]) -> None:
    body = pr["body"]
    listed = section(body, "Screens")
    none = re.search(r"^Screens: none — +\S", listed if listed is not None else body, re.M)
    if none:
        ui_test(local, names, "Screens: none")
        return
    if listed is None:
        raise Hold(8, "the PR has cases and no ## Screens list")
    rows = re.findall(r"^- (SCREEN-\d+) · .+ · ([^·\n]+)$", listed, re.M)
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
    flag(a, pr, local, specs)
    base(pr, local, specs)
    verified(pr)
    names = [n for n in gh("pr", "diff", str(a.pr), "--repo", a.repo, "--name-only").splitlines() if n.strip()]
    paths(a, local, names)
    github(a, pr)
    smoke = section(pr["body"], "Smoke", stop_marker="<!-- /smoke -->")
    if smoke is not None and re.search(r"^### AC-\d+", smoke, re.M):
        walk(pr)
        screens(a, pr, local, names)
    elif re.search(r"^Smoke: none — +\S", pr["body"], re.M):
        ui_test(local, names, "Smoke: none")
    else:
        raise Hold(9, "the body has neither ## Smoke cases nor a Smoke: none line")


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
    a = p.parse_args(argv)
    try:
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
