#!/usr/bin/env python3
"""Remove what one /adw-build run left on disk, and nothing else (commands/adw-build.md Phase 5).

The run names everything it creates after its slug, so the slug is the whole scope:

  adw-<slug>-uNN[+uMM]           unit worktree           adw-build Phase 2
  adw-close-<slug>               chain close worktree    adw-build Phase 4
  pr-ready-<slug>-uNN|close-v<k> verify worktree         pr-ready §4.3, REF from adw-build §3.4
  pr-<N>                         review worktree         review-core §1.1, one per --pr
  Xcode DerivedData whose WorkspacePath is inside one of those worktrees, once it is gone

A worktree is removed only when every guard holds. Any doubt keeps it and prints why:
no process names its path; its HEAD is on a remote ref (or is the head of a merged PR); and
it has no change except a --provisioned file. A verify worktree is a throwaway checkout of a
pushed sha, so its gate output is reset first, exactly as pr-ready §4.3 does. Never --force.

Exit codes: 0 ran (kept items are not errors) · 1 --repo is not inside a git checkout · 2 bad flag.
"""
import argparse
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys

DERIVED_DATA = os.path.expanduser("~/Library/Developer/Xcode/DerivedData")
DD_NAME = re.compile(r"^[A-Za-z0-9_.-]+-[a-z]{28}$")
DAEMONS = ("org.gradle.launcher.daemon.bootstrap.GradleDaemon", "KotlinCompileDaemon")


def git(*args, cwd):
    p = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def scope(slug, prs):
    """Return (kind, name regex, expected branch or None) per worktree kind this run creates."""
    s = re.escape(slug)
    units = r"u\d+(?:\+u\d+)*"
    out = [
        ("unit", re.compile(rf"^adw-{s}-{units}$"), lambda n: "adw/" + n[len("adw-"):]),
        ("close", re.compile(rf"^adw-close-{s}$"), lambda n: f"adw/{slug}"),
        ("verify", re.compile(rf"^pr-ready-{s}-(?:{units}|close)-v\d+$"), None),
    ]
    for n in prs:
        out.append(("review", re.compile(rf"^pr-{n}$"), None))
    return out


def kind_of(name, kinds):
    for kind, rx, branch in kinds:
        if rx.match(name):
            return kind, branch
    return None, None


def worktrees(main):
    rc, out, _ = git("worktree", "list", "--porcelain", cwd=main)
    rows, cur = [], None
    for line in out.splitlines():
        if line.startswith("worktree "):
            cur = {"path": line[len("worktree "):], "branch": None}
            rows.append(cur)
        elif line.startswith("branch ") and cur is not None:
            cur["branch"] = line[len("branch "):].removeprefix("refs/heads/")
    return rows


def processes():
    """[(pid, command line, cwd)] for every process but this one and its parent shell."""
    skip = {str(os.getpid()), str(os.getppid())}
    p = subprocess.run(["ps", "-axww", "-o", "pid=,command="], capture_output=True, text=True)
    cmds = {}
    for line in p.stdout.splitlines():
        pid, _, cmd = line.strip().partition(" ")
        if pid.isdigit() and pid not in skip:
            cmds[pid] = cmd.strip()
    cwds, pid = {}, None
    p = subprocess.run(["lsof", "-nP", "-d", "cwd", "-Fpn"], capture_output=True, text=True)
    for line in p.stdout.splitlines():
        if line.startswith("p"):
            pid = line[1:]
        elif line.startswith("n") and pid:
            cwds[pid] = line[1:]
    return [(pid, cmd, cwds.get(pid, "")) for pid, cmd in cmds.items()]


def busy(path, procs):
    """The pid of a process whose cwd is inside path or whose command line names it, else None.

    A build daemon keeps the cwd it started in for hours after its last build, and serves builds of
    any project, so its cwd alone proves nothing. A build it runs for this path has a client whose
    command line names the path (`<wt>/gradle/wrapper/gradle-wrapper.jar`), and that client counts."""
    for pid, cmd, cwd in procs:
        daemon = any(d in cmd for d in DAEMONS)
        if not daemon and (cwd == path or cwd.startswith(path + "/")):
            return pid
        if any(path + end in cmd for end in ("/", " ", '"', "'")) or cmd.endswith(path):
            return pid
    return None


