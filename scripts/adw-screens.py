#!/usr/bin/env python3
"""adw-screens.py: push a walk's screen images to the app repo's screens ref and post one PR comment.

The screenshot relay of adw-build §3.8 runs it after the walk's Audit:

  python3 adw-screens.py --repo <owner/repo> --checkout <path> --pr <N> --head <sha> --walk <k>
      --screens <screens.md> --dir <sweep>/screens --ref <ref>

It reads the `## Screens` rows (`- SCREEN-<n> · <title> · <device>, ...`), takes each listed pair's
`<dir>/SCREEN-<n>-<device>.png`, scales it to 1000 px on its long side, and commits all of them on top of
the ref's tip under `pr-<N>/<sha7>/walk-<k>/`, with no worktree (a temp index). A push the remote rejects
because the ref moved is retried once on the new tip. Then one PR comment carries the images; a comment
with the `<!-- adw-screens ` marker is replaced, not added to. A listed pair with no file is left out:
the gate, not this script, holds the PR for it.

Prints `screens <comment url> · <n> images` or `screens none — <why>`. Exit 0; 1 when the push or the
comment failed after one retry; 2 on a bad flag.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile

MARKER = "<!-- adw-screens "
ROW = re.compile(r"^- (SCREEN-[0-9]+) · (.+) · ([^·]+)$")


class Failed(Exception):
    pass


def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="adw-screens.py")
    p.add_argument("--repo", required=True)
    p.add_argument("--checkout", required=True)
    p.add_argument("--pr", type=int, required=True)
    p.add_argument("--head", required=True)
    p.add_argument("--walk", type=int, required=True)
    p.add_argument("--screens", required=True)
    p.add_argument("--dir", required=True)
    p.add_argument("--ref", required=True)
    a = p.parse_args(argv)
    if not re.fullmatch(r"[0-9a-f]{40}", a.head):
        p.error("--head must be a 40-character commit sha")
    if not re.fullmatch(r"[^/\s]+/[^/\s]+", a.repo):
        p.error("--repo must be <owner>/<repo>")
    if not a.ref.startswith("refs/"):
        p.error("--ref must be a full ref name, refs/...")
    return a


def listed(screens_md: str) -> list[tuple[str, str, list[str]]]:
    """(id, title, devices) for each `## Screens` row, in file order; code fences are skipped."""
    rows, fence = [], False
    with open(screens_md, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.lstrip().startswith(("```", "~~~")):
                fence = not fence
                continue
            m = None if fence else ROW.match(line)
            if m:
                devs = [d.strip().lower() for d in m.group(3).split(",") if d.strip()]
                rows.append((m.group(1), m.group(2).strip(), devs))
    return rows


def git(checkout: str, *args: str, env: dict | None = None, check: bool = True) -> subprocess.CompletedProcess:
    p = subprocess.run(["git", "-C", checkout, *args], env=env, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise Failed("git %s: %s" % (args[0], p.stderr.strip()))
    return p


def remote_tip(checkout: str, ref: str) -> str | None:
    p = git(checkout, "fetch", "-q", "origin", ref, check=False)
    if p.returncode != 0:
        if "couldn't find remote ref" in p.stderr:
            return None
        raise Failed("git fetch %s: %s" % (ref, p.stderr.strip()))
    return git(checkout, "rev-parse", "FETCH_HEAD").stdout.strip()


def build_commit(checkout: str, tip: str | None, files: list[tuple[str, str]], message: str) -> str:
    """A commit of `tip`'s tree plus `files` [(repo path, local file)], built in a temp index."""
    fd, index = tempfile.mkstemp(prefix="adw-screens-index-")
    os.close(fd)
    os.remove(index)
    env = dict(os.environ, GIT_INDEX_FILE=index)
    try:
        git(checkout, "read-tree", *([tip] if tip else ["--empty"]), env=env)
        for path, local in files:
            blob = git(checkout, "hash-object", "-w", local).stdout.strip()
            git(checkout, "update-index", "--add", "--cacheinfo", "100644,%s,%s" % (blob, path), env=env)
        tree = git(checkout, "write-tree", env=env).stdout.strip()
        parent = ["-p", tip] if tip else []
        return git(checkout, "commit-tree", tree, *parent, "-m", message).stdout.strip()
    finally:
        if os.path.exists(index):
            os.remove(index)


