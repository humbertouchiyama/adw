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
import time
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
if args[:2] == ["pr", "merge"]:
    if count("merge") < fx.get("merge_fail", 0):
        sys.stderr.write("GraphQL: Head branch was modified. Review and try the merge again.\n"); sys.exit(1)
    if not fx.get("merge_noop"):
        open(os.environ["FAKE_GH_FIXTURE"] + ".merged", "w").write("1")
    sys.exit(fx.get("merge_rc", 0))
if args[:2] == ["pr", "view"]:
    merged = os.path.exists(os.environ["FAKE_GH_FIXTURE"] + ".merged")
    if merged and fx.get("readback_fail"):
        sys.stderr.write("HTTP 502: Bad Gateway\n"); sys.exit(1)
    view = dict(fx["view"])
    view["state"] = "MERGED" if merged else "OPEN"
    view["mergeCommit"] = {"oid": "abcdef0" + "1" * 33} if merged else None
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


def diff_file(path: str, added: str = "x") -> str:
    """One file's diff block that adds one line."""
    return ("diff --git a/%s b/%s\n--- a/%s\n+++ b/%s\n@@ -1 +1,2 @@\n ctx\n+%s\n" % (path, path, path, path, added))


def diff_for(names) -> str:
    return "".join(diff_file(n) for n in names)


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

    def test_merge_template_line_holds(self):
        self.fx["contents"][SPEC + "?ref=" + HEAD] = spec(merge="auto | hold")
        self.assertHold(1)

    def test_merge_line_outside_the_header_holds(self):
        s = spec(merge=None).replace("1. It works.", "1. It works.\n\nmerge: auto-merges duplicate rows\n")
        self.fx["contents"][SPEC + "?ref=" + HEAD] = s
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


class TestSignOff(Gate):
    def test_sign_off_pending_holds(self):
        self.set_body(evidence=EVIDENCE.replace("verified ", "visual     rows 4 · pass 1 · fail 0 · unscored 3 · no image 0 · rounds 5 · sign-off pending\nverified "))
        self.assertHold(10)

    def test_signed_off_passes(self):
        self.set_body(evidence=EVIDENCE.replace("verified ", "visual     rows 4 · pass 4 · fail 0 · unscored 0 · no image 0 · rounds 5 · sign-off 1a2b3c4\nverified "))
        self.assertPass()

    def test_prose_about_a_pending_sign_off_passes(self):
        self.set_body(extra="visual: sign-off pending was the state before the owner said ok\n")
        self.assertPass()

    def test_sign_off_none_passes(self):
        self.set_body(evidence=EVIDENCE.replace("verified ", "visual     rows 2 · pass 2 · fail 0 · unscored 0 · no image 0 · rounds 1 · sign-off none\nverified "))
        self.assertPass()


