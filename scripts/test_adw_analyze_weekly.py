"""Tests for adw-analyze-weekly.sh against scratch repos and fake gh, claude, launchctl and reader.
Run: cd scripts && python3 -m unittest -v test_adw_analyze_weekly"""
import os
import shutil
import stat
import subprocess
from datetime import datetime, timezone

from adw_analyze.testkit import TmpCase

HERE = os.path.dirname(os.path.abspath(__file__))
WRAPPER = os.path.join(HERE, "adw-analyze-weekly.sh")
PROMPT = os.path.join(os.path.dirname(HERE), ".claude", "skills", "adw-analyze", "critical-pass.md")

FAKE_READER = r'''#!/bin/bash
echo "python3 $*" >> "$STUB_LOG"
reports=""; prev=""
for a in "$@"; do [ "$prev" = "--reports" ] && reports="$a"; prev="$a"; done
case " $* " in
  *" --scan "*) echo "leak scan: stub"; exit "${FAKE_SCAN_EXIT:-0}";;
  *" --transcript-dirs "*) echo "$FAKE_TDIR"; exit 0;;
esac
[ "${FAKE_READER_EXIT:-0}" = 0 ] || exit "$FAKE_READER_EXIT"
d="$reports/${FAKE_READER_DATE:-$(date -u +%Y-%m-%d)}"
[ -e "$d" ] && { echo "$d exists" >&2; exit 2; }
mkdir -p "$d"
printf '# ADW analysis\n\n## Critical pass\n\ncritical pass: pending\n' > "$d/report.md"
printf 'Verdicts: none\n\ncritical pass: pending\nleak scan: pending\n' > "$d/issue.md"
echo '{"schema": 1}' > "$d/metrics.json"
echo "$d"
'''
FAKE_CLAUDE = r'''#!/bin/bash
echo "claude $*" >> "$STUB_LOG"
echo "claude-stderr-marker" >&2
out=""
for a in "$@"; do case "$a" in "Edit("*) out="${a#Edit(}"; out="${out%)}";; esac; done
[ -n "${FAKE_CLAUDE_PARTIAL:-}" ] && printf -- '- partial finding\n' > "$out"
[ -n "${FAKE_CLAUDE_SLEEP:-}" ] && sleep "$FAKE_CLAUDE_SLEEP"
[ -n "${FAKE_CLAUDE_SILENT:-}" ] && exit 1
printf -- '- `cost.total_usd.v1` moved +40%%: fewer intents, not a regression.\n' > "$out"
'''
FAKE_LAUNCHCTL = '#!/bin/bash\necho "launchctl $*" >> "$STUB_LOG"\n'