def size_kb(path):
    p = subprocess.run(["du", "-sk", path], capture_output=True, text=True)
    try:
        return int(p.stdout.split()[0])
    except (IndexError, ValueError):
        return 0


def gb(kb):
    return f"{kb / 1048576:.1f} GB"


def on_remote(wt):
    rc, out, _ = git("for-each-ref", "--contains", "HEAD", "--format=%(refname)", "refs/remotes", cwd=wt)
    return rc == 0 and bool(out.strip())


def prs_for(branch, main):
    """The PRs whose head branch is `branch`, or None when gh did not answer."""
    p = subprocess.run(["gh", "pr", "list", "--state", "all", "--head", branch, "--json", "number,state,headRefOid"],
                       cwd=main, capture_output=True, text=True)
    if p.returncode != 0:
        return None
    try:
        return json.loads(p.stdout or "[]")
    except ValueError:
        return None


def pr_by_number(n, main):
    """[the PR] numbered n, or None when gh did not answer."""
    p = subprocess.run(["gh", "pr", "view", str(n), "--json", "number,state,headRefOid"],
                       cwd=main, capture_output=True, text=True)
    if p.returncode != 0:
        return None
    try:
        return [json.loads(p.stdout)]
    except ValueError:
        return None


def covered(wt, prs):
    """True when HEAD is a PR's head, or an ancestor of one whose commits are here.

    A fix pushed from another worktree leaves this HEAD behind its PR's head, and a merged PR's
    remote branch may be pruned, so HEAD is on no remote ref. The PR head still proves GitHub has it."""
    head = git("rev-parse", "HEAD", cwd=wt)[1].strip()
    for p in prs:
        oid = p.get("headRefOid") or ""
        if head and oid == head:
            return True
        if oid and git("cat-file", "-e", oid + "^{commit}", cwd=wt)[0] == 0 \
                and git("merge-base", "--is-ancestor", head, oid, cwd=wt)[0] == 0:
            return True
    return False


def changes(wt):
    """Return [(status, path)] for every tracked change and untracked file. Ignored files are not listed."""
    rc, out, _ = git("status", "--porcelain=v1", "-z", "--untracked-files=normal", cwd=wt)
    if rc != 0:
        return None
    items, parts, i = [], out.split("\0"), 0
    while i < len(parts):
        e = parts[i]
        i += 1
        if not e:
            continue
        st, path = e[:2], e[3:]
        if st[0] in "RC":
            i += 1  # the rename source follows as its own field
        items.append((st, path))
    return items


def clean_worktrees(main, kinds, provisioned, dry, procs, here):
    removed, kept, removed_kb = [], [], 0
    root = os.path.join(main, ".claude", "worktrees")
    for row in worktrees(main):
        path = os.path.realpath(row["path"])
        name = os.path.basename(path)
        kind, want_branch = kind_of(name, kinds)
        if not kind or os.path.dirname(path) != root:
            continue

        def keep(why):
            kept.append(name)
            print(f"kept     {name}  {why}")

        if here == path or here.startswith(path + "/"):
            keep("this session runs inside it")
            continue
        if want_branch and row["branch"] != want_branch(name):
            keep(f"branch is {row['branch'] or 'detached'}, expected {want_branch(name)}")
            continue
        pid = busy(path, procs)
        if pid:
            keep(f"process {pid} uses it")
            continue
        if want_branch:
            # A unit or close worktree goes only once its work is a PR. A squash-merged branch the
            # remote deleted is on no remote ref, and its PR head proves the commits are on GitHub.
            prs = prs_for(row["branch"], main)
            if prs is None:
                keep(f"gh did not answer, so the PR for {row['branch']} is unknown")
                continue
            if not prs:
                keep(f"no PR has head {row['branch']}")
                continue
            if not on_remote(path) and not covered(path, prs):
                keep("HEAD is on no remote ref and is no PR's head")
                continue
        elif not on_remote(path):
            # A review worktree pushes its apply fixes, so its PR's head can cover a pruned branch.
            prs = pr_by_number(name[len("pr-"):], main) if kind == "review" else None
            if not prs or not covered(path, prs):
                keep("HEAD is on no remote ref")
                continue
        items = changes(path)
        if items is None:
            keep("git status failed")
            continue
        dirty_prov = [p for st, p in items if st == " M" and p in provisioned]
        other = [p for st, p in items if not (st == " M" and p in provisioned)]
        if other and kind != "verify":
            keep("uncommitted: " + ", ".join(other[:3]) + (" …" if len(other) > 3 else ""))
            continue

        kb = size_kb(path)
        if dry:
            removed.append(name)
            removed_kb += kb
            print(f"would remove  {name}  {gb(kb)}")
            continue
        if kind == "verify":
            steps = [("reset", "-q", "--hard", "HEAD"), ("clean", "-fdq")]
        else:
            steps = [("checkout", "--", *dirty_prov)] if dirty_prov else []
        failed = next((e for s in steps for rc, _, e in [git(*s, cwd=path)] if rc != 0), None)
        if failed is not None:
            keep("restore failed: " + (failed.strip().splitlines() or ["?"])[0])
            continue
        rc, _, err = git("worktree", "remove", path, cwd=main)
        if rc != 0:
            keep("git worktree remove failed: " + (err.strip().splitlines() or ["?"])[0])
            continue
        removed.append(name)
        removed_kb += kb
        print(f"removed  {name}  {gb(kb)}")
    return removed, kept, removed_kb


