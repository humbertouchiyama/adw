"""Tests for adw_analyze.facts and adw_analyze.metrics. Run: cd scripts && python3 -m unittest -v test_adw_analyze_metrics"""
import collections
import os
import unittest
from types import SimpleNamespace
from unittest import mock

from adw_analyze import facts as F
from adw_analyze.config import Repo
from adw_analyze.github import Commit, PR, parse_block
from adw_analyze.metrics import REGISTRY, compute
from adw_analyze.pricing import Usage
from adw_analyze.testkit import TmpCase, assistant, pr_node, tool_use, user_prompt, write_session, write_subagent
from adw_analyze.transcripts import SessionFacts

APP = Repo(name="app", slug="o/app", base="develop")
ADW = Repo(name="adw", slug="o/adw", role="contract", base="main")
START, END = "2026-10-01T00:00:00Z", "2026-10-29T00:00:00Z"


def pr(number, title, created, merged=None, state="MERGED", block="", commits=(), labels_ever=(), labels_now=(),
       files=(), repo="app", body=None, base="develop"):
    body = body if body is not None else (f"```\n{block}\n```" if block else "")
    b, n = parse_block(body)
    cs = [Commit(oid=str(i), headline=h, date=created, inherited=h.startswith("[adw ")) for i, h in enumerate(commits)]
    from adw_analyze.github import TITLE
    m = TITLE.match(title)
    return PR(repo=repo, number=number, title=title, slug=m.group(1) if m else None, unit=m.group(2) if m else None,
              adw=bool(m), state=state, created=created, merged=merged, closed=merged, last_edited=None,
              base=base, head="h", merge_sha=None, labels_now=set(labels_now),
              labels_ever=set(labels_ever) | set(labels_now), commits=cs, files=list(files), body=body, block=b,
              block_count=n)


def session(sid, agent=None, model="claude-opus-5-5", out=0, first="2026-10-05T08:00:00Z", last="2026-10-05T09:00:00Z",
            prompts=(), captures=None, peak=0, compactions=(), tool_calls=None, denials=None, gates=()):
    s = SessionFacts(path=f"/p/{sid}" + (f"/subagents/agent-{agent}.jsonl" if agent else ".jsonl"), project_dir="-app",
                     session_id=sid, agent_id=agent, first_ts=first, last_ts=last,
                     captures=collections.Counter(captures or {}), human_prompts=list(prompts),
                     compactions=list(compactions), tool_calls=collections.Counter(tool_calls or {}),
                     denials=collections.Counter(denials or {}), gate_calls=list(gates))
    s.usage = {"m": Usage(model=model, ts=first, output=out)} if out else {}
    s.peak_context = peak
    return s


def fixture():
    prs = [
        pr(1, "[adw alpha u01] a", "2026-10-05T10:00:00Z", "2026-10-05T12:00:00Z", labels_ever=["adw:blocked"],
           block="contract   aaaaaaa\ncycles     fix 1/3 · review 0/2 progress-conditions none fired\nowner-wait 0m",
           commits=["feat: x", "fix-attempt-1: y", "fix(review): z"]),
        pr(2, "[adw alpha] Alpha", "2026-10-06T10:00:00Z", "2026-10-06T12:00:00Z",
           block="contract   bbbbbbb\ncycles     fix 0/3 · review 1/2 progress-conditions P3 fired",
           commits=["[adw alpha u01] a (#1)", "fix-attempt-2: w"]),
        pr(3, "[adw beta u01] b", "2026-10-07T10:00:00Z", state="OPEN"),
        pr(4, "fix: crash after #1", "2026-10-08T10:00:00Z", "2026-10-08T11:00:00Z", body="Follow-up to #1."),
        pr(10, "adw-build: x", "2026-10-09T10:00:00Z", "2026-10-09T11:00:00Z", repo="adw", files=["commands/adw-build.md"]),
    ]
    open_prs = [pr(3, "[adw beta u01] b", "2026-10-07T10:00:00Z", state="OPEN", labels_now=["adw:failed"])]
    sessions = [
        session("m1", out=1_000_000, first="2026-10-05T08:00:00Z", last="2026-10-06T12:00:00Z",
                prompts=[("2026-10-05T09:00:00Z", "2026-10-05T08:30:00Z"), ("2026-10-05T20:00:00Z", "2026-10-05T00:00:00Z")],
                captures={"alpha": 25}, compactions=[("2026-10-05T11:00:00Z", "limit"), ("2026-10-05T12:00:00Z", "idle")],
                tool_calls={"Bash": 600}, denials={"auto_mode_classifier": 3}, gates=[("gate 4", "2026-10-05T10:00:00Z", 3600.0)]),
        session("m1", agent="s1", model="claude-sonnet-5-5", out=600_000, peak=300_000, tool_calls={"Bash": 400}),
        session("m2", out=150_000, first="2026-10-07T08:00:00Z", last="2026-10-07T09:00:00Z",
                prompts=[("2026-10-07T08:10:00Z", "2026-10-07T08:05:00Z")], captures={"beta": 30}),
        session("m2", agent="s2", model="claude-sonnet-5-5", out=0, first="2026-10-07T08:20:00Z", last="2026-10-07T08:30:00Z"),
        session("m3", model="claude-sonnet-5-5", out=100_000, first="2026-10-08T08:00:00Z", last="2026-10-08T08:30:00Z"),
    ]
    sessions[1].first_ts = sessions[1].last_ts = "2026-10-05T10:00:00Z"
    return F.assemble([APP, ADW], {"app": sessions}, prs, open_prs, until=END)