class Weekly(TmpCase):
    def setUp(self):
        super().setUp()
        self.date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.stubs = self.mkdir("stubs")
        for name, body in (("python3", FAKE_READER), ("claude", FAKE_CLAUDE), ("launchctl", FAKE_LAUNCHCTL)):
            p = os.path.join(self.stubs, name)
            with open(p, "w") as f:
                f.write(body)
            os.chmod(p, os.stat(p).st_mode | stat.S_IEXEC)
        self.home = self.mkdir("home")
        self.adw_origin = self.bare("adw-origin.git")
        self.adw = self.git_repo("adw", remote=self.adw_origin)
        for src, rel in ((WRAPPER, "scripts/adw-analyze-weekly.sh"), (PROMPT, ".claude/skills/adw-analyze/critical-pass.md")):
            os.makedirs(os.path.dirname(os.path.join(self.adw, rel)), exist_ok=True)
            shutil.copy(src, os.path.join(self.adw, rel))
        self.commit_push(self.adw)
        self.reports_origin = self.bare("reports-origin.git")
        self.reports = self.git_repo("reports", remote=self.reports_origin)
        self.write_json(os.path.join(self.reports, "sources.json"), {"schema": 1, "repos": []})
        self.commit_push(self.reports)

    def bare(self, rel):
        d = os.path.join(self.tmp, rel)
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", d], check=True)
        return d

    def commit_push(self, repo):
        self.git("add", ".", cwd=repo)
        self.git("commit", "-q", "-m", "init", cwd=repo)
        self.git("push", "-q", "origin", "main", cwd=repo)

    def env(self, **extra):
        e = {**os.environ, **self.gh.env(), "HOME": self.home, "STUB_LOG": os.path.join(self.tmp, "stub.log"),
             "ADW_ANALYSIS_DIR": self.reports, "ADW_REPO": self.adw, "ADW_WEEKLY_WORKTREE": os.path.join(self.tmp, "adw weekly"),
             "ADW_WEEKLY_PATH": f"{self.stubs}:{self.gh.bin}:/usr/bin:/bin", "ADW_ANALYSIS_SLUG": "o/adw-analysis",
             "FAKE_TDIR": os.path.join(self.tmp, "projects dir", "-app"),
             "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        e.pop("ADW_WEEKLY_REEXEC", None)
        e.update(extra)
        return e

    def run_wrapper(self, mode="run", **extra):
        return subprocess.run(["bash", os.path.join(self.adw, "scripts", "adw-analyze-weekly.sh"), mode],
                              capture_output=True, text=True, env=self.env(**extra))

    def pushed(self):
        return subprocess.run(["git", "--git-dir", self.reports_origin, "log", "--format=%s", "main"],
                              capture_output=True, text=True).stdout.split("\n")[0]

    def issues(self):
        return [c[c.index("--title") + 1] for c in self.gh.calls() if c[:2] == ["issue", "create"]]

    def report(self):
        with open(os.path.join(self.reports, self.date, "report.md")) as f:
            return f.read()

    def test_happy_path_commits_pushes_and_opens_issue(self):
        r = self.run_wrapper()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.pushed(), f"report {self.date}")
        self.assertEqual(self.issues(), [f"ADW analysis {self.date}"])
        self.assertIn("fewer intents", self.report())
        self.assertNotIn("critical pass: pending", self.report())
        with open(os.path.join(self.reports, self.date, "issue.md")) as f:
            self.assertIn("leak scan: clean", f.read())
        with open(os.path.join(self.tmp, "stub.log")) as f:
            log = f.read()
        self.assertIn("--model sonnet", log)
        self.assertIn("--permission-mode dontAsk", log)
        self.assertIn("--tools Read Grep Glob Edit Write", log)
        self.assertIn("--strict-mcp-config", log)
        tdir = os.path.join(self.tmp, "projects dir", "-app")
        self.assertIn("--add-dir " + tdir, log)
        self.assertIn(f"--allowedTools Read(./**) Read(/{tdir}/**) Edit({self.date}/critical-pass.md) --disallowedTools", log)
        self.assertIn(f"report: {self.reports}/{self.date}/report.md", r.stdout)
        self.assertNotIn("--add-dir " + os.path.join(self.home, ".claude", "projects") + " ", log)
        self.assertIn("claude-stderr-marker", r.stderr)
        self.assertTrue(os.path.isdir(os.path.join(self.tmp, "adw weekly")))
        with open(os.path.join(self.reports, self.date, "issue.md")) as f:
            self.assertIn("critical pass: ok", f.read())

    def test_default_path_finds_claude(self):
        with open(WRAPPER) as f:
            self.assertIn('$HOME/.local/bin', next(line for line in f if line.startswith("ADW_WEEKLY_PATH=")))

    def test_hung_critical_pass_is_cut_off(self):
        import time
        t0 = time.time()
        r = self.run_wrapper(FAKE_CLAUDE_SLEEP="30", ADW_CRITICAL_TIMEOUT="2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertLess(time.time() - t0, 20)
        self.assertIn("critical pass: timed out", self.report())

    def test_a_timed_out_pass_is_not_ok_even_with_a_partial_file(self):
        r = self.run_wrapper(FAKE_CLAUDE_PARTIAL="1", FAKE_CLAUDE_SLEEP="30", ADW_CRITICAL_TIMEOUT="2")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("critical pass: timed out", self.report())
        self.assertNotIn("partial finding", self.report())
        with open(os.path.join(self.reports, self.date, "issue.md")) as f:
            self.assertIn("critical pass: timed out", f.read())

    def test_a_dry_run_does_not_block_a_real_run_that_day(self):
        self.assertEqual(self.run_wrapper("--dry-run").returncode, 0)
        r = self.run_wrapper()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.pushed(), f"report {self.date}")
        self.assertEqual(self.issues(), [f"ADW analysis {self.date}"])

    def test_a_committed_report_still_blocks_a_second_run(self):
        self.assertEqual(self.run_wrapper().returncode, 0)
        r = self.run_wrapper()
        self.assertNotEqual(r.returncode, 0)
        self.assertTrue(os.path.exists(os.path.join(self.reports, self.date, "report.md")))
        self.assertEqual(self.issues()[-1], f"ADW analysis {self.date} failed at reader")

    def test_the_folder_is_the_one_the_reader_wrote(self):
        r = self.run_wrapper(FAKE_READER_DATE="2099-01-01")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.pushed(), "report 2099-01-01")
        with open(os.path.join(self.reports, "2099-01-01", "report.md")) as f:
            self.assertIn("fewer intents", f.read())

    def test_missing_script_on_the_ref_opens_an_issue(self):
        self.git("rm", "-q", "scripts/adw-analyze-weekly.sh", cwd=self.adw)
        self.git("commit", "-q", "-m", "drop", cwd=self.adw)
        self.git("push", "-q", "origin", "main", cwd=self.adw)
        runner = os.path.join(self.tmp, "runner.sh")
        shutil.copy(WRAPPER, runner)
        r = subprocess.run(["bash", runner, "run"], capture_output=True, text=True, env=self.env())
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(self.issues(), [f"ADW analysis {self.date} failed at re-exec"])

    def test_a_branch_can_be_dry_run(self):
        self.git("checkout", "-q", "-b", "feature", cwd=self.adw)
        self.git("push", "-q", "origin", "feature", cwd=self.adw)
        self.git("checkout", "-q", "main", cwd=self.adw)
        self.git("rm", "-q", "scripts/adw-analyze-weekly.sh", cwd=self.adw)
        self.git("commit", "-q", "-m", "drop", cwd=self.adw)
        self.git("push", "-q", "origin", "main", cwd=self.adw)
        runner = os.path.join(self.tmp, "runner.sh")
        shutil.copy(WRAPPER, runner)
        r = subprocess.run(["bash", runner, "--dry-run"], capture_output=True, text=True,
                           env=self.env(ADW_WEEKLY_REF="origin/feature"))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_failure_after_the_reader_removes_the_uncommitted_folder(self):
        r = self.run_wrapper(FAKE_SCAN_EXIT="1")
        self.assertEqual(r.returncode, 1)
        self.assertFalse(os.path.exists(os.path.join(self.reports, self.date)))
        self.assertEqual(self.issues(), [f"ADW analysis {self.date} failed at leak scan"])

    def test_missing_critical_pass_is_marked_and_still_committed(self):
        r = self.run_wrapper(FAKE_CLAUDE_SILENT="1")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("critical pass: missing", self.report())
        self.assertEqual(self.pushed(), f"report {self.date}")
        with open(os.path.join(self.reports, self.date, "issue.md")) as f:
            self.assertIn("critical pass: missing", f.read())

    def test_scan_hit_deletes_folder_and_opens_failure_issue(self):
        r = self.run_wrapper(FAKE_SCAN_EXIT="4")
        self.assertEqual(r.returncode, 1)
        self.assertFalse(os.path.exists(os.path.join(self.reports, self.date)))
        self.assertEqual(self.issues(), [f"ADW analysis {self.date} failed at leak scan"])
        self.assertEqual(self.pushed(), "init")

    def test_reader_failure_opens_failure_issue(self):
        r = self.run_wrapper(FAKE_READER_EXIT="1")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(self.issues(), [f"ADW analysis {self.date} failed at reader"])

    def test_dry_run_pushes_nothing(self):
        r = self.run_wrapper("--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.pushed(), "init")
        self.assertEqual(self.issues(), [])
        self.assertIn("would open issue", r.stdout)
        self.assertIn("fewer intents", self.report())
        local = subprocess.run(["git", "-C", self.reports, "log", "--format=%s"], capture_output=True, text=True).stdout
        self.assertEqual(local.split(), ["init"])

    def test_install_and_uninstall(self):
        r = self.run_wrapper("--install")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        plist = os.path.join(self.home, "Library", "LaunchAgents", "dev.adw.analyze-weekly.plist")
        with open(plist) as f:
            text = f.read()
        self.assertIn("<key>Weekday</key>\n\t\t<integer>1</integer>", text)
        self.assertIn(os.path.join(self.tmp, "adw weekly", "scripts", "adw-analyze-weekly.sh"), text)
        self.assertEqual(subprocess.run(["plutil", "-lint", plist], capture_output=True).returncode, 0)
        r = self.run_wrapper("--uninstall")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(plist))
        with open(os.path.join(self.tmp, "stub.log")) as f:
            log = f.read()
        self.assertIn("launchctl bootstrap gui/", log)
        self.assertIn("launchctl bootout gui/", log)
        self.assertEqual(self.issues(), [])
