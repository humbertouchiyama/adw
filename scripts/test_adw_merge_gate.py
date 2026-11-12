"""Tests for adw-merge-gate.py `check` against a fake `gh` that serves one PR fixture.
Run: cd scripts && python3 -m unittest -v test_adw_merge_gate"""
from __future__ import annotations

import copy
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "adw-merge-gate.py")
HEAD = "0123456789abcdef0123456789abcdef01234567"
OLD = "f" * 40
SPEC = "docs/adw/specs/x/u1.md"

FAKE_GH = r'''#!/usr/bin/env python3
import json, os, sys
fx = json.load(open(os.environ["FAKE_GH_FIXTURE"]))
args = sys.argv[1:]
with open(os.environ["FAKE_GH_LOG"], "a") as f:
    f.write(json.dumps(args) + "\n")
def count(key):
    path = os.environ["FAKE_GH_FIXTURE"] + "." + key
    n = int(open(path).read()) if os.path.exists(path) else 0
    open(path, "w").write(str(n + 1))
    return n
def seq(key, default):
    items = fx.get(key)
    if not items:
        return default
    return items[min(count(key), len(items) - 1)]
if fx.get("fail_all"):
    sys.stderr.write("HTTP 502: Bad Gateway\n"); sys.exit(1)
if args[:2] == ["pr", "view"]:
    view = dict(fx["view"])
    view["mergeable"] = seq("mergeable_seq", view.get("mergeable", "MERGEABLE"))
    print(json.dumps(view)); sys.exit(0)
if args[:2] == ["pr", "diff"]:
    if "--name-only" in args:
        print("\n".join(fx["names"])); sys.exit(0)
    if fx.get("diff_fail"):
        sys.stderr.write("could not find pull request diff: HTTP 406: Sorry, the diff exceeded the maximum number of lines\n"); sys.exit(1)
    sys.stdout.write(fx["diff"]); sys.exit(0)
if args[:2] == ["pr", "checks"]:
    checks = seq("checks_seq", fx.get("checks", []))
    if not checks:
        sys.stderr.write("no checks reported on the 'feat/x' branch\n"); sys.exit(1)
    print(json.dumps(checks))
    sys.exit(8 if any(c["bucket"] == "pending" for c in checks) else 1 if any(c["bucket"] in ("fail", "cancel") for c in checks) else 0)
if args[0] == "api":
    path = [a for a in args[1:] if a.startswith("repos/")][0]
    if "/contents/" in path:
        key = path.split("/contents/", 1)[1]
        if key not in fx["contents"]:
            sys.stderr.write("gh: Not Found (HTTP 404)\n"); sys.exit(1)
        sys.stdout.write(fx["contents"][key]); sys.exit(0)
    if path.endswith("/comments"):
        print(json.dumps(fx["comments"])); sys.exit(0)
sys.stderr.write("fake gh: unhandled %r\n" % args); sys.exit(1)
'''


def profile(auto: str | None = "on", ui: str | None = "`src/**`") -> str:
    rows = ["| **default base** | `develop` |", "| **production branch** | `main` |",
            "| **merge convention** | squash |"]
    if auto is not None:
        rows.append("| **auto-merge default** | `%s` |" % auto)
    rows.append("| **merge-protected paths** | `.claude/**` `.github/workflows/**` `firebase.json` |")
    if ui is not None:
        rows.append("| **UI paths** | %s |" % ui)
    return "\n".join([
        "# Repo profile", "", "## §2 — Layout", "", "| | |", "|---|---|",
        "| **artifact exclusion pathspec** | `':!docs/adw/**' ':!docs/superpowers/**'` — excludes specs+plans |",
        "", "## §3 — Branches", "", "| Role | Value |", "|---|---|", *rows,
        "", "## §11 — Trap domains", "", "| Domain | Match |", "|---|---|",
        "| migrations | path prefix `api/drizzle/` |", "| money | `formatMoney\\|money\\.ts\\|cents` |", "",
    ])


def spec(merge: str | None = "auto", base: str = "develop") -> str:
    lines = ["# u1 — a unit", "", "depth: D1"]
    if merge is not None:
        lines.append("merge: %s   # OPTIONAL — omitted = hold" % merge)
    lines += ["base: %s" % base, "", "## Acceptance", "1. It works."]
    return "\n".join(lines) + "\n"