class Values(unittest.TestCase):
    def setUp(self):
        self.facts = fixture()
        self.win = F.Slice(self.facts, START, END)

    def v(self, mid, sl=None):
        return compute(mid, sl or self.win)

    def test_usd_per_merged_pr(self):
        r = self.v("cost.usd_per_merged_pr.v1")
        self.assertAlmostEqual(r.value, 15.0)
        self.assertEqual((r.n, r.status), (2, "below minimum"))

    def test_total_breakdown(self):
        r = self.v("cost.total_usd.v1")
        self.assertAlmostEqual(r.value, 30.0)
        self.assertAlmostEqual(r.breakdown["repo:app"], 30.0)
        self.assertAlmostEqual(r.breakdown["main"], 24.0)
        self.assertAlmostEqual(r.breakdown["sub"], 6.0)

    def test_owner_wait_cap(self):
        alpha = next(i for i in self.facts.intents if i.slug == "alpha")
        self.assertAlmostEqual(alpha.owner_wait_h, 12.5)

    def test_missing_field_is_no_data(self):
        beta_only = F.Slice(self.facts, "2026-10-07T00:00:00Z", "2026-10-08T00:00:00Z")
        r = compute("evidence.review0_with_fixreview_rate.v1", beta_only)
        self.assertEqual((r.value, r.status), (None, "no data"))

    def test_unattributed_session_counts_in_cost_only(self):
        self.assertIsNone(self.facts.slug_of["/p/m3.jsonl"])
        self.assertNotIn("/p/m3.jsonl", [s.path for i in self.facts.intents for s in i.sessions])

    def test_side_split(self):
        is_after = {("M", "aaaaaaa"): True, ("M", "bbbbbbb"): False}.get
        after = F.Slice(self.facts, START, END, side=("after", "M"), is_after=lambda m, c: is_after((m, c)))
        before = F.Slice(self.facts, START, END, side=("before", "M"), is_after=lambda m, c: is_after((m, c)))
        self.assertEqual([p.number for p in after.prs()], [1, 3])    # #3 has no sha anywhere: clock, so both here
        self.assertEqual([p.number for p in before.prs()], [2, 3])
        self.assertIn("/p/m1.jsonl", [s.path for s in after.sessions()])
        self.assertNotIn("/p/m1.jsonl", [s.path for s in before.sessions()])
        self.assertIn("/p/m3.jsonl", [s.path for s in before.sessions()])

    def test_only_rates_ratios_medians_predictable(self):
        for m in REGISTRY.values():
            self.assertEqual(m.predictable, m.kind in ("rate", "ratio", "median"), m.id)
            self.assertTrue(m.id.endswith(".v1"), m.id)

    def test_progress_buckets(self):
        self.assertEqual(self.v("design.progress_fired.v1").value, 1)
        self.assertEqual(self.v("design.progress_not_consumed.v1").value, 0)
        self.assertEqual(self.v("design.instrumented_units.v1").value, 2)

    def test_review0_mismatch(self):
        self.assertAlmostEqual(self.v("evidence.review0_with_fixreview_rate.v1").value, 0.5)

    def test_followup_fix_rate(self):
        self.assertAlmostEqual(self.v("outcome.followup_fix_rate.v1").value, 0.5)

    def test_fix_cycles_exclude_inherited(self):
        self.assertAlmostEqual(self.v("outcome.fix_cycles_per_pr.v1").value, 1.5)

    def test_rates(self):
        self.assertAlmostEqual(self.v("outcome.ever_blocked_rate.v1").value, 1 / 3)
        self.assertAlmostEqual(self.v("evidence.block_missing_rate.v1").value, 1 / 3)
        self.assertAlmostEqual(self.v("friction.subagents_over_250k_rate.v1").value, 0.5)
        self.assertAlmostEqual(self.v("friction.denials_per_1k_calls.v1").value, 3.0)
        self.assertEqual(self.v("friction.compactions_limit.v1").value, 1)
        self.assertEqual(self.v("friction.compactions_idle.v1").value, 1)
        self.assertAlmostEqual(self.v("time.gate_fg_hours.v1").value, 1.0)

    def test_run_hours_cap_gaps_like_the_wait(self):
        alpha = next(i for i in self.facts.intents if i.slug == "alpha")
        m1 = alpha.mains[0]
        m1.turn_ts = ["2026-10-05T08:00:00Z", "2026-10-05T09:00:00Z", "2026-10-06T05:00:00Z"]
        self.assertAlmostEqual(alpha.run_h, 13.0)

    def test_wait_share_over_main_threads_in_the_window(self):
        turns = {"/p/m1.jsonl": ["2026-10-05T08:00:00Z", "2026-10-05T09:00:00Z", "2026-10-06T05:00:00Z"],
                 "/p/m2.jsonl": ["2026-10-07T08:00:00Z", "2026-10-07T08:10:00Z"],
                 "/p/m3.jsonl": ["2026-10-08T08:00:00Z", "2026-10-08T08:30:00Z"]}
        for s in self.facts.sessions:
            s.turn_ts = turns.get(s.path, s.turn_ts)
        r = self.v("owner.wait_share.v1")
        self.assertAlmostEqual(r.value, (12.5 + 5 / 60) / (13 + 10 / 60 + 0.5))
        self.assertEqual(r.n, 3)

    def test_intents_without_sessions_are_not_zero_cost(self):
        F.Intent  # beta has sessions; add a third intent with a merged PR and no session
        self.facts.prs.append(pr(5, "[adw gamma u01] g", "2026-10-09T10:00:00Z", "2026-10-09T12:00:00Z"))
        facts = F.assemble([APP, ADW], {"app": [s for s in self.facts.sessions]}, self.facts.prs, self.facts.open_prs, until=END)
        r = compute("cost.usd_per_intent_median.v1", F.Slice(facts, START, END))
        self.assertEqual(r.n, 1)

    def test_lead_time(self):
        self.assertAlmostEqual(self.v("time.intent_lead_hours_median.v1").value, 27.0)

    def test_open_blocked_failed(self):
        self.assertEqual(self.v("design.open_blocked_failed.v1").value, 1)
        self.assertEqual(self.v("design.oldest_blocked_failed_days.v1").value, 21)
        prior = F.Slice(self.facts, "2026-09-03T00:00:00Z", START)
        self.assertEqual(compute("design.open_blocked_failed.v1", prior).status, "no data")

    def test_contract_prs_split_by_the_clock(self):
        after = F.Slice(self.facts, START, END, side=("after", "M"), is_after=lambda m, c: True, split_at="2026-10-09T12:00:00Z")
        before = F.Slice(self.facts, START, END, side=("before", "M"), is_after=lambda m, c: True, split_at="2026-10-09T12:00:00Z")
        self.assertEqual([p.number for p in after.contract_prs()], [])
        self.assertEqual([p.number for p in before.contract_prs()], [10])

    def test_transcript_metrics_before_complete_transcripts_are_no_data(self):
        self.facts.transcripts_since = "2026-10-06T00:00:00Z"
        early = F.Slice(self.facts, "2026-10-05T00:00:00Z", END)
        self.assertEqual(compute("cost.total_usd.v1", early).status, "no data")
        self.assertEqual(compute("friction.compactions_idle.v1", early).status, "no data")
        self.assertEqual(compute("outcome.prs_opened.v1", early).value, 3)
        late = F.Slice(self.facts, "2026-10-06T00:00:00Z", END)
        self.assertEqual(compute("cost.total_usd.v1", late).status, "ok")

    def test_loop_counts(self):
        self.facts.predict_lines = {10: [SimpleNamespace(kind="none")]}
        self.assertEqual(self.v("loop.contract_prs_merged.v1").value, 1)
        self.assertEqual(self.v("loop.contract_prs_predicts_none.v1").value, 1)
        self.assertAlmostEqual(self.v("loop.predicts_coverage.v1").value, 1.0)

    def test_uncovered_names_contract_prs_with_no_line(self):
        from adw_analyze.metrics import uncovered
        self.facts.predict_lines = {}
        self.assertEqual([p.number for p in uncovered(F.Slice(self.facts, START, END))], [10])
        self.facts.predict_lines = {10: [SimpleNamespace(kind="none")]}
        self.assertEqual(uncovered(F.Slice(self.facts, START, END)), [])

    def test_a_definition_change_is_a_new_id(self):
        from adw_analyze.metrics import FUNCS, metric
        metric("loop.example", "rate", 1, "ratio", "test only")(lambda sl: (None, 0, {}))
        metric("loop.example", "rate", 1, "ratio", "test only, new definition", version=2)(lambda sl: (None, 0, {}))
        try:
            self.assertIn("loop.example.v1", REGISTRY)   # the old id stays judgeable beside the new one
            self.assertIn("loop.example.v2", REGISTRY)
        finally:
            for mid in ("loop.example.v1", "loop.example.v2"):
                REGISTRY.pop(mid, None)
                FUNCS.pop(mid, None)

    def test_every_registry_id_computes(self):
        for mid in REGISTRY:
            r = compute(mid, self.win)
            self.assertIn(r.status, ("ok", "no data", "below minimum"), mid)


