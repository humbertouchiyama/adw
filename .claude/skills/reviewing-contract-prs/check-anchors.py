#!/usr/bin/env python3
"""Resolve every cross-file citation in the ADW contract against real headings.

Usage: check-anchors.py <base-ref> <head-ref>   (run from the adw repo root)

Prints citations that do not resolve at <head-ref>, split into NEW (the PR adds a
citing site) and OLD (already broken at base). Exit 1 if any NEW.
A citation is `<file> §N`, `<file> §N.M` or `<file> Phase N[.M][a]`, with or without
`.md` and backticks. `repo-profile §N` resolves against docs/repo-profile-EXAMPLE.md.
Bare `§N` (self-reference) is not checked.
"""
import re, subprocess, sys

FILES = {
    "adw-core": "commands/adw-core.md", "adw-build": "commands/adw-build.md",
    "adw-init": "commands/adw-init.md", "pr-ready": "commands/pr-ready.md",
    "review-core": "commands/review-core.md", "code-review": "commands/code-review.md",
    "cleanup": "commands/cleanup.md", "design": "docs/00-design.md",
    "repo-profile": "docs/repo-profile-EXAMPLE.md",
}
SCAN = list(FILES.values()) + ["README.md"]
# A heading, or a bold paragraph lead used as an anchor (`**§4.2 — Gate-file tripwire.**`).
HEAD_RE = re.compile(r"^(?:#{1,6}\s+|\*\*)(?:Phase\s+|§\s?)?(\d+(?:\.\d+)*[a-z]?)(?=[\s.—:-]|$)")
CITE_RE = re.compile(r"`?\b(" + "|".join(FILES) + r")(?:\.md)?`?\s+(?:(§)\s?|Phase\s+)(\d+(?:\.\d+)*[a-z]?)")


def show(ref, path):
    r = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


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
    heads = {k: anchors(show(ref, p) or "") for k, p in FILES.items()}
    bad = {}
    for path in SCAN:
        text = show(ref, path)
        if text is None:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            for m in CITE_RE.finditer(line):
                key, num = m.group(1), m.group(3)
                form = f"§{num}" if m.group(2) else f"Phase {num}"
                if FILES.get(key) == path:
                    continue  # self-citation by name: headings may be phrased differently
                if num not in heads[key]:
                    bad.setdefault((key, form), []).append(f"{path}:{n}")
    return bad


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    base, head = broken(sys.argv[1]), broken(sys.argv[2])
    # NEW when the PR adds a citing site, even to an anchor that was already broken.
    new = {k: v for k, v in head.items() if len(v) > len(base.get(k, []))}
    old = {k: v for k, v in head.items() if k not in new}
    for label, group in (("NEW", new), ("OLD", old)):
        for (key, num), where in sorted(group.items()):
            print(f"{label}  {key} {num} does not resolve  <- {', '.join(where[:5])}"
                  + (f" (+{len(where) - 5})" if len(where) > 5 else ""))
    if not head:
        print("all citations resolve")
    sys.exit(1 if new else 0)


if __name__ == "__main__":
    main()