class TestPaths(Gate):
    def test_protected_path_holds(self):
        self.fx["diff"] += diff_file(".claude/repo-profile.md")
        out = self.assertHold(4)
        self.assertIn(".claude/repo-profile.md", out)

    def test_money_line_holds(self):
        self.fx["diff"] = DIFF.replace("+export const total = sum(rows);", "+export const total = formatMoney(rows);")
        self.assertHold(4)

    def test_money_line_in_excluded_path_passes(self):
        self.fx["diff"] = DIFF.replace("+merge: auto", "+the fee is 120 cents")
        self.assertPass()

    def test_diff_too_large_holds(self):
        self.fx["diff_fail"] = True   # --name-only would still answer: the gate must not lean on it
        self.assertHold(4)

    def test_rename_out_of_a_protected_path_holds(self):
        self.fx["diff"] += ("diff --git a/.github/workflows/deploy.yml b/ci/deploy.yml\nsimilarity index 100%\n"
                            "rename from .github/workflows/deploy.yml\nrename to ci/deploy.yml\n")
        self.fx["names"] = ["src/app.ts", SPEC, "ci/deploy.yml"]
        out = self.assertHold(4)
        self.assertIn(".github/workflows/deploy.yml", out)

    def test_money_line_in_a_quoted_path_holds(self):
        self.fx["diff"] = DIFF.replace("+++ b/src/app.ts", '+++ "b/src/pre\\303\\247o.ts"').replace(
            "+export const total = sum(rows);", "+export const total = formatMoney(rows);")
        self.assertHold(4)

    def test_added_line_that_looks_like_a_header_is_still_scanned(self):
        self.fx["diff"] = DIFF.replace("+export const total = sum(rows);",
                                       "+++ a note\n+export const total = formatMoney(rows);")
        self.assertHold(4)

    def test_a_diff_touching_a_money_file_holds_without_a_money_line(self):
        self.fx["diff"] += diff_file("src/lib/money.ts", added="export const x = 1;")
        self.assertHold(4)

    def test_rename_into_a_money_path_prefix_holds(self):
        self.local = self.local.replace("| money | `formatMoney\\|money\\.ts\\|cents` |", "| money | path prefix `api/billing/` |")
        self.fx["contents"][".claude/repo-profile.md?ref=develop"] = self.local
        self.fx["diff"] += ("diff --git a/api/x.ts b/api/billing/x.ts\nsimilarity index 100%\n"
                            "rename from api/x.ts\nrename to api/billing/x.ts\n")
        self.assertHold(4)

    def test_a_protected_row_with_no_glob_holds(self):
        self.local = self.local.replace("`.claude/**` `.github/workflows/**` `firebase.json`", ".claude/** .github/workflows/**")
        self.fx["contents"][".claude/repo-profile.md?ref=develop"] = self.local
        self.assertHold(4)

    def test_a_money_row_with_no_pattern_holds(self):
        self.local = self.local.replace("| money | `formatMoney\\|money\\.ts\\|cents` |", "| money | formatMoney or cents |")
        self.fx["contents"][".claude/repo-profile.md?ref=develop"] = self.local
        self.assertHold(4)

    def test_a_file_moved_out_of_a_money_prefix_holds(self):
        self.local = self.local.replace("| money | `formatMoney\\|money\\.ts\\|cents` |", "| money | path prefix `api/billing/` |")
        self.fx["contents"][".claude/repo-profile.md?ref=develop"] = self.local
        self.fx["diff"] += ("diff --git a/api/billing/charge.ts b/api/core/charge.ts\nsimilarity index 90%\n"
                            "rename from api/billing/charge.ts\nrename to api/core/charge.ts\n"
                            "--- a/api/billing/charge.ts\n+++ b/api/core/charge.ts\n@@ -1 +1 @@\n-return amount*100\n+return amount*10\n")
        self.assertHold(4)

    def test_no_merge_protected_row_holds(self):
        self.local = self.local.replace("| **merge-protected paths** | `.claude/**` `.github/workflows/**` `firebase.json` |\n", "")
        self.assertHold(4)

    def test_path_the_base_profile_protects_holds_when_the_local_copy_is_stale(self):
        self.local = self.local.replace(" `firebase.json`", "")
        self.fx["diff"] += diff_file("firebase.json")
        self.assertHold(4)


TEST_ROW = "| **test sources** | `**/*.test.ts` `**/__tests__/**` |\n"


