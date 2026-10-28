"""Tests for adw_analyze.pricing and adw_analyze.transcripts. Run: cd scripts && python3 -m unittest -v test_adw_analyze_transcripts"""
import unittest

from adw_analyze import pricing
from adw_analyze.transcripts import read_session
from adw_analyze.testkit import (TmpCase, assistant, system, tool_result, tool_use, usage, user_prompt,
                                 write_session, write_subagent)

M = 1_000_000
GATES = {"gate 4": r"testDebugUnitTest|allTests"}


def cost(model, **u):
    return pricing.message_cost(pricing.Usage(model=model, ts="", **{**dict(input=0, output=0, cache_read=0,
                                                                      cache_write_5m=0, cache_write_1h=0), **u}))


class Prices(unittest.TestCase):
    def test_prices(self):
        self.assertAlmostEqual(cost("claude-opus-5-5", input=M), 4.0)
        self.assertAlmostEqual(cost("claude-opus-5-5", output=M), 20.0)
        self.assertAlmostEqual(cost("claude-opus-5-5", cache_read=M), 0.20)
        self.assertAlmostEqual(cost("claude-opus-5-5", cache_write_5m=M), 5.0)
        self.assertAlmostEqual(cost("claude-opus-5-5", cache_write_1h=M), 8.0)
        self.assertAlmostEqual(cost("claude-sonnet-5-5", output=M), 10.0)
        self.assertEqual(pricing.PRICES_AS_OF, "2026-10-22")


