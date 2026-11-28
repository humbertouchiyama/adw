#!/usr/bin/env python3
"""adw-guard: a PreToolUse hook that enforces four Never rules of the ADW contract with code.

A rule pasted into every brief is still a prompt, and the contract's own counts show prompts broke
them (11 `git stash` commands in 7 sessions, review-core §11). A hook binds the main session and
every subagent alike. The consuming repo registers it in `.claude/settings.json` (README,
"Installing it in a repo"), with the matcher `Bash|EnterWorktree`.

It denies:
- `git stash` in any form (`git -C <path> stash`, `/usr/bin/git stash`, inside `$( )` or `bash -c`):
  the stash is shared by every worktree of a repo (adw-build "Never").
- `gh pr merge`, and `gh api` on a pull request's merge: a model merges through
  `adw-merge-gate.py merge`, which merges only after its own checks (adw-build §3.7). The owner merges
  by hand with `! gh pr merge …`, which no hook sees.
- `herdr` commands that type into a pane (`agent prompt`, `agent send-keys`, `pane send-text`,
  `pane send-keys`, `pane run`): a line for a child goes through `adw-dispatch.py prompt`, which
  refuses an answer to the child's approval surface (adw-dispatch §7).
- EnterWorktree from a subagent: the orchestrator gives each subagent its worktree (adw-build "Never").

It reads the command the way an agent writes it. It is a guard against a slip, not a sandbox. A
command it cannot split into words (an unclosed quote) is checked with a plain pattern instead.
Input is the hook JSON on stdin. A deny is a JSON decision on stdout, exit 0. Anything else allows.
"""
import json
import os
import re
import sys

STASH = ("adw-guard: `git stash` is denied. The stash is shared by every worktree of this repo, so it "
         "can take or drop another session's work (adw-build \"Never\"). Commit on your own branch instead.")
MERGE = ("adw-guard: a typed `gh pr merge` is denied. Merge with the contract cache's "
         "`scripts/adw-merge-gate.py merge` (adw-build §3.7: the gate; `--sub` for a sub-PR; `--owner` "
         "after the owner said merge), which merges only after its own checks. Otherwise print "
         "`! gh pr merge …` for the owner to run.")
HERDR = ("adw-guard: typing into a pane with herdr is denied. Send the owner's line with "
         "`python3 \"$DISPATCH\" prompt <pane> \"<line>\"` (adw-dispatch §7), which refuses a line "
         "that could answer a child's approval surface.")
WORKTREE = ("adw-guard: a subagent does not create its own worktree (adw-build \"Never\"). Work in the "
            "worktree your brief names. If it names none, say so in your result.")

SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
# Wrappers that run the rest of the line as a command, with the options each one takes a value for.
WRAPPERS = {"command": set(), "builtin": set(), "exec": set(), "nohup": set(), "time": set(),
            "env": {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"},
            "sudo": {"-u", "-g", "-h", "-p", "-C", "-D", "-r", "-t", "-U"},
            "nice": {"-n"}, "timeout": {"-s", "-k", "--signal", "--kill-after"},
            "xargs": {"-I", "-L", "-n", "-P", "-s", "-d", "-E", "-a", "--max-args", "--max-procs",
                      "--delimiter", "--arg-file", "--replace"},
            "rtk": set(), "caffeinate": {"-t", "-w"}}
GIT_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--config-env",
             "--exec-path", "--list-cmds"}
GH_VALUE = {"-R", "--repo", "--hostname"}
HERDR_VALUE = {"--session", "--machine", "--remote"}
HERDR_TYPING = {("agent", "prompt"), ("agent", "send-keys"), ("pane", "send-text"),
                ("pane", "send-keys"), ("pane", "run")}
ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


class Unparsed(Exception):
    pass


def closing(s, i, opener, closer):
    """Index of the `closer` that ends a `$(`…`)` or `` ` ``…`` ` `` opened before i, quotes respected."""
    depth, q = 1, None
    while i < len(s):
        c = s[i]
        if q == "'":
            if c == "'":
                q = None
        elif c == "\\":
            i += 1
        elif q == '"':
            if c == '"':
                q = None
        elif c in "'\"" and opener != "`":
            q = c
        elif opener == "(" and s.startswith("$(", i):
            depth += 1
            i += 1
        elif opener == "(" and c == "(":
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise Unparsed("unclosed %s" % opener)