class TestTestSources(Gate):
    """A money word on an added line of a test source is not a money change (AXCMedApp #807, #768): the
    test sources row exempts those lines, and nothing else."""

    def with_row(self, local=True, base=True):
        protected = "| **merge-protected paths** |"
        if local:
            self.local = self.local.replace(protected, TEST_ROW + protected)
        if base:
            self.fx["contents"][".claude/repo-profile.md?ref=develop"] = profile().replace(protected, TEST_ROW + protected)

    def test_money_line_in_a_test_file_passes(self):
        self.with_row()
        self.fx["diff"] += diff_file("src/lib/total.test.ts", added="expect(total()).toBe(formatMoney(1234));")
        self.assertPass()

    def test_money_line_in_a_test_dir_passes(self):
        self.with_row()
        self.fx["diff"] += diff_file("api/billing/__tests__/charge.ts", added="const cents = 990;")
        self.assertPass()

    def test_money_line_in_a_test_file_holds_with_no_test_sources_row(self):
        self.fx["diff"] += diff_file("src/lib/total.test.ts", added="expect(total()).toBe(formatMoney(1234));")
        self.assertHold(4)

    def test_money_line_in_a_test_file_holds_when_the_base_profile_has_no_row(self):
        self.with_row(base=False)
        self.fx["diff"] += diff_file("src/lib/total.test.ts", added="expect(total()).toBe(formatMoney(1234));")
        self.assertHold(4)

    def test_money_line_in_a_test_file_holds_when_the_local_profile_has_no_row(self):
        self.with_row(local=False)
        self.fx["diff"] += diff_file("src/lib/total.test.ts", added="expect(total()).toBe(formatMoney(1234));")
        self.assertHold(4)

    def test_a_test_sources_row_with_no_glob_exempts_nothing(self):
        self.with_row()
        self.local = self.local.replace("`**/*.test.ts` `**/__tests__/**`", "test files")
        self.fx["contents"][".claude/repo-profile.md?ref=develop"] = self.local
        self.fx["diff"] += diff_file("src/lib/total.test.ts", added="expect(total()).toBe(formatMoney(1234));")
        self.assertHold(4)

    def test_money_line_in_production_beside_a_test_still_holds(self):
        self.with_row()
        self.fx["diff"] += diff_file("src/lib/total.test.ts", added="expect(total()).toBe(formatMoney(1234));")
        self.fx["diff"] += diff_file("src/lib/total.ts", added="return formatMoney(sum);")
        out = self.assertHold(4)
        self.assertIn("src/lib/total.ts adds a money line", out)

    def test_a_test_file_the_money_row_names_still_holds(self):
        self.with_row()
        self.fx["diff"] += diff_file("src/lib/__tests__/money.ts", added="export const x = 1;")
        out = self.assertHold(4)
        self.assertIn("money file", out)

    def test_a_move_from_production_into_a_test_source_still_holds(self):
        self.with_row()
        self.fx["diff"] += ("diff --git a/src/pay.ts b/src/__tests__/pay.ts\nsimilarity index 90%\n"
                            "rename from src/pay.ts\nrename to src/__tests__/pay.ts\n"
                            "--- a/src/pay.ts\n+++ b/src/__tests__/pay.ts\n@@ -1 +1 @@\n-x\n+return cents * 2\n")
        self.assertHold(4)

    def test_a_protected_test_file_still_holds(self):
        self.with_row()
        self.fx["diff"] += diff_file(".claude/__tests__/gate.test.ts", added="x")
        out = self.assertHold(4)
        self.assertIn("merge-protected", out)


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

    def test_wait_budget_bounds_the_polls(self):
        # the gate must print its line inside adw-build §3.7's 600000 ms Bash timeout, whatever the poll counts
        self.env.update(ADW_GATE_POLL_SECONDS="0.2", ADW_GATE_BUDGET_SECONDS="0.5")
        self.fx["mergeable_seq"] = ["UNKNOWN", "MERGEABLE"]
        self.fx["checks"] = [{"name": "validate", "bucket": "pending"}]
        t0 = time.monotonic()
        out = self.assertHold(5)
        self.assertLess(time.monotonic() - t0, 2.0)
        self.assertIn("validate", out)


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

    def test_defect_text_saying_not_run_passes(self):
        # only the status line says the walk did not run; a row's own words never do
        self.result(rows="| D1 | polish | the banner did not run its fade | - | none |\n")
        self.assertPass()

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


    def test_defect_row_with_no_check_line_holds(self):
        # the refuter was skipped, or its lines were lost: a worth-fixing defect with no verdict
        self.result(rows="| D1 | worth-fixing | the total is wrong | code | fix |\n")
        self.assertHold(7)

    def test_overstated_to_polish_passes(self):
        self.result(rows="| D1 | worth-fixing | a label wraps | code | fix |\n", lines="polish: D1 — overstated\n")
        self.assertPass()

    def test_valid_line_as_a_list_item_holds(self):
        self.result(rows="| D1 | worth-fixing | the total is wrong | code | fix |\n", lines="- valid: D1 — image, spec, file:1\n")
        self.assertHold(7)

    def test_unconfirmed_fix_as_a_list_item_holds(self):
        self.result(lines="* fixed: D2 (walk 1) in abcdef1, unconfirmed\n")
        self.assertHold(7)

    def test_walk_line_with_no_devices_holds(self):
        self.result(first="PASS — 1/1 cases · walk 1 at 0123456 · 12m", rows="| G1 | - | ipad not runnable | runner | none |\n")
        self.assertHold(7)

    def test_the_word_devices_in_the_verdict_does_not_shadow_the_list(self):
        self.result(first="clean on all devices pass · walk 1 at 0123456 · devices iphone17,ipad · 12m",
                    rows="| G1 | - | ipad not runnable | runner | none |\n")
        self.assertHold(7)

    def test_a_result_line_starting_with_smoke_is_not_the_evidence_row(self):
        self.result(first="smoke clean · walk 1 at 0123456 · devices iphone17,ipad · 12m")
        self.set_body(result=RESULT.replace("PASS — 1/1 cases", "smoke clean"), evidence=EVIDENCE.replace("audit 0", "audit 1"))
        self.assertHold(7)


    def test_a_spaced_device_list_keeps_every_device(self):
        self.result(first="PASS — 1/1 cases · walk 1 at 0123456 · devices iphone17, ipad · 12m",
                    rows="| G1 | - | ipad not runnable | runner | none |\n")
        self.assertHold(7)

    def test_check_lines_with_other_list_markers_hold(self):
        for marker in ("+ ", "1. "):
            self.result(lines=marker + "fixed: D2 (walk 1) in abcdef1, unconfirmed\n")
            self.assertHold(7)

    def test_no_smoke_evidence_row_holds(self):
        self.set_body(evidence=EVIDENCE.replace(
            "smoke      walk 1 · 0 defects (0 blocking) · 0 gaps · valid 0 · refuted 0 · fixed 0 (0 unconfirmed) · cases 1/1 · audit 0 · 12m\n", ""))
        self.assertHold(7)

    def test_a_defect_row_without_a_leading_pipe_still_counts(self):
        self.result(rows="D1 | blocking | the save button does nothing | code | fix |\n")
        self.assertHold(7)

    def test_a_kept_fixed_line_does_not_shadow_a_later_refuted_line(self):
        self.result(rows="| D1 | worth-fixing | a label wraps | code | fix |\n",
                    lines="fixed: D1 (walk 1) in abcdef1\nrefuted: D1 — the spec does not ask for one line\n")
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

    def test_a_screens_line_that_is_not_a_row_holds(self):
        self.set_body(screens="## Screens\n- SCREEN-1 · Painel · iphone17, ipad\n- SCREEN-2 - Ajustes - iphone17\n")
        self.assertHold(8)

    def test_screens_none_on_pr_with_cases_takes_ui_paths_test(self):
        self.set_body(screens="## Screens\nScreens: none — the change is an API field no screen shows\n")
        self.fx["diff"] = diff_for(["api/x.ts", SPEC])
        self.assertPass()
        self.fx["diff"] = diff_for(["src/app.ts", SPEC])
        self.assertHold(9)