class Parse(TmpCase):
    def session(self, records, sid="s1"):
        self.projects = self.mkdir("projects")
        return read_session(write_session(self.projects, "-x-app", sid, records), GATES)

    def test_usage_deduped_by_message_id(self):
        s = self.session([assistant("2026-10-01T10:00:00Z", "m1", usage_=usage(output_tokens=50)),
                          assistant("2026-10-01T10:00:01Z", "m1", usage_=usage(output_tokens=100))])
        self.assertEqual(list(s.usage), ["m1"])
        self.assertEqual(s.usage["m1"].output, 100)

    def test_cache_writes_split(self):
        s = self.session([
            assistant("2026-10-01T10:00:00Z", "m1", usage_=usage(cache_creation_input_tokens=300,
                      cache_creation={"ephemeral_5m_input_tokens": 100, "ephemeral_1h_input_tokens": 200})),
            assistant("2026-10-01T10:00:01Z", "m2", usage_=usage(cache_creation_input_tokens=70))])
        self.assertEqual((s.usage["m1"].cache_write_5m, s.usage["m1"].cache_write_1h), (100, 200))
        self.assertEqual((s.usage["m2"].cache_write_5m, s.usage["m2"].cache_write_1h), (70, 0))

    def test_unknown_model_costs_zero_and_is_counted(self):
        s = self.session([assistant("2026-10-01T10:00:00Z", "m1", model="gpt-9", usage_=usage(output_tokens=M)),
                          assistant("2026-10-01T10:00:01Z", "m2", model="<synthetic>")])
        self.assertEqual(s.cost, 0.0)
        self.assertEqual(s.unknown_models, 1)
        self.assertNotIn("m2", s.usage)

    def test_compaction_kinds(self):
        s = self.session([
            system("2026-10-01T10:00:00Z", "compact_boundary", compactMetadata={"trigger": "auto"}),
            system("2026-10-01T10:00:05Z", "informational", content="Compacted while idle to save context"),
            system("2026-10-01T11:00:00Z", "compact_boundary", compactMetadata={"trigger": "auto"}),
            system("2026-10-01T12:00:00Z", "compact_boundary", compactMetadata={"trigger": "manual"})])
        self.assertEqual([k for _, k in s.compactions], ["idle", "limit", "manual"])

    def test_timing_ignores_other_records(self):
        s = self.session([user_prompt("2026-10-01T10:00:00Z"), assistant("2026-10-01T10:30:00Z", "m1"),
                          system("2026-10-01T15:00:00Z", "informational", content="Remote Control disconnected"),
                          {"type": "pr-link", "timestamp": "2026-10-01T16:00:00Z", "prNumber": 5, "prRepository": "o/r"}])
        self.assertEqual((s.first_ts, s.last_ts), ("2026-10-01T10:00:00Z", "2026-10-01T10:30:00Z"))

    def test_human_prompts_and_interrupts(self):
        s = self.session([
            assistant("2026-10-01T10:00:00Z", "m1", tools=[tool_use("t1", "Bash", command="ls")]),
            tool_result("2026-10-01T10:00:02Z", "t1"),
            user_prompt("2026-10-01T10:05:00Z"),
            user_prompt("2026-10-01T10:06:00Z", isMeta=True),
            {"type": "user", "timestamp": "2026-10-01T10:07:00Z", "message": {"content": "[Request interrupted by user]"}}])
        self.assertEqual(s.human_prompts, [("2026-10-01T10:05:00Z", "2026-10-01T10:00:00Z")])
        self.assertEqual(s.interrupts, ["2026-10-01T10:07:00Z"])

    def test_denial_sources(self):
        msgs = ["The user doesn't want to proceed with this tool use.",
                "Permission for this action has been denied by the Claude Code auto mode classifier.",
                "The classifier gave no verdict.", "Blocked by the built-in Claude Code safety check.",
                "PreToolUse:Bash hook error: Blocked by hook"]
        recs = []
        for i, m in enumerate(msgs):
            recs.append(assistant(f"2026-10-01T10:00:0{i}Z", f"m{i}", tools=[tool_use(f"t{i}", "Bash", command="x")]))
            recs.append(tool_result(f"2026-10-01T10:00:0{i}Z", f"t{i}", m, is_error=True))
        recs.append({"type": "user", "timestamp": "2026-10-01T10:01:00Z", "message": {"content": "x"},
                     "permissionDecision": {"decision": "reject", "source": "config"}})
        s = self.session(recs)
        self.assertEqual(dict(s.denials), {"user_rejected": 1, "auto_mode_classifier": 1, "classifier_no_verdict": 1,
                                           "builtin_safety": 1, "hook_block": 1, "permissionDecision:config": 1})
        self.assertEqual(s.tool_errors["Bash"], 5)
        self.assertEqual(sum(s.tool_calls.values()), 5)

    def test_permission_decision_and_marker_count_once(self):
        s = self.session([
            assistant("2026-10-01T10:00:00Z", "m1", tools=[tool_use("t1", "Bash", command="x")]),
            tool_result("2026-10-01T10:00:01Z", "t1", "Permission for this action has been denied by the Claude Code auto mode classifier.",
                        is_error=True, permissionDecision={"decision": "reject", "source": "classifier"})])
        self.assertEqual(dict(s.denials), {"auto_mode_classifier": 1})

    def test_gate_calls(self):
        s = self.session([
            assistant("2026-10-01T10:00:00Z", "m1", tools=[tool_use("t1", "Bash", command="./gradlew testDebugUnitTest")]),
            tool_result("2026-10-01T10:01:30Z", "t1", "BUILD SUCCESSFUL"),
            assistant("2026-10-01T10:02:00Z", "m2", tools=[tool_use("t2", "Bash", command="./gradlew allTests", run_in_background=True)]),
            tool_result("2026-10-01T10:02:01Z", "t2", "started")])
        self.assertEqual(s.gate_calls, [("gate 4", "2026-10-01T10:00:00Z", 90.0)])
        self.assertEqual(s.background_gate_calls, 1)

    def test_bad_lines(self):
        s = self.session([user_prompt("2026-10-01T10:00:00Z"), assistant("2026-10-01T10:00:01Z", "m1"),
                          '{"type": "assistant", "timestamp": "2026-10-01T10:00:0'])
        self.assertEqual(s.bad_lines, 1)
        self.assertEqual(len(s.usage), 1)

    def test_known_and_unknown_types(self):
        s = self.session([{"type": "cost-state", "totalCostUSD": 99}, {"type": "brand-new-record"}])
        self.assertEqual(dict(s.unknown_types), {"brand-new-record": 1})
        self.assertEqual(s.cost, 0.0)

    def test_pr_links_and_captures(self):
        s = self.session([
            user_prompt("2026-10-01T10:00:00Z", "/adw-build panel", gitBranch="adw/panel",
                        cwd="/r/.claude/worktrees/adw-panel-u03"),
            assistant("2026-10-01T10:00:01Z", "m1", tools=[tool_use("a1", "Agent", prompt="work in .claude/worktrees/adw-other-u01")]),
            {"type": "pr-link", "timestamp": "2026-10-01T10:00:02Z", "prNumber": 41, "prRepository": "o/app"}])
        self.assertEqual(s.pr_links, [("o/app", 41)])
        self.assertEqual(s.captures["panel"], 2)          # branch adw/panel + /adw-build arg
        self.assertEqual(s.captures["adw-panel-u03"], 1)  # worktree in cwd
        self.assertEqual(dict(s.dispatches["a1"]), {"adw-other-u01": 1})
        self.assertNotIn("adw-other-u01", s.captures)

    def test_analyzer_session_flagged(self):
        s = self.session([assistant("2026-10-01T10:00:00Z", "m1", tools=[
            tool_use("t1", "Bash", command="python3 scripts/adw-analyze.py --reports x")])])
        self.assertTrue(s.ran_analyzer)

    def test_subagent_meta(self):
        projects = self.mkdir("projects")
        p = write_subagent(projects, "-x-app", "s1", "abc", [assistant("2026-10-01T10:00:00Z", "m1")], "toolu_1",
                           parent_agent_id="def", worktreeBranch="adw/panel-u02")
        s = read_session(p, GATES)
        self.assertEqual((s.session_id, s.agent_id, s.tool_use_id, s.parent_agent_id), ("s1", "abc", "toolu_1", "def"))
        self.assertEqual(s.captures["panel-u02"], 1)
        self.assertEqual(s.project_dir, "-x-app")

    def test_peak_context(self):
        s = self.session([assistant("2026-10-01T10:00:00Z", "m1", usage_=usage(input_tokens=1000, cache_read_input_tokens=250_000,
                                                                                cache_creation_input_tokens=500))])
        self.assertEqual(s.peak_context, 251_500)

    def test_no_text_kept(self):
        marker = "SECRET-MARKER-123 the quick brown fox jumps over the lazy dog"
        s = self.session([user_prompt("2026-10-01T10:00:00Z", marker),
                          assistant("2026-10-01T10:00:01Z", "m1", text=marker,
                                    tools=[tool_use("t1", "Bash", command="echo " + marker)]),
                          tool_result("2026-10-01T10:00:02Z", "t1", marker)])
        self.assertNotIn("SECRET-MARKER", repr(s))


if __name__ == "__main__":
    unittest.main()
