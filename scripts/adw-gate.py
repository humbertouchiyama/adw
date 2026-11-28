#!/usr/bin/env python3
"""adw-gate.py: the skip test of adw-init Phase 2, computed by a script instead of judged by the run.

  python3 adw-gate.py skip --profile <local repo-profile.md> --surface <file> --decide <file>
      --questions "<Q1 Q2 …>" --base <the intent's base>

`--surface` is the approval surface as it would print, every line above the verb menu (adw-core §7).
`--decide` is the decide pass's reply, verbatim. `--questions` lists triage's question ids, or is
`none` (or empty) when triage asked none. The gate is the only human gate of a run, so every input
fails closed. It prints one line, for the first condition that fails, in adw-init's order:

  skip                 (exit 0) all four hold: the gate is skipped
  wait 1 <reason>      (exit 1) a question is `ask`: a line says so, or no `decided` line names its id,
                       or the surface's `needs you` line is not `none`
  wait 2 <reason>      (exit 1) a blocking ⚠ line prints, or the always-printed coverage line is missing
  wait 3 <reason>      (exit 1) the surface prints a `base` line, or --base is not repo-profile §3's
                       default base
  wait 4 <reason>      (exit 1) the surface prints an `extends` line (extend mode keeps the gate)
  wait 0 error: <msg>  (exit 2) a file cannot be read, a flag is bad, or the profile has no default base

Lines inside a fenced block (a D0 draft spec on the surface) are not surface lines.
"""
from __future__ import annotations

import argparse
import re
import sys


class Wait(Exception):
    def __init__(self, n: int, reason: str):
        super().__init__(reason)
        self.n, self.reason = n, reason


class GateError(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        print("wait 0 error: %s" % message)
        sys.exit(2)


def read(path: str) -> str:
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError as e:
        raise GateError("cannot read %s: %s" % (path, e.strerror or e))


def default_base(profile: str) -> str:
    sec = ""
    for line in profile.splitlines():
        m = re.match(r"^## §(\d+)\b", line)
        if m:
            sec = m.group(1)
            continue
        if sec == "3" and line.lstrip().startswith("|"):
            cells = re.split(r"(?<!\\)\|", line.strip())
            if len(cells) >= 4 and cells[1].replace("**", "").replace("`", "").strip().lower() == "default base":
                ticks = re.findall(r"`([^`]+)`", cells[2])
                if ticks:
                    return ticks[0].strip()
    raise GateError("repo-profile §3 has no default base row with a branch in backticks")


def surface_lines(text: str) -> list[str]:
    out, fenced = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            out.append(line.rstrip())
    return out


def questions(arg: str) -> list[str]:
    ids = [q for q in re.split(r"[\s,]+", arg.strip()) if q]
    if ids in ([], ["none"]):
        return []
    bad = [q for q in ids if not re.fullmatch(r"Q\d+", q)]
    if bad:
        raise GateError("--questions takes ids like Q1 Q2, or none: %s" % " ".join(bad))
    return ids


def decided(reply: str) -> tuple[set[str], set[str]]:
    """The ids the reply settles, and the ids it sends to the owner. Anything else is unparseable."""
    done, ask = set(), set()
    for line in reply.splitlines():
        m = re.match(r"^\W*(Q\d+)\W*\|\s*(decided:\s*\S.*|ask)\s*$", line.strip().strip("`").strip())
        if not m:
            continue
        (ask if m.group(2) == "ask" else done).add(m.group(1))
    return done - ask, ask


def skip(a) -> None:
    ids = questions(a.questions)
    lines = surface_lines(read(a.surface))
    reply = read(a.decide)
    base = default_base(read(a.profile))
    if not lines:
        raise GateError("the surface file is empty")

    done, ask = decided(reply)
    asked = [q for q in ids if q in ask]
    if asked:
        raise Wait(1, "%s is ask" % ", ".join(asked))
    open_ = [q for q in ids if q not in done]
    if open_:
        raise Wait(1, "no decided line for %s, so it is ask" % ", ".join(open_))
    needs = [l for l in lines if l.startswith("needs you")]
    if not needs:
        raise Wait(1, "the surface has no needs you line")
    if not re.match(r"^needs you\s+none\b", needs[0]):
        raise Wait(1, "the surface prints %r" % needs[0][:60])

    coverage = [l for l in lines if l.startswith("⚠ spec criteria covered by no unit:")]
    if not coverage:
        raise Wait(2, "the surface has no ⚠ spec criteria line, which always prints")
    for l in coverage:
        rest = l.split(":", 1)[1].split("←")[0].strip()
        if rest != "none":
            raise Wait(2, "⚠ spec criteria covered by no unit: %s" % rest[:60])
    for l in lines:
        if l.startswith("⚠ orchestrator on "):
            raise Wait(2, l[:80])
        if l.startswith("⚠ no trustworthy gate sees "):
            raise Wait(2, l[:80])

    based = [l for l in lines if re.match(r"^base\s", l)]
    if based:
        raise Wait(3, "the surface prints %r" % based[0][:60])
    if a.base != base:
        raise Wait(3, "the intent's base %s is not the default base %s" % (a.base, base))

    extends = [l for l in lines if re.match(r"^extends\s", l)]
    if extends:
        raise Wait(4, "the surface prints %r" % extends[0][:60])


def main(argv: list[str]) -> int:
    p = Parser(prog="adw-gate.py")
    sub = p.add_subparsers(dest="cmd", required=True, parser_class=Parser)
    s = sub.add_parser("skip")
    s.add_argument("--profile", required=True)
    s.add_argument("--surface", required=True)
    s.add_argument("--decide", required=True)
    s.add_argument("--questions", required=True)
    s.add_argument("--base", required=True)
    a = p.parse_args(argv)
    try:
        skip(a)
    except Wait as w:
        print("wait %d %s" % (w.n, w.reason))
        return 1
    except GateError as e:
        print("wait 0 error: %s" % e)
        return 2
    print("skip")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