RESULT = """## Smoke result
PASS — 1/1 cases · walk 1 at 0123456 · devices iphone17,ipad · 12m
| P1 | - | the list loads fast | - | none |
evidence: /tmp/sweep/SUMMARY.md, on the machine that ran the build · screens https://github.com/o/r/pull/7#issuecomment-1 · 2 images
"""
CASES = """## Smoke
### AC-1 Painel — the list shows the ward
- **Checks**: u1 AC 1
- **Device**: all
- **Entry point**: Painel
- **Preconditions**: the seeded ward
- **Steps**:
  1. Open Painel
- **Expected**:
  1. The ward shows
<!-- /smoke -->
"""
SCREENS = """## Screens
- SCREEN-1 · Painel · iphone17, ipad
"""
EVIDENCE = """```
contract   abcdef1            depth D1       resumed-from 0
verified   %s
smoke      walk 1 · 0 defects (0 blocking) · 0 gaps · valid 0 · refuted 0 · fixed 0 (0 unconfirmed) · cases 1/1 · audit 0 · 12m
```
""" % HEAD


def body(result: str = RESULT, cases: str = CASES, screens: str = SCREENS, evidence: str = EVIDENCE, extra: str = "") -> str:
    return "Adds the ward list.\n\n" + result + "\n" + cases + "\n" + screens + "\n" + extra + evidence


COMMENT = ("<!-- adw-screens head=%s walk=1 -->\n**Screens at 0123456, walk 1**\n\n#### SCREEN-1 · Painel\n"
           "![SCREEN-1 · iphone17](https://github.com/o/r/blob/c/pr-7/0123456/walk-1/SCREEN-1-iphone17.png?raw=true) "
           "![SCREEN-1 · ipad](https://github.com/o/r/blob/c/pr-7/0123456/walk-1/SCREEN-1-ipad.png?raw=true)\n")

DIFF = """diff --git a/src/app.ts b/src/app.ts
--- a/src/app.ts
+++ b/src/app.ts
@@ -1,2 +1,3 @@
 export const a = 1;
+export const total = sum(rows);
diff --git a/docs/adw/specs/x/u1.md b/docs/adw/specs/x/u1.md
--- /dev/null
+++ b/docs/adw/specs/x/u1.md
@@ -0,0 +1,2 @@
+# u1 — a unit
+merge: auto
"""


def clean() -> dict:
    return {
        "view": {"number": 7, "baseRefName": "develop", "headRefOid": HEAD, "labels": [],
                 "body": body(), "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN"},
        "names": ["src/app.ts", SPEC],
        "diff": DIFF,
        "checks": [{"name": "validate", "bucket": "pass"}],
        "comments": [{"id": 1, "body": "a review"}, {"id": 2, "body": COMMENT % HEAD}],
        "contents": {SPEC + "?ref=" + HEAD: spec(), ".claude/repo-profile.md?ref=develop": profile()},
    }