class TestSmokeNone(Gate):
    def smoke_none(self, names):
        self.set_body(result="", cases="Smoke: none — a backend field no user sees\n", screens="")
        self.fx["diff"] = diff_for(names)
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


class Trial(unittest.TestCase):
    """trial / discard against a temp bare remote: the base merged into the head in a detached tree."""

    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.env = dict(os.environ, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="t",
                        GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        self.origin = os.path.join(self.tmp, "origin.git")
        self.main = os.path.join(self.tmp, "App Repo")   # a space, on purpose
        self.other = os.path.join(self.tmp, "other")
        self.git("init", "-q", "--bare", "-b", "develop", self.origin, cwd=self.tmp)
        self.git("clone", "-q", self.origin, self.main, cwd=self.tmp)
        self.git("checkout", "-q", "-b", "develop")
        self.commit(self.main, {"a.txt": "a\n", "c.txt": "c\n"}, "base")
        self.git("push", "-q", "origin", "develop")
        self.git("checkout", "-q", "-b", "feat")
        self.commit(self.main, {"a.txt": "a head\n"}, "head")
        self.git("push", "-q", "origin", "feat")
        self.head = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "develop")
        self.git("clone", "-q", "-b", "develop", self.origin, self.other, cwd=self.tmp)
        self.tree = os.path.join(self.main, ".claude", "worktrees", "adw-trial-foo-pr7")

    def git(self, *args, cwd=None):
        p = subprocess.run(["git", *args], cwd=cwd or self.main, env=self.env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return p.stdout.strip()

    def commit(self, root, files, msg):
        for rel, text in files.items():
            path = os.path.join(root, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(text)
        self.git("add", "-A", cwd=root)
        self.git("commit", "-qm", msg, cwd=root)

    def move_base(self, files):
        self.commit(self.other, files, "base moves")
        self.git("push", "-q", "origin", "develop", cwd=self.other)
        return self.git("rev-parse", "HEAD", cwd=self.other)

    def gate(self, *args):
        p = subprocess.run([sys.executable, SCRIPT, *args], env=self.env, capture_output=True, text=True)
        return p.returncode, p.stdout.strip(), p.stderr

    def trial(self):
        return self.gate("trial", "--checkout", self.main, "--pr", "7", "--slug", "foo", "--base", "develop", "--head", self.head)

    def registered(self):
        return [l[len("worktree "):] for l in self.git("worktree", "list", "--porcelain").splitlines() if l.startswith("worktree ")]

    def test_unmoved_base(self):
        rc, out, err = self.trial()
        self.assertEqual((rc, out), (0, "base unmoved"), err)
        self.assertFalse(os.path.exists(self.tree))

    def test_moved_disjoint_files_gives_tree(self):
        tip = self.move_base({"c.txt": "c base\n"})
        rc, out, err = self.trial()
        self.assertEqual((rc, out), (0, "tree %s base %s" % (self.tree, tip)), err)
        with open(os.path.join(self.tree, "a.txt")) as f:
            self.assertEqual(f.read(), "a head\n")
        with open(os.path.join(self.tree, "c.txt")) as f:
            self.assertEqual(f.read(), "c base\n")
        self.assertEqual(self.git("rev-parse", "feat"), self.head)
        self.assertEqual(self.git("ls-remote", self.origin, "refs/heads/feat").split()[0], self.head)
        self.assertEqual(self.git("rev-parse", "--abbrev-ref", "HEAD", cwd=self.tree), "HEAD")   # detached

    def test_overlap_holds(self):
        self.move_base({"a.txt": "a base\n"})
        rc, out, err = self.trial()
        self.assertEqual((rc, out), (1, "hold 6 overlap: a.txt"), err)
        self.assertNotIn(self.tree, self.registered())

    def test_conflict_holds_and_leaves_no_worktree(self):
        # disjoint paths that still conflict: the base adds a file `d`, the head a directory `d/`
        self.git("checkout", "-q", "feat")
        self.commit(self.main, {"d/x.txt": "x\n"}, "head adds d/")
        self.git("push", "-q", "origin", "feat")
        self.head = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "develop")
        self.move_base({"d": "a file\n"})
        rc, out, err = self.trial()
        self.assertEqual(rc, 1, out + err)
        self.assertTrue(out.startswith("hold 6 conflict: "), out)
        self.assertNotIn(self.tree, self.registered())
        self.assertFalse(os.path.exists(self.tree))

    def test_discard_removes_tree(self):
        self.move_base({"c.txt": "c base\n"})
        self.assertEqual(self.trial()[0], 0)
        rc, out, err = self.gate("discard", "--checkout", self.main, "--tree", self.tree)
        self.assertEqual(rc, 0, out + err)
        self.assertNotIn(self.tree, self.registered())
        self.assertFalse(os.path.exists(self.tree))

    def test_clean_leftover_tree_is_replaced(self):
        # a run that died before Phase 5 left its trial tree: a clean one is removed and the trial runs again
        tip = self.move_base({"c.txt": "c base\n"})
        self.assertEqual(self.trial()[0], 0)
        rc, out, err = self.trial()
        self.assertEqual((rc, out), (0, "tree %s base %s" % (self.tree, tip)), err)

    def test_dirty_leftover_tree_is_a_gate_error(self):
        self.move_base({"c.txt": "c base\n"})
        self.assertEqual(self.trial()[0], 0)
        with open(os.path.join(self.tree, "a.txt"), "w") as f:
            f.write("edited after the merge\n")
        rc, out, err = self.trial()
        self.assertEqual(rc, 2, out + err)
        self.assertTrue(out.startswith("hold 0 gate error: "), out)
        self.assertIn(self.tree, self.registered())

    def test_discard_keeps_a_tree_with_other_changes(self):
        self.move_base({"c.txt": "c base\n"})
        self.assertEqual(self.trial()[0], 0)
        with open(os.path.join(self.tree, "a.txt"), "w") as f:
            f.write("edited after the merge\n")
        rc, out, err = self.gate("discard", "--checkout", self.main, "--tree", self.tree)
        self.assertEqual(rc, 1, out + err)
        self.assertIn(self.tree, self.registered())


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


class Merge(Gate):
    """`merge`: the gate, a sub-PR and the owner's word each merge only on their own checks."""

    def merge(self, *extra):
        with open(self.env["FAKE_GH_FIXTURE"], "w") as f:
            json.dump(self.fx, f)
        with open(self.local_profile, "w") as f:
            f.write(self.local)
        args = [sys.executable, SCRIPT, "merge", "--repo", "o/r", "--pr", "7", "--head", HEAD, *extra]
        p = subprocess.run(args, env=self.env, capture_output=True, text=True)
        return p.returncode, p.stdout.strip(), p.stderr

    def gh_calls(self):
        if not os.path.exists(self.env["FAKE_GH_LOG"]):
            return []
        with open(self.env["FAKE_GH_LOG"]) as f:
            return [json.loads(l) for l in f]

    def merges(self):
        return [c for c in self.gh_calls() if c[:2] == ["pr", "merge"]]

    def gate(self, *extra):
        return self.merge("--base", "develop", "--profile", self.local_profile, "--spec-path", SPEC, *extra)

    def owner(self, *extra):
        return self.merge("--owner", "--profile", self.local_profile, *extra)

    def sub(self, *extra):
        self.fx["view"]["baseRefName"] = "adw/x"
        return self.merge("--sub", "--slug", "x", *extra)


class TestMergeGateMode(Merge):
    def test_pass_merges_with_the_convention_and_the_head(self):
        rc, out, err = self.gate()
        self.assertEqual((rc, out), (0, "merged abcdef0"), err)
        self.assertEqual(self.merges(), [["pr", "merge", "7", "--repo", "o/r", "--squash", "--match-head-commit", HEAD]])

    def test_a_hold_never_merges(self):
        self.fx["view"]["labels"] = [{"name": "adw:hold"}]
        rc, out, _ = self.gate()
        self.assertEqual(rc, 1)
        self.assertTrue(out.startswith("hold 1 "), out)
        self.assertEqual(self.merges(), [])

    def test_base_other_than_the_intent_holds(self):
        rc, out, _ = self.merge("--base", "feature/x", "--profile", self.local_profile, "--spec-path", SPEC)
        self.assertTrue(out.startswith("hold 2 base changed"), out)
        self.assertEqual(self.merges(), [])

    def test_head_other_than_the_given_sha_holds(self):
        with open(self.env["FAKE_GH_FIXTURE"], "w") as f:
            json.dump(self.fx, f)
        with open(self.local_profile, "w") as f:
            f.write(self.local)
        p = subprocess.run([sys.executable, SCRIPT, "merge", "--repo", "o/r", "--pr", "7", "--head", OLD,
                            "--base", "develop", "--profile", self.local_profile, "--spec-path", SPEC],
                           env=self.env, capture_output=True, text=True)
        self.assertTrue(p.stdout.startswith("hold 3 head moved"), p.stdout)
        self.assertEqual(self.merges(), [])

    def test_flag_overrides_the_convention(self):
        rc, out, _ = self.gate("--flag", "merge")
        self.assertEqual(rc, 0, out)
        self.assertIn("--merge", self.merges()[0])

    def test_missing_spec_path_is_a_gate_error(self):
        rc, out, _ = self.merge("--base", "develop", "--profile", self.local_profile)
        self.assertEqual((rc, out), (2, "hold 0 gate error: merge needs --spec-path"))

    def test_short_head_is_a_gate_error(self):
        p = subprocess.run([sys.executable, SCRIPT, "merge", "--repo", "o/r", "--pr", "7", "--head", "0123456"],
                           env=self.env, capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stdout.strip()), (2, "hold 0 gate error: --head must be a full 40-character sha"))

    def test_failed_call_is_retried_once(self):
        self.fx["merge_fail"] = 1
        rc, out, err = self.gate()
        self.assertEqual((rc, out), (0, "merged abcdef0"), err)
        self.assertEqual(len(self.merges()), 2)

    def test_two_failed_calls_are_a_held_call(self):
        self.fx["merge_fail"] = 2
        rc, out, _ = self.gate()
        self.assertEqual(rc, 1)
        self.assertEqual(out, "hold call — GraphQL: Head branch was modified. Review and try the merge again.")

    def test_a_zero_exit_without_merged_is_a_held_call(self):
        self.fx["merge_noop"] = True
        rc, out, _ = self.gate()
        self.assertEqual((rc, out), (1, "hold call — the PR is OPEN after the merge call"))

    def test_a_read_back_that_fails_is_a_held_call_not_a_gate_error(self):
        self.fx["readback_fail"] = True
        rc, out, _ = self.gate()
        self.assertEqual(rc, 1, out)
        self.assertEqual(out, "hold call — the merge call exited 0, and the PR could not be read back: "
                              "check it before anything else")
        self.assertEqual(len(self.merges()), 1)

    def test_a_non_zero_exit_that_merged_is_merged(self):
        self.fx["merge_rc"] = 1
        rc, out, _ = self.gate()
        self.assertEqual((rc, out), (0, "merged abcdef0"))
        self.assertEqual(len(self.merges()), 1)


