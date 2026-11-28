"""Tests for install/hooks/adw-guard.py, the PreToolUse hook. Run: cd scripts && python3 -m unittest -v test_adw_guard"""
import importlib.util
import json
import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "..", "install", "hooks", "adw-guard.py")
spec = importlib.util.spec_from_file_location("adw_guard", HOOK)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

DENIED = {
    guard.STASH: [
        "git stash", "git stash pop", "git -C /a/b stash push -m x", "git -C '/a b/c' stash list",
        "/usr/bin/git stash", "cd x && git stash", "git status; git stash", "git status\ngit stash",
        "echo $(git stash)", 'echo "$(git stash)"', "echo `git stash`", "bash -c 'git stash'",
        "zsh -lc \"git stash\"", "rtk git stash", "rtk proxy git stash", "FOO=1 git stash",
        "env -u X GIT_DIR=.git git stash", "sudo -u me git stash", "git -c a=b --no-pager stash",
        "eval git stash", "x=$(echo (a)); git stash", "true | xargs -n 1 git stash",
        "echo 'unclosed git stash", "! git stash", "{ git stash; }", "while true; do git stash; break; done",
        "if git diff --quiet; then git stash; fi", "if true; then :; else git stash; fi",
    ],
    guard.MERGE: [
        "gh pr merge 3 --squash", "gh pr merge 3 --squash --match-head-commit abc", "gh -R o/r pr merge 3",
        "gh pr --repo o/r merge 3", "cd /x && gh pr merge 3", "gh api -X PUT repos/o/r/pulls/3/merge",
        "gh api graphql -f query='mutation { mergePullRequest(input: {}) { clientMutationId } }'",
        "bash -c 'gh pr merge 3'", "for n in 3 4; do gh pr merge $n --squash; done",
        "gh pr view 3 && { gh pr merge 3; }",
    ],
    guard.HERDR: [
        "herdr agent prompt w1:p2 approve", "herdr agent send-keys w1:p2 Enter",
        "herdr pane send-text w1:p2 hi", "herdr pane send-keys w1:p2 C-c", "herdr pane run w1:p2 'ls'",
        "herdr --session s pane run w1 x",
    ],
}
ALLOWED = [
    'grep -n "gh pr merge" commands/*.md', "rg 'herdr agent prompt' commands", "git log --grep stash",
    "git commit -m 'never git stash'", 'git commit -m "no git stash, no gh pr merge"', "echo git stash",
    "gh pr view 3", "gh pr checks 3", "gh api repos/o/r/pulls/3", "herdr agent get w1:p2",
    "herdr agent read w1:p2 --lines 60", "herdr agent wait x --timeout 540000", "herdr pane read w1 --lines 15",
    "python3 adw-merge-gate.py merge --sub --pr 3", "python3 \"$DISPATCH\" prompt w1:p2 'rebase'",
    "git stash-helper", "ls # git stash", "git status && git diff",
    "cat > f.md <<'EOF'\nNever `git stash` here\ngh pr merge 1\nEOF\ngit add f.md",
    "cat <<-EOF\n\tgit stash\n\tEOF\necho done",
    "git add -A && git commit -m \"$(cat <<'EOF'\nfix: no git stash\nEOF\n)\"",
    "echo 'unclosed", "",
    "git commit -m \"$(cat <<'EOF'\nDon't run git stash here\nEOF\n)\"",
    "gh pr edit 12 --body \"$(cat <<'EOF'\nThe PR's base moved.\ndefault: run ! gh pr merge 12 --squash\nEOF\n)\"",
    "gh pr comment 12 --body \"$(cat <<-EOF\n\tit's fine: herdr agent prompt is denied\n\tEOF\n)\"",
    "for f in a b; do echo \"$f\"; done", "if [ -f x ]; then cat x; fi",
]


class Commands(unittest.TestCase):
    def test_denied(self):
        for why, cmds in DENIED.items():
            for cmd in cmds:
                with self.subTest(cmd=cmd):
                    self.assertEqual(guard.check_command(cmd), why)

    def test_allowed(self):
        for cmd in ALLOWED:
            with self.subTest(cmd=cmd):
                self.assertIsNone(guard.check_command(cmd))


class Hook(unittest.TestCase):
    def run_hook(self, event):
        p = subprocess.run([sys.executable, HOOK], input=event if isinstance(event, str) else json.dumps(event),
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout) if p.stdout.strip() else None

    def test_a_denied_command_prints_a_deny_decision(self):
        out = self.run_hook({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                             "tool_input": {"command": "git stash"}})
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertEqual(out["hookSpecificOutput"]["permissionDecisionReason"], guard.STASH)

    def test_an_allowed_command_prints_nothing(self):
        self.assertIsNone(self.run_hook({"tool_name": "Bash", "tool_input": {"command": "git status"}}))

    def test_enter_worktree_is_denied_in_a_subagent_only(self):
        out = self.run_hook({"tool_name": "EnterWorktree", "agent_id": "a1", "agent_type": "general-purpose",
                             "tool_input": {"name": "x"}})
        self.assertEqual(out["hookSpecificOutput"]["permissionDecisionReason"], guard.WORKTREE)
        self.assertIsNone(self.run_hook({"tool_name": "EnterWorktree", "agent_id": None, "tool_input": {}}))

    def test_other_tools_and_bad_input_pass(self):
        self.assertIsNone(self.run_hook({"tool_name": "Read", "tool_input": {"file_path": "/x"}}))
        self.assertIsNone(self.run_hook({"tool_name": "Bash", "tool_input": {}}))
        self.assertIsNone(self.run_hook("not json"))
        self.assertIsNone(self.run_hook("[]"))


if __name__ == "__main__":
    unittest.main()
