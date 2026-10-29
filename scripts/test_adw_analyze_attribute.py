"""Tests for adw_analyze.attribute. Run: cd scripts && python3 -m unittest -v test_adw_analyze_attribute"""
import collections
import unittest

from adw_analyze.attribute import attribute_all, attribute_session, normalize
from adw_analyze.transcripts import SessionFacts

KNOWN = {"panel", "panel-shift-form", "x", "y"}
REPO = "o/app"
PRS = {41: "x", 42: "y"}


def main(sid="s1", captures=None, pr_links=(), dispatches=None):
    return SessionFacts(path=f"/p/{sid}.jsonl", project_dir="-p", session_id=sid,
                        captures=collections.Counter(captures or {}), pr_links=list(pr_links),
                        dispatches={k: collections.Counter(v) for k, v in (dispatches or {}).items()})


def sub(agent_id, sid="s1", tool_use_id=None, parent=None, captures=None, dispatches=None):
    s = main(sid, captures, dispatches=dispatches)
    s.path = f"/p/{sid}/subagents/agent-{agent_id}.jsonl"
    s.agent_id, s.tool_use_id, s.parent_agent_id = agent_id, tool_use_id, parent
    return s


class Normalize(unittest.TestCase):
    def test_longest_slug_first(self):
        self.assertEqual(normalize("panel-shift-form", KNOWN), "panel-shift-form")
        self.assertEqual(normalize("panel-shift-form-u02", KNOWN), "panel-shift-form")
        self.assertEqual(normalize("panel-extra", KNOWN), "panel")

    def test_unit_and_close_names(self):
        for c in ("adw-panel-u03", "adw-panel-u02+u03", "adw-close-panel",
                  "pr-ready-panel-close-v2", "pr-ready-panel-u01"):
            self.assertEqual(normalize(c, KNOWN), "panel", c)

    def test_unknown_is_none(self):
        self.assertIsNone(normalize("something-else", KNOWN))


class Main(unittest.TestCase):
    def test_longest_slug_wins_the_count(self):
        s = main(captures={"panel-shift-form": 25})
        self.assertEqual(attribute_session(s, KNOWN, PRS, REPO), "panel-shift-form")

    def test_threshold_19_hits_is_none(self):
        self.assertIsNone(attribute_session(main(captures={"x": 19}), KNOWN, PRS, REPO))
        self.assertEqual(attribute_session(main(captures={"x": 20}), KNOWN, PRS, REPO), "x")

    def test_ratio_below_3x_is_none(self):
        self.assertIsNone(attribute_session(main(captures={"x": 30, "y": 12}), KNOWN, PRS, REPO))
        self.assertEqual(attribute_session(main(captures={"x": 36, "y": 12}), KNOWN, PRS, REPO), "x")

    def test_pr_link_overrides_counts(self):
        s = main(captures={"y": 40}, pr_links=[(REPO, 41)])
        self.assertEqual(attribute_session(s, KNOWN, PRS, REPO), "x")

    def test_release_and_other_repo_links_ignored(self):
        s = main(captures={"y": 40}, pr_links=[(REPO, 7), ("o/other", 41)])
        self.assertEqual(attribute_session(s, KNOWN, PRS, REPO), "y")

    def test_links_to_two_slugs_fall_back_to_counts(self):
        s = main(captures={"y": 40}, pr_links=[(REPO, 41), (REPO, 42)])
        self.assertEqual(attribute_session(s, KNOWN, PRS, REPO), "y")


class Subagents(unittest.TestCase):
    def test_subagent_from_dispatch_prompt(self):
        m = main(captures={"x": 50}, dispatches={"t1": {"adw-panel-u03": 1}})
        a = sub("a1", tool_use_id="t1")
        got = attribute_all([m, a], KNOWN, PRS, REPO)
        self.assertEqual(got[a.path], "panel")
        self.assertEqual(got[m.path], "x")

    def test_subagent_inherits_parent(self):
        m = main(captures={"x": 50}, dispatches={"t1": {}})
        a = sub("a1", tool_use_id="t1", dispatches={"t2": {}})
        b = sub("b2", tool_use_id="t2", parent="a1")
        got = attribute_all([b, a, m], KNOWN, PRS, REPO)
        self.assertEqual((got[a.path], got[b.path]), ("x", "x"))

    def test_depth_two_uses_the_parent_subagents_dispatch(self):
        m = main(captures={"x": 50})
        a = sub("a1", tool_use_id="t1", dispatches={"t2": {"adw-y-u01": 1}})
        b = sub("b2", tool_use_id="t2", parent="a1")
        self.assertEqual(attribute_all([m, a, b], KNOWN, PRS, REPO)[b.path], "y")

    def test_own_worktree_capture_when_prompt_has_none(self):
        m = main(captures={"x": 50}, dispatches={"t1": {}})
        a = sub("a1", tool_use_id="t1", captures={"panel-u02": 1})
        self.assertEqual(attribute_all([m, a], KNOWN, PRS, REPO)[a.path], "panel")


if __name__ == "__main__":
    unittest.main()