class TestMergeSubMode(Merge):
    def test_verified_head_merges_with_squash(self):
        self.local = profile().replace("| **merge convention** | squash |", "| **merge convention** | merge |")
        rc, out, err = self.sub()
        self.assertEqual((rc, out), (0, "merged abcdef0"), err)
        self.assertIn("--squash", self.merges()[0])

    def test_base_other_than_the_integration_branch_holds(self):
        rc, out, _ = self.merge("--sub", "--slug", "x")
        self.assertTrue(out.startswith("hold 2 the sub-PR's base develop is not adw/x"), out)
        self.assertEqual(self.merges(), [])

    def test_stale_verified_row_holds(self):
        self.fx["view"]["body"] = body(evidence=EVIDENCE.replace(HEAD, OLD))
        rc, out, _ = self.sub()
        self.assertTrue(out.startswith("hold 3 verified ffffff"), out)
        self.assertEqual(self.merges(), [])

    def test_no_verified_row_holds(self):
        self.fx["view"]["body"] = "no evidence"
        rc, out, _ = self.sub()
        self.assertEqual(out, "hold 3 the evidence block has no verified row")

    def test_a_blocked_sub_pr_is_carried(self):
        self.fx["view"]["labels"] = [{"name": "adw:blocked"}]
        rc, out, _ = self.sub()
        self.assertEqual((rc, out), (0, "merged abcdef0"))

    def test_missing_slug_is_a_gate_error(self):
        rc, out, _ = self.merge("--sub")
        self.assertEqual((rc, out), (2, "hold 0 gate error: merge --sub needs --slug"))