class Gate(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        bin_dir = os.path.join(self.tmp, "bin")
        os.mkdir(bin_dir)
        gh = os.path.join(bin_dir, "gh")
        with open(gh, "w") as f:
            f.write(FAKE_GH)
        os.chmod(gh, os.stat(gh).st_mode | stat.S_IEXEC)
        self.env = dict(os.environ, PATH=bin_dir + os.pathsep + os.environ["PATH"], ADW_GATE_POLL_SECONDS="0",
                        FAKE_GH_FIXTURE=os.path.join(self.tmp, "fx.json"), FAKE_GH_LOG=os.path.join(self.tmp, "gh.log"))
        self.local_profile = os.path.join(self.tmp, "repo-profile.md")
        self.fx = clean()
        self.local = profile()

    def check(self, specs=(SPEC,)):
        with open(self.env["FAKE_GH_FIXTURE"], "w") as f:
            json.dump(self.fx, f)
        with open(self.local_profile, "w") as f:
            f.write(self.local)
        args = [sys.executable, SCRIPT, "check", "--repo", "o/r", "--pr", "7", "--profile", self.local_profile]
        for s in specs:
            args += ["--spec-path", s]
        p = subprocess.run(args, env=self.env, capture_output=True, text=True)
        return p.returncode, p.stdout.strip(), p.stderr

    def assertHold(self, n, specs=(SPEC,)):
        rc, out, err = self.check(specs)
        self.assertEqual(rc, 1, out + err)
        self.assertTrue(out.startswith("hold %d " % n), out + err)
        self.assertEqual(len(out.splitlines()), 1, out)
        return out

    def assertPass(self, specs=(SPEC,)):
        rc, out, err = self.check(specs)
        self.assertEqual((rc, out), (0, "pass"), err)

    def set_body(self, **kw):
        self.fx["view"]["body"] = body(**kw)


class TestPass(Gate):
    def test_clean_pr_passes(self):
        self.assertPass()


class TestFlag(Gate):
    def test_hold_label_holds(self):
        self.fx["view"]["labels"] = [{"name": "adw:hold"}]
        self.assertHold(1)

    def test_specs_disagree_hold(self):
        self.fx["contents"]["docs/adw/specs/x/u2.md?ref=" + HEAD] = spec(merge="hold")
        self.assertHold(1, specs=(SPEC, "docs/adw/specs/x/u2.md"))

    def test_no_merge_line_holds(self):
        self.fx["contents"][SPEC + "?ref=" + HEAD] = spec(merge=None)
        self.assertHold(1)

    def test_kill_switch_off_on_base_holds(self):
        self.fx["contents"][".claude/repo-profile.md?ref=develop"] = profile(auto="off")
        self.assertHold(1)

    def test_no_auto_merge_row_locally_holds(self):
        self.local = profile(auto=None)
        self.assertHold(1)


class TestBase(Gate):
    def test_production_base_holds(self):
        self.fx["view"]["baseRefName"] = "main"
        self.fx["contents"][SPEC + "?ref=" + HEAD] = spec(base="main")
        self.fx["contents"][".claude/repo-profile.md?ref=main"] = profile()
        self.assertHold(2)

    def test_base_differs_from_intent_holds(self):
        self.fx["view"]["baseRefName"] = "feat/other"
        self.fx["contents"][".claude/repo-profile.md?ref=feat/other"] = profile()
        self.assertHold(2)


class TestVerified(Gate):
    def test_verified_row_stale_holds(self):
        self.set_body(evidence=EVIDENCE.replace(HEAD, OLD))
        self.assertHold(3)

    def test_blocked_label_holds(self):
        self.fx["view"]["labels"] = [{"name": "adw:blocked"}]
        self.assertHold(3)


class TestPaths(Gate):
    def test_protected_path_holds(self):
        self.fx["names"].append(".claude/repo-profile.md")
        out = self.assertHold(4)
        self.assertIn(".claude/repo-profile.md", out)

    def test_money_line_holds(self):
        self.fx["diff"] = DIFF.replace("+export const total = sum(rows);", "+export const total = formatMoney(rows);")
        self.assertHold(4)

    def test_money_line_in_excluded_path_passes(self):
        self.fx["diff"] = DIFF.replace("+merge: auto", "+the fee is 120 cents")
        self.assertPass()

    def test_diff_too_large_holds(self):
        self.fx["diff_fail"] = True
        self.assertHold(4)


class TestGitHub(Gate):
    def test_unknown_mergeable_bounded(self):
        self.fx["mergeable_seq"] = ["UNKNOWN"] * 5
        self.assertHold(5)
        self.setUp()
        self.fx["mergeable_seq"] = ["UNKNOWN", "MERGEABLE"]
        self.assertPass()

    def test_conflicting_holds(self):
        self.fx["view"]["mergeable"] = "CONFLICTING"
        self.assertHold(5)

    def test_failed_check_holds(self):
        self.fx["checks"] = [{"name": "validate", "bucket": "fail"}]
        out = self.assertHold(5)
        self.assertIn("validate", out)

    def test_pending_check_then_pass(self):
        self.fx["checks_seq"] = [[{"name": "validate", "bucket": "pending"}], [{"name": "validate", "bucket": "pass"}]]
        self.assertPass()

    def test_check_pending_past_bound_holds(self):
        self.fx["checks"] = [{"name": "validate", "bucket": "pending"}]
        self.assertHold(5)

    def test_no_checks_passes(self):
        self.fx["checks"] = []
        self.assertPass()


class TestWalk(Gate):
    def result(self, first=None, rows="", lines=""):
        r = RESULT
        if first is not None:
            r = r.replace("PASS — 1/1 cases · walk 1 at 0123456 · devices iphone17,ipad · 12m", first)
        r = r.replace("| P1 | - | the list loads fast | - | none |\n", "| P1 | - | the list loads fast | - | none |\n" + rows + lines)
        self.set_body(result=r)

    def test_walk_at_old_head_holds(self):
        self.result(first="PASS — 1/1 cases · walk 1 at fffffff · devices iphone17,ipad · 12m")
        self.assertHold(7)

    def test_no_walk_line_holds(self):
        self.set_body(result="")
        self.assertHold(7)

    def test_unaudited_holds(self):
        self.result(first="PASS — 1/1 cases · walk 1 at 0123456 · devices iphone17,ipad · 12m · unaudited: check 8")
        self.assertHold(7)

    def test_audit_row_not_zero_holds(self):
        self.set_body(evidence=EVIDENCE.replace("audit 0", "audit 1"))
        self.assertHold(7)

    def test_not_run_holds(self):
        self.set_body(result="## Smoke result\nsmoke not run — queued behind other\n")
        self.assertHold(7)

    def test_valid_row_holds(self):
        self.result(rows="| D1 | worth-fixing | the total is wrong | code | fix |\n", lines="valid: D1 — image, spec, file:1\n")
        self.assertHold(7)

    def test_unchecked_row_holds(self):
        self.result(rows="| D1 | worth-fixing | the total is wrong | code | fix |\n", lines="unchecked: D1\n")
        self.assertHold(7)

    def test_unconfirmed_fix_holds(self):
        self.result(lines="fixed: D2 (walk 1) in abcdef1, unconfirmed\n")
        self.assertHold(7)

    def test_refuted_blocking_row_holds(self):
        self.result(rows="| D1 | blocking | the button floats | code | fix |\n", lines="refuted: D1 — a keyboard over it\n")
        self.assertHold(7)

    def test_gap_naming_ac_holds(self):
        self.result(rows="| G1 | - | AC-1 blocked: seed absent | runner | none |\n")
        self.assertHold(7)

    def test_gap_naming_walked_device_holds(self):
        self.result(rows="| G1 | - | ipad not runnable | runner | none |\n")
        self.assertHold(7)

    def test_gap_naming_unwalked_device_passes(self):
        self.result(rows="| G1 | - | iphone16e not provisioned | runner | none |\n")
        self.assertPass()

    def test_polish_and_refuted_rows_pass(self):
        self.result(rows="| D1 | polish | a margin is 2px off | code | none |\n| D2 | worth-fixing | a label wraps | code | fix |\n",
                    lines="refuted: D2 — the spec does not ask for one line\n")
        self.assertPass()


class TestScreens(Gate):
    def test_missing_image_holds(self):
        self.fx["comments"][1]["body"] = (COMMENT % HEAD).split(" ![SCREEN-1 · ipad]")[0] + "\n"
        out = self.assertHold(8)
        self.assertIn("ipad", out)

    def test_comment_for_old_head_holds(self):
        self.fx["comments"][1]["body"] = COMMENT % OLD
        self.assertHold(8)

    def test_no_comment_holds(self):
        self.fx["comments"] = [{"id": 1, "body": "a review"}]
        self.assertHold(8)

    def test_empty_screens_list_holds(self):
        self.set_body(screens="## Screens\n")
        self.assertHold(8)

    def test_no_screens_list_holds(self):
        self.set_body(screens="")
        self.assertHold(8)

    def test_screens_none_on_pr_with_cases_takes_ui_paths_test(self):
        self.set_body(screens="## Screens\nScreens: none — the change is an API field no screen shows\n")
        self.fx["names"] = ["api/x.ts", SPEC]
        self.assertPass()
        self.fx["names"] = ["src/app.ts", SPEC]
        self.assertHold(9)


class TestSmokeNone(Gate):
    def smoke_none(self, names):
        self.set_body(result="", cases="Smoke: none — a backend field no user sees\n", screens="")
        self.fx["names"] = names
        self.fx["comments"] = []

    def test_smoke_none_outside_ui_paths_passes(self):
        self.smoke_none(["api/x.ts", SPEC])
        self.assertPass()

    def test_smoke_none_touching_ui_paths_holds(self):
        self.smoke_none(["src/app.ts", SPEC])
        self.assertHold(9)

    def test_no_ui_paths_row_holds(self):
        self.smoke_none(["api/x.ts", SPEC])
        self.local = profile(ui=None)
        self.assertHold(9)

    def test_neither_cases_nor_smoke_none_holds(self):
        self.set_body(result="", cases="", screens="")
        self.assertHold(9)


class TestErrors(Gate):
    def test_gh_failure_is_hold_0(self):
        self.fx["fail_all"] = True
        rc, out, err = self.check()
        self.assertEqual(rc, 2, out + err)
        self.assertTrue(out.startswith("hold 0 gate error: "), out)

    def test_bad_flag_exits_2(self):
        p = subprocess.run([sys.executable, SCRIPT, "check", "--repo", "o/r"], env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)


if __name__ == "__main__":
    unittest.main()