def merge_row(row):
    return f"contract   aaaaaaa\nmerge      {row}"


def gate_facts(prs):
    return F.assemble([APP, ADW], {"app": []}, prs, [], until=END)


class AutoMerge(unittest.TestCase):
    def test_auto_merged_share(self):
        prs = [pr(21, "[adw a] A", "2026-10-05T10:00:00Z", "2026-10-05T12:00:00Z", block=merge_row("merged 1111111 · base unmoved")),
               pr(22, "[adw b u01] B", "2026-10-06T10:00:00Z", "2026-10-06T12:00:00Z",
                  block=merge_row("merged 2222222 · base trial ok at 3333333")),
               pr(23, "[adw c] C", "2026-10-07T10:00:00Z", state="OPEN", block=merge_row("hold 7 — walk failed · at 4444444")),
               pr(24, "[adw d] D", "2026-10-08T10:00:00Z", "2026-10-09T12:00:00Z", block=merge_row("hold call — denied · at 5555555")),
               pr(25, "[adw e u01] E", "2026-10-08T10:00:00Z", "2026-10-08T12:00:00Z", block="contract   aaaaaaa",
                  base="adw/e"),                                                     # a sub-PR: the gate never runs on it
               pr(26, "[adw f] F", "2026-10-09T10:00:00Z", state="OPEN", block="contract   aaaaaaa")]   # in flight
        r = compute("outcome.auto_merged_share.v1", F.Slice(gate_facts(prs), START, END))
        self.assertAlmostEqual(r.value, 0.5)
        self.assertEqual(r.n, 4)

    def test_share_counts_final_prs_that_ended_without_the_gate(self):
        prs = [pr(21, "[adw a] A", "2026-10-05T10:00:00Z", "2026-10-05T12:00:00Z", block=merge_row("merged 1111111 · base unmoved")),
               pr(22, "[adw b u02] B", "2026-10-06T10:00:00Z", state="OPEN", labels_now=["adw:blocked"], block="contract   aaaaaaa"),
               pr(23, "[adw c] C", "2026-10-07T10:00:00Z", state="CLOSED", block="contract   aaaaaaa")]
        r = compute("outcome.auto_merged_share.v1", F.Slice(gate_facts(prs), START, END))
        self.assertAlmostEqual(r.value, 1 / 3)   # a blocked PR and a closed one were not auto-merged
        self.assertEqual(r.n, 3)

    def test_auto_merged_label_stands_for_a_lost_row(self):
        prs = [pr(21, "[adw a] A", "2026-10-05T10:00:00Z", "2026-10-05T12:00:00Z", labels_ever=["adw:auto-merged"],
                  block=merge_row("hold 5 — checks pending · at 1111111"))]
        sl = F.Slice(gate_facts(prs), START, END)
        self.assertAlmostEqual(compute("outcome.auto_merged_share.v1", sl).value, 1.0)
        from adw_analyze.metrics import holds
        self.assertEqual(holds(sl), {})

    def test_a_revert_counts_only_against_the_pr_it_reverts(self):
        auto = merge_row("merged 1111111 · base unmoved")
        prs = [pr(21, "[adw a] A", "2026-10-05T10:00:00Z", "2026-10-05T12:00:00Z", block=auto),
               pr(22, "[adw b] B", "2026-10-05T10:00:00Z", "2026-10-05T13:00:00Z", block=auto),
               pr(41, 'Revert "[adw a] A"', "2026-10-06T10:00:00Z", "2026-10-06T11:00:00Z",
                  body="Reverts o/app#21\n\nKeeps the fix from #22.")]
        r = compute("outcome.auto_merge_false_pass.v1", F.Slice(gate_facts(prs), START, END))
        self.assertAlmostEqual(r.value, 0.5)

    def test_a_fix_pr_citing_the_merge_is_a_false_pass(self):
        prs = [pr(21, "[adw a] A", "2026-10-05T10:00:00Z", "2026-10-05T12:00:00Z", block=merge_row("merged 1111111 · base unmoved")),
               pr(43, "fix: crash after the ward change", "2026-10-07T10:00:00Z", "2026-10-07T11:00:00Z", body="Follow-up to #21.")]
        r = compute("outcome.auto_merge_false_pass.v1", F.Slice(gate_facts(prs), START, END))
        self.assertAlmostEqual(r.value, 1.0)

    def test_a_fix_pr_citing_another_repo_is_not_a_false_pass(self):
        prs = [pr(21, "[adw a] A", "2026-10-05T10:00:00Z", "2026-10-05T12:00:00Z", block=merge_row("merged 1111111 · base unmoved")),
               pr(43, "fix: bump the lib", "2026-10-07T10:00:00Z", "2026-10-07T11:00:00Z", body="Needs o/lib#21 first.")]
        r = compute("outcome.auto_merge_false_pass.v1", F.Slice(gate_facts(prs), START, END))
        self.assertAlmostEqual(r.value, 0.0)

    def test_one_followup_counts_once_against_the_latest_merge(self):
        auto = merge_row("merged 1111111 · base unmoved")
        prs = [pr(21, "[adw d u04] D4", "2026-10-05T10:00:00Z", "2026-10-07T10:00:00Z", block=auto),
               pr(22, "[adw d] D", "2026-10-05T10:00:00Z", "2026-10-07T12:00:00Z", block=auto),
               pr(31, "[adw d-f1] smaller", "2026-10-09T10:00:00Z", state="OPEN")]
        r = compute("outcome.auto_merge_false_pass.v1", F.Slice(gate_facts(prs), START, END))
        self.assertAlmostEqual(r.value, 0.5)
        self.assertEqual(r.n, 2)

    def test_auto_merge_false_pass(self):
        auto = merge_row("merged 1111111 · base unmoved")
        prs = [pr(21, "[adw alpha] A", "2026-10-05T10:00:00Z", "2026-10-05T12:00:00Z", block=auto),
               pr(31, "[adw alpha-f1] logo bigger", "2026-10-08T10:00:00Z", "2026-10-08T12:00:00Z"),
               pr(41, 'Revert "[adw alpha] A"', "2026-10-09T10:00:00Z", "2026-10-09T11:00:00Z", body="Reverts o/app#21"),
               pr(22, "[adw beta] B", "2026-10-06T10:00:00Z", "2026-10-06T12:00:00Z", block=auto),
               pr(32, "[adw beta-f1] late", "2026-10-14T13:00:00Z", state="OPEN"),
               pr(23, "[adw gamma] G", "2026-10-07T10:00:00Z", "2026-10-07T12:00:00Z", block=auto),
               pr(33, "[adw big-gamma-f1] other", "2026-10-08T10:00:00Z", state="OPEN"),
               pr(24, "[adw delta] D", "2026-10-07T10:00:00Z", "2026-10-10T12:00:00Z", block=merge_row("hold 7 — walk failed · at 4444444")),
               pr(34, "[adw delta-f1] fix", "2026-10-11T10:00:00Z", state="OPEN"),
               pr(25, "[adw eps] E", "2026-10-24T10:00:00Z", "2026-10-25T12:00:00Z", block=auto),
               pr(26, "[adw zeta u01] Z", "2026-10-10T10:00:00Z", "2026-10-11T12:00:00Z", block=auto),
               pr(42, 'Revert "[adw zeta u01] Z"', "2026-10-12T10:00:00Z", "2026-10-12T11:00:00Z", body="")]
        r = compute("outcome.auto_merge_false_pass.v1", F.Slice(gate_facts(prs), START, END))
        self.assertAlmostEqual(r.value, 0.5)   # alpha once (follow-up and revert), zeta (revert); not beta, gamma
        self.assertEqual(r.n, 4)               # delta was held, eps has not had its 7 days

    def test_holds_by_condition_table(self):
        from adw_analyze.report import Run, report_md, totals
        prior = ("2026-09-03T00:00:00Z", START)
        prs = [pr(21, "[adw a] A", "2026-10-05T10:00:00Z", state="OPEN", block=merge_row("hold 7 — walk failed · at 1111111")),
               pr(22, "[adw b] B", "2026-10-06T10:00:00Z", state="OPEN", block=merge_row("hold 7 — 2 gaps · at 2222222")),
               pr(23, "[adw c] C", "2026-10-07T10:00:00Z", state="OPEN", block=merge_row("hold 1 — merge: hold · at 3333333")),
               pr(24, "[adw d] D", "2026-10-08T10:00:00Z", state="OPEN", block=merge_row("hold call — denied · at 4444444")),
               pr(25, "[adw e] E", "2026-10-08T10:00:00Z", "2026-10-08T12:00:00Z", block=merge_row("merged 5555555 · base unmoved")),
               pr(26, "[adw f] F", "2026-09-20T10:00:00Z", state="OPEN", block=merge_row("hold 7 — walk failed · at 6666666")),
               pr(27, "[adw g] G", "2026-10-09T10:00:00Z", state="OPEN",
                  block=merge_row("hold 10 — the design sign-off is pending · at 7777777"))]
        facts = gate_facts(prs)
        run = Run(until=END, window=(START, END), prior=prior, facts=facts,
                  win={m: compute(m, F.Slice(facts, START, END)) for m in REGISTRY},
                  pri={m: compute(m, F.Slice(facts, *prior)) for m in REGISTRY})
        report = report_md(run, {}, totals(facts))
        self.assertIn("## Auto-merge holds", report)
        self.assertIn("| 1 · flag | 1 | 0 |", report)
        self.assertIn("| 10 · design sign-off | 1 | 0 |", report)
        self.assertIn("| 7 · walk | 2 | 1 |", report)
        self.assertIn("| call · merge call | 1 | 0 |", report)
        self.assertNotIn("| 2 · base |", report)