def clean_derived_data(main, kinds, dd, dry, procs, gone):
    """DerivedData of a scope worktree that no longer exists. Never one whose worktree is still there.

    `gone` names the worktrees a dry run would have removed, so the dry run lists their DerivedData too."""
    root = os.path.join(main, ".claude", "worktrees") + "/"
    done, kept, done_kb = [], [], 0
    if not os.path.isdir(dd):
        return done, kept, done_kb
    for d in sorted(os.listdir(dd)):
        full = os.path.join(dd, d)
        if not DD_NAME.match(d) or os.path.islink(full) or not os.path.isdir(full):
            continue
        try:
            with open(os.path.join(full, "info.plist"), "rb") as f:
                wp = plistlib.load(f).get("WorkspacePath", "")
        except (OSError, plistlib.InvalidFileException, ValueError):
            continue
        if not wp.startswith(root):
            continue
        name = wp[len(root):].split("/", 1)[0]
        if not kind_of(name, kinds)[0] or (os.path.exists(root + name) and name not in gone):
            continue
        if busy(full, procs) or busy(wp, procs):
            kept.append(d)
            print(f"kept     {d}  a process uses it ({name})")
            continue
        kb = size_kb(full)
        if not dry:
            shutil.rmtree(full, ignore_errors=True)
            if os.path.exists(full):
                kept.append(d)
                print(f"kept     {d}  delete failed ({name})")
                continue
        done.append(d)
        done_kb += kb
        print(f"{'would delete' if dry else 'deleted '}  {d}  {gb(kb)}  (DerivedData of {name})")
    return done, kept, done_kb


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True, help="any checkout of the consuming repo; its main checkout is found")
    ap.add_argument("--slug", required=True)
    ap.add_argument("--pr", action="append", type=int, default=[], help="a PR this run opened; repeat")
    ap.add_argument("--provisioned", action="append", default=[],
                    help="a tracked file provisioning rewrites (repo-profile §18); repeat")
    ap.add_argument("--derived-data", default=DERIVED_DATA, help=argparse.SUPPRESS)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", a.slug):
        ap.error(f"bad --slug: {a.slug!r}")

    rc, common, _ = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=os.path.abspath(a.repo))
    if rc != 0 or os.path.basename(common.strip()) != ".git":
        print(f"adw-run-clean: {a.repo} is not inside a git checkout with a main working tree", file=sys.stderr)
        sys.exit(1)
    main_dir = os.path.realpath(os.path.dirname(common.strip()))

    rc, here, _ = git("rev-parse", "--show-toplevel", cwd=os.getcwd())
    here = os.path.realpath(here.strip()) if rc == 0 else ""
    kinds = scope(a.slug, a.pr)
    procs = processes()
    wt, kept, wt_kb = clean_worktrees(main_dir, kinds, set(a.provisioned), a.dry_run, procs, here)
    gone = set(wt) if a.dry_run else set()
    dd, dd_kept, dd_kb = clean_derived_data(main_dir, kinds, a.derived_data, a.dry_run, procs, gone)
    verb = "would free" if a.dry_run else "freed"
    print(f"run-clean{' (dry run)' if a.dry_run else ''}: {len(wt)} worktrees, {len(dd)} DerivedData dirs, "
          f"{verb} {gb(wt_kb + dd_kb)}; kept {len(kept) + len(dd_kept)}")


if __name__ == "__main__":
    main()