def push_images(a: argparse.Namespace, files: list[tuple[str, str]]) -> str:
    message = "adw-screens: pr-%d %s walk %d" % (a.pr, a.head[:7], a.walk)
    for attempt in (1, 2):
        commit = build_commit(a.checkout, remote_tip(a.checkout, a.ref), files, message)
        p = git(a.checkout, "push", "-q", "origin", "%s:%s" % (commit, a.ref), check=False)
        if p.returncode == 0:
            return commit
        why = p.stderr.strip()
    raise Failed("push to %s rejected twice: %s" % (a.ref, why))


def gh_json(*args: str, body: str | None = None) -> object:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"body": body}, f)
        payload = f.name
    try:
        cmd = ["gh", "api", *args] + (["--input", payload] if body is not None else [])
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            raise Failed("gh api %s: %s" % (" ".join(args), p.stderr.strip()))
        return json.loads(p.stdout or "null")
    finally:
        os.remove(payload)


def post_comment(a: argparse.Namespace, body: str) -> str:
    last = ""
    for attempt in (1, 2):
        try:
            comments = gh_json("repos/%s/issues/%d/comments" % (a.repo, a.pr), "--paginate")
            mine = [c for c in comments or [] if str(c.get("body", "")).startswith(MARKER)]
            if mine:
                out = gh_json("-X", "PATCH", "repos/%s/issues/comments/%d" % (a.repo, mine[-1]["id"]), body=body)
            else:
                out = gh_json("-X", "POST", "repos/%s/issues/%d/comments" % (a.repo, a.pr), body=body)
            return out["html_url"]
        except (Failed, KeyError, TypeError, ValueError) as e:
            last = str(e)
    raise Failed("comment failed twice: %s" % last)


def scaled(src: str, out_dir: str) -> str:
    dst = os.path.join(out_dir, os.path.basename(src))
    p = subprocess.run(["sips", "-Z", "1000", src, "--out", dst], capture_output=True, text=True)
    if p.returncode != 0:
        raise Failed("sips could not scale %s: %s" % (src, p.stderr.strip()))
    return dst


def main(argv: list[str]) -> int:
    a = parse_args(argv)
    rows = listed(a.screens) if os.path.isfile(a.screens) else []
    present = {n.lower(): os.path.join(a.dir, n) for n in os.listdir(a.dir)} if os.path.isdir(a.dir) else {}
    shots = []  # (id, title, device, local path)
    for sid, title, devs in rows:
        for d in devs:
            path = present.get(("%s-%s.png" % (sid, d)).lower())
            if path:
                shots.append((sid, title, d, path))
    if not shots:
        print("screens none — no images in %s" % a.dir)
        return 0
    prefix = "pr-%d/%s/walk-%d" % (a.pr, a.head[:7], a.walk)
    try:
        with tempfile.TemporaryDirectory(prefix="adw-screens-") as tmp:
            files = [("%s/%s-%s.png" % (prefix, sid, d), scaled(path, tmp)) for sid, _, d, path in shots]
            commit = push_images(a, files)
        base = "https://github.com/%s/blob/%s/%s" % (a.repo, commit, prefix)
        lines = ["%shead=%s walk=%d -->" % (MARKER, a.head, a.walk),
                 "**Screens at %s, walk %d**" % (a.head[:7], a.walk)]
        for sid, title, _ in rows:
            imgs = ["![%s · %s](%s/%s-%s.png?raw=true)" % (s, d, base, s, d) for s, _, d, _ in shots if s == sid]
            if imgs:
                lines += ["", "#### %s · %s" % (sid, title), " ".join(imgs)]
        url = post_comment(a, "\n".join(lines) + "\n")
    except Failed as e:
        print("adw-screens: %s" % e, file=sys.stderr)
        return 1
    print("screens %s · %d images" % (url, len(shots)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