class Build(TmpCase):
    def test_build_facts_reads_files_and_drops_the_analyzer(self):
        projects = self.mkdir("projects")
        write_session(projects, "-app", "m1", [user_prompt("2026-10-05T08:00:00Z", "/adw-build alpha", gitBranch="adw/alpha")] +
                      [assistant(f"2026-10-05T08:{i:02d}:30Z", f"m{i}", tools=[tool_use(f"t{i}", "Bash", command="git -C .claude/worktrees/adw-alpha-u01 status")])
                       for i in range(25)])
        write_subagent(projects, "-app", "m1", "a1", [assistant("2026-10-05T09:00:00Z", "x1")], "t0")
        write_session(projects, "-app", "m9", [assistant("2026-10-06T08:00:00Z", "y1", tools=[
            tool_use("u1", "Bash", command="python3 scripts/adw-analyze.py --reports r")])])
        repo = Repo(name="app", slug="o/app", transcripts=["-app"])
        self.gh.set(prs={"o/app": [pr_node(1, "[adw alpha u01] a", created="2026-10-05T10:00:00Z")]}, open={})
        with mock.patch.dict(os.environ, self.gh.env()):
            facts = F.build_facts([repo], projects, until=END, since="2026-09-01T00:00:00Z")
        self.assertEqual(facts.excluded_sessions, 1)
        self.assertEqual(sorted(s.session_id for s in facts.sessions), ["m1", "m1"])
        self.assertEqual({facts.slug_of[s.path] for s in facts.sessions}, {"alpha"})

    def test_no_transcripts_is_a_source_error(self):
        from adw_analyze.github import SourceError
        repo = Repo(name="app", slug="o/app", transcripts=["-nothing-*"])
        self.gh.set(prs={}, open={})
        with mock.patch.dict(os.environ, self.gh.env()), self.assertRaises(SourceError):
            F.build_facts([repo], self.mkdir("projects"), until=END, since="2026-09-01T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
