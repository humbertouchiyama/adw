#!/usr/bin/env python3
"""Resolve cross-file citations in the ADW contract against real headings.

Usage: check-anchors.py <base-ref> <head-ref>   (run from anywhere inside the adw repo)
Tests: python3 -B test_check_anchors.py         (next to this file)

Compares <head-ref> with its merge-base against <base-ref>, so an anchor the base
branch fixed after the PR branched is not charged to the PR. Prints citations that do
not resolve at <head-ref>, split into NEW (the citing line is not at the merge-base)
and OLD (it is). A line the PR rewords counts as new. Every citing site is printed.
Old sites of an anchor in OPTIONAL print as OPT; a new site of it is still NEW.
Exit 1 if any NEW. Exit 2 if the check could not run: unreadable ref, no contract
files, no merge-base, bad usage.

Forms it reads: `<file> §N`, `<file> §N.M`, `<file> §N/§M`, `<file> Phase N[.M][a]`,
with or without `.md` and backticks, wrapped across lines or blockquote prefixes.
<file> is a commands/*.md name, `design` (docs/00-design.md) or `repo-profile`
(docs/repo-profile-EXAMPLE.md, the profile the anchors are checked against).
Not read: comma lists (`§3, §8`), bare numbers (`code-review 4b`), bare `§N`, and a
citation of a file by its own name. A bold lead that opens with `§N` or `Phase N`
counts as an anchor even when it is a sentence.
Scans README.md and every tracked .md under commands/, install/, docs/ and .claude/skills/.
Citations inside code fences count: an agent copies fenced text verbatim.
"""
import re, subprocess, sys
from collections import Counter

DOCS = {"design": "docs/00-design.md", "repo-profile": "docs/repo-profile-EXAMPLE.md"}
SCAN_DIRS = ("commands/", "install/", "docs/", ".claude/skills/")
# Anchors the contract cites and documents a fallback for when a profile lacks them
# (code-review.md: "Where a repo carries no `§19`, derive"). Old sites print as OPT.
OPTIONAL = {("repo-profile", "§19")}
NUM = r"\d+(?:\.\d+)*[a-z]?"
# A heading, or a bold paragraph lead that names its own anchor, blockquoted or not
# (`**§4.2 — Gate-file tripwire.**`, `> **Phase 0 reads ...**`). A bold lead that
# starts with a bare number is prose (`**61.4% of ...**`), not an anchor.
HEAD_RE = re.compile(
    r"^(?:#{1,6}\s+(?:Phase\s+|§\s?)?|(?:>\s*)?\*\*(?:Phase\s+|§\s?))"
    r"(" + NUM + r")(?=[\s.—:-]|$)"
)
TAIL_RE = re.compile(r"/§\s?(" + NUM + ")")


def git(*args):
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def show(ref, path):
    return git("show", f"{ref}:{path}")


def ls(ref, *paths):
    return (git("ls-tree", "-r", "--name-only", "--full-tree", ref, *paths) or "").splitlines()


def files(ref):
    """{name: path} for every file a citation may name, at <ref>."""
    out = dict(DOCS)
    for p in ls(ref, "--", "commands/"):
        if p.endswith(".md"):
            out[p[len("commands/"):-3]] = p
    return out


def scan_paths(ref):
    return [n for n in ls(ref) if n.endswith(".md") and (n == "README.md" or n.startswith(SCAN_DIRS))]


def cite_re(names):
    alt = "|".join(sorted(map(re.escape, names), key=len, reverse=True))
    return re.compile(r"`?\b(" + alt + r")(?:\.md)?`?[\s>]+(?:(§)\s?|Phase\s+)(" + NUM + ")")


def anchors(text):
    out, fence = set(), False
    for line in text.splitlines():
        if line.startswith("```"):
            fence = not fence
        m = None if fence else HEAD_RE.match(line)
        if m:
            out.add(m.group(1))
    return out


def cites(text, cre):
    """Yield (offset, file name, '§' or 'Phase', number) for every citation in text."""
    for m in cre.finditer(text):
        form = "§" if m.group(2) else "Phase"
        yield m.start(), m.group(1), form, m.group(3)
        if form == "§":
            t = TAIL_RE.match(text, m.end())
            while t:
                yield m.start(), m.group(1), form, t.group(1)
                t = TAIL_RE.match(text, t.end())


def broken(ref, names):
    """{(file, form+number): [(site label, (path, citing line text))]} for cites that do not resolve.

    names: every file name a citation may use, from the base and the head, so a cite of a
    file the PR renamed or deleted is parsed and reported instead of silently skipped."""
    fmap = files(ref)
    cre = cite_re(names)
    heads = {k: anchors(show(ref, fmap[k]) or "") if k in fmap else set() for k in names}
    bad = {}
    for path in scan_paths(ref):
        text = show(ref, path) or ""
        lines = text.split("\n")
        for pos, key, form, num in cites(text, cre):
            if fmap.get(key) == path:
                continue  # self-citation by name: headings may be phrased differently
            if num not in heads[key]:
                n = text.count("\n", 0, pos) + 1
                label = f"§{num}" if form == "§" else f"Phase {num}"
                bad.setdefault((key, label), []).append((f"{path}:{n}", (path, lines[n - 1].strip())))
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
    merge_base = merge_base.strip()
    names = set(files(merge_base)) | set(files(head_ref))
    base, head = broken(merge_base, names), broken(head_ref, names)
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
    opt = {k: old.pop(k) for k in OPTIONAL if k in old}
    for label, group in (("NEW", new), ("OLD", old), ("OPT", opt)):
        for (key, num), where in sorted(group.items()):
            print(f"{label}  {key} {num} does not resolve  <- {', '.join(where)}")
    if not head:
        print("all parsed citations resolve")
    sys.exit(1 if new else 0)


if __name__ == "__main__":
    main()
