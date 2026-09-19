#!/usr/bin/env python3
"""Resolve every cross-file citation in the ADW contract against real headings.

Usage: check-anchors.py <base-ref> <head-ref>   (run from inside the adw repo)

Compares <head-ref> with its merge-base against <base-ref>, so an anchor the base
branch fixed after the PR branched is not charged to the PR. Prints citations that do
not resolve at <head-ref>, split into NEW (the citing line is not at the merge-base)
and OLD (it is). A line the PR rewords counts as new. An anchor in OPTIONAL prints as
OPT and is never NEW. Exit 1 if any NEW, 2 if a ref cannot be read.
A citation is `<file> §N`, `<file> §N.M` or `<file> Phase N[.M][a]`, with or without
`.md` and backticks. It may wrap across lines. `repo-profile §N` resolves against
docs/repo-profile-EXAMPLE.md. Bare `§N` (self-reference) is not checked.
Scans README.md and every tracked .md under commands/, install/, docs/ and .claude/skills/.
Citations inside code fences count: an agent copies fenced text verbatim.
"""
import re, subprocess, sys
from collections import Counter

FILES = {
    "adw-core": "commands/adw-core.md", "adw-build": "commands/adw-build.md",
    "adw-init": "commands/adw-init.md", "pr-ready": "commands/pr-ready.md",
    "review-core": "commands/review-core.md", "code-review": "commands/code-review.md",
    "cleanup": "commands/cleanup.md", "design": "docs/00-design.md",
    "repo-profile": "docs/repo-profile-EXAMPLE.md",
}
SCAN_DIRS = ("commands/", "install/", "docs/", ".claude/skills/")
# Anchors the contract cites and documents a fallback for when a profile lacks them
# (code-review.md: "Where a repo carries no `§19`, derive"). Printed as OPT, never NEW.
OPTIONAL = {("repo-profile", "§19")}
# A heading, or a bold paragraph lead that names its own anchor, blockquoted or not
# (`**§4.2 — Gate-file tripwire.**`, `> **Phase 0 reads ...**`). A bold lead that
# starts with a bare number is prose (`**61.4% of ...**`), not an anchor.
HEAD_RE = re.compile(
    r"^(?:#{1,6}\s+(?:Phase\s+|§\s?)?|(?:>\s*)?\*\*(?:Phase\s+|§\s?))"
    r"(\d+(?:\.\d+)*[a-z]?)(?=[\s.—:-]|$)"
)
CITE_RE = re.compile(
    r"`?\b(" + "|".join(FILES) + r")(?:\.md)?`?[\s>]+(?:(§)\s?|Phase\s+)(\d+(?:\.\d+)*[a-z]?)"
)


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def show(ref, path):
    return git("show", f"{ref}:{path}")


def scan_paths(ref):
    names = git("ls-tree", "-r", "--name-only", ref) or ""
    return [n for n in names.splitlines()
            if n.endswith(".md") and (n == "README.md" or n.startswith(SCAN_DIRS))]


def anchors(text):
    out, fence = set(), False
    for line in text.splitlines():
        if line.startswith("```"):
            fence = not fence
        m = None if fence else HEAD_RE.match(line)
        if m:
            out.add(m.group(1))
    return out


def broken(ref):
    """{(file, form): [(site label, (path, citing line text))]} for cites that do not resolve."""
    heads = {k: anchors(show(ref, p) or "") for k, p in FILES.items()}
    bad = {}
    for path in scan_paths(ref):
        text = show(ref, path) or ""
        lines = text.split("\n")
        for m in CITE_RE.finditer(text):
            key, num = m.group(1), m.group(3)
            form = f"§{num}" if m.group(2) else f"Phase {num}"
            if FILES.get(key) == path:
                continue  # self-citation by name: headings may be phrased differently
            if num not in heads[key]:
                n = text.count("\n", 0, m.start()) + 1
                bad.setdefault((key, form), []).append((f"{path}:{n}", (path, lines[n - 1].strip())))
    return bad


def fail(msg):
    print(msg, file=sys.stderr)
    sys.exit(2)


def main():
    if len(sys.argv) != 3:
        fail(__doc__)
    base_ref, head_ref = sys.argv[1:]
    for ref in (base_ref, head_ref):
        if git("rev-parse", "--verify", "-q", f"{ref}^{{commit}}") is None:
            fail(f"cannot read ref {ref}")
    if not scan_paths(head_ref):
        fail(f"no contract files at {head_ref}")
    merge_base = git("merge-base", base_ref, head_ref)
    if merge_base is None:
        fail(f"no merge-base for {base_ref} and {head_ref}")
    base, head = broken(merge_base.strip()), broken(head_ref)
    # NEW when the PR adds a citing line, even to an anchor that was already broken.
    new, old = {}, {}
    for key, sites in head.items():
        seen = Counter(ident for _, ident in base.get(key, []))
        for label, ident in sites:
            if seen[ident] > 0:
                seen[ident] -= 1
                old.setdefault(key, []).append(label)
            else:
                new.setdefault(key, []).append(label)
    opt = {k: new.pop(k, []) + old.pop(k, []) for k in OPTIONAL if k in head}
    for label, group in (("NEW", new), ("OLD", old), ("OPT", opt)):
        for (key, num), where in sorted(group.items()):
            print(f"{label}  {key} {num} does not resolve  <- {', '.join(where[:5])}"
                  + (f" (+{len(where) - 5})" if len(where) > 5 else ""))
    if not head:
        print("all citations resolve")
    sys.exit(1 if new else 0)


if __name__ == "__main__":
    main()