class TestMergeOwnerMode(Merge):
    def test_owner_merges_without_the_flag(self):
        self.fx["contents"][SPEC + "?ref=" + HEAD] = spec(merge="hold")
        self.fx["view"]["labels"] = [{"name": "adw:hold"}]
        rc, out, err = self.owner("--delete-branch")
        self.assertEqual((rc, out), (0, "merged abcdef0"), err)
        self.assertEqual(self.merges()[0][-1], "--delete-branch")

    def test_production_base_is_refused(self):
        self.fx["view"]["baseRefName"] = "main"
        self.fx["contents"][".claude/repo-profile.md?ref=main"] = profile()
        rc, out, _ = self.owner()
        self.assertEqual(out, "hold 2 the PR's base main is the production branch")
        self.assertEqual(self.merges(), [])

    def test_production_named_only_by_the_base_copy_is_refused(self):
        self.local = profile().replace("| **production branch** | `main` |\n", "")
        self.fx["view"]["baseRefName"] = "main"
        self.fx["contents"][".claude/repo-profile.md?ref=main"] = profile()
        rc, out, _ = self.owner()
        self.assertTrue(out.startswith("hold 2 the PR's base main"), out)

    def test_no_production_row_anywhere_holds(self):
        self.local = profile().replace("| **production branch** | `main` |\n", "")
        self.fx["contents"][".claude/repo-profile.md?ref=develop"] = self.local
        rc, out, _ = self.owner()
        self.assertTrue(out.startswith("hold 2 no copy of the profile"), out)

    def test_moved_head_holds(self):
        self.fx["view"]["headRefOid"] = OLD
        rc, out, _ = self.owner()
        self.assertTrue(out.startswith("hold 3 head moved"), out)
        self.assertEqual(self.merges(), [])

    def test_given_base_must_match(self):
        rc, out, _ = self.owner("--base", "feature/x")
        self.assertTrue(out.startswith("hold 2 base changed"), out)

    def test_delete_branch_is_owner_only(self):
        rc, out, _ = self.gate("--delete-branch")
        self.assertEqual(rc, 0, out)
        self.assertNotIn("--delete-branch", self.merges()[0])

    def test_sub_and_owner_together_is_a_bad_flag(self):
        rc, out, _ = self.merge("--sub", "--owner", "--slug", "x")
        self.assertEqual(rc, 2)
        self.assertTrue(out.startswith("hold 0 gate error:"), out)