def lex(s, out, depth=0):
    """Append to `out` the argv of every simple command in s, and of every command substitution."""
    if depth > 6:
        raise Unparsed("too deep")
    argv, word, has_word, i, heredocs = [], [], False, 0, []

    def end_word():
        nonlocal word, has_word
        if has_word:
            argv.append("".join(word))
        word, has_word = [], False

    def end_cmd():
        nonlocal argv
        end_word()
        if argv:
            out.append(argv)
        argv = []

    while i < len(s):
        c = s[i]
        if c == "\\":
            if i + 1 < len(s) and s[i + 1] != "\n":
                word.append(s[i + 1])
                has_word = True
            i += 2
            continue
        if c == "'" or s.startswith("$'", i):
            j = i + (2 if c == "$" else 1)
            k = j
            while k < len(s) and s[k] != "'":
                k += 2 if (c == "$" and s[k] == "\\") else 1
            if k >= len(s):
                raise Unparsed("unclosed '")
            word.append(s[j:k])
            has_word, i = True, k + 1
            continue
        if c == '"':
            k = i + 1
            while k < len(s) and s[k] != '"':
                if s[k] == "\\":
                    k += 1
                elif s.startswith("$(", k):
                    e = closing(s, k + 2, "(", ")")
                    lex(s[k + 2:e], out, depth + 1)
                    k = e
                elif s[k] == "`":
                    e = closing(s, k + 1, "`", "`")
                    lex(s[k + 1:e], out, depth + 1)
                    k = e
                k += 1
            if k >= len(s):
                raise Unparsed('unclosed "')
            word.append(s[i + 1:k])
            has_word, i = True, k + 1
            continue
        if s.startswith("$(", i):
            e = closing(s, i + 2, "(", ")")
            lex(s[i + 2:e], out, depth + 1)
            word.append("$()")
            has_word, i = True, e + 1
            continue
        if c == "`":
            e = closing(s, i + 1, "`", "`")
            lex(s[i + 1:e], out, depth + 1)
            word.append("``")
            has_word, i = True, e + 1
            continue
        if s.startswith("<<", i) and not s.startswith("<<<", i):
            m = re.match(r"<<(-?)[ \t]*(['\"]?)([A-Za-z0-9_.-]+)\2", s[i:])
            if m:
                heredocs.append((m.group(3), m.group(1) == "-"))
                i += m.end()
                continue
        if c == "#" and not has_word:
            while i < len(s) and s[i] != "\n":
                i += 1
            continue
        if c in " \t":
            end_word()
            i += 1
            continue
        if c == "\n":
            end_cmd()
            i += 1
            for tag, tabs in heredocs:  # skip each body: it is data, not commands
                while i < len(s):
                    nl = s.find("\n", i)
                    line = s[i:] if nl < 0 else s[i:nl]
                    i = len(s) if nl < 0 else nl + 1
                    if (line.lstrip("\t") if tabs else line) == tag:
                        break
            heredocs = []
            continue
        if c in ";&|()":
            end_cmd()
            i += 1
            continue
        word.append(c)
        has_word = True
        i += 1
    end_cmd()
    return out


def collect(cmd, found, depth=0):
    """Append to `found` the argv each simple command in cmd finally runs, wrappers removed."""
    for argv in lex(cmd, [], depth):
        inner = unwrap(argv, found, depth)
        if inner:
            found.append(inner)
    return found


def unwrap(argv, found, depth):
    """The command a wrapper line runs: strips `VAR=x`, `env`, `sudo`, `rtk`, `xargs`; opens `bash -c`
    and `eval`, whose commands go to `found` directly."""
    while argv:
        name = os.path.basename(argv[0])
        if ASSIGN.match(argv[0]):
            argv = argv[1:]
        elif name in WRAPPERS:
            rest, takes = argv[1:], WRAPPERS[name]
            if name == "rtk" and rest[:1] == ["proxy"]:
                rest = rest[1:]
            while rest and (rest[0].startswith("-") or (name == "env" and ASSIGN.match(rest[0]))
                            or (name == "timeout" and re.match(r"^\d", rest[0]))):
                rest = rest[2:] if rest[0] in takes else rest[1:]
            argv = rest
        elif name in SHELLS:
            for k, a in enumerate(argv[1:], 1):
                if re.match(r"^-[a-z]*c[a-z]*$", a) and k + 1 < len(argv):
                    collect(argv[k + 1], found, depth + 1)
                    return None
            return argv
        elif name == "eval":
            collect(" ".join(argv[1:]), found, depth + 1)
            return None
        else:
            return argv
    return None


def positional(args, takes_value):
    out, skip = [], False
    for a in args:
        if skip:
            skip = False
        elif a.startswith("-"):
            skip = a in takes_value
        else:
            out.append(a)
    return out


def verdict(argv):
    name = os.path.basename(argv[0])
    if name == "git":
        rest = argv[1:]
        while rest and rest[0].startswith("-"):
            rest = rest[2:] if rest[0] in GIT_VALUE else rest[1:]
        if rest and rest[0] == "stash":
            return STASH
    elif name == "gh":
        pos = positional(argv[1:], GH_VALUE)
        if pos[:2] == ["pr", "merge"]:
            return MERGE
        if pos[:1] == ["api"] and any(re.search(r"pulls/[^/\s]+/merge\b", a) or "mergePullRequest" in a
                                      for a in argv[1:]):
            return MERGE
    elif name == "herdr":
        pos = positional(argv[1:], HERDR_VALUE)
        if tuple(pos[:2]) in HERDR_TYPING:
            return HERDR
    return None


FALLBACK = [
    (re.compile(r"\bgit\b[^;&|\n]*\bstash\b"), STASH),
    (re.compile(r"\bgh\b[^;&|\n]*\bpr\b[^;&|\n]*\bmerge\b"), MERGE),
    (re.compile(r"\bherdr\b[^;&|\n]*\b(?:agent|pane)\b[^;&|\n]*\b(?:prompt|send-keys|send-text|run)\b"), HERDR),
]


def check_command(cmd):
    """The deny reason for a Bash command line, or None."""
    try:
        found = collect(cmd, [])
    except (Unparsed, RecursionError):
        for rx, why in FALLBACK:
            if rx.search(cmd):
                return why
        return None
    for argv in found:
        why = verdict(argv)
        if why:
            return why
    return None


def decide(event):
    tool = event.get("tool_name")
    if tool == "EnterWorktree" and event.get("agent_id"):
        return WORKTREE
    if tool == "Bash":
        cmd = (event.get("tool_input") or {}).get("command")
        if isinstance(cmd, str):
            return check_command(cmd)
    return None


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    why = decide(event) if isinstance(event, dict) else None
    if why:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                 "permissionDecision": "deny",
                                                 "permissionDecisionReason": why}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
