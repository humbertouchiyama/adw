"""One Claude Code transcript (a main thread or a subagent JSONL) → SessionFacts.

Keeps counts, timestamps and short regex captures (slugs, worktree names) only: no message, prompt,
command or tool-output text survives the parse. Rules from spec §5.1:

- usage is deduped by message.id, keeping the record with the largest output_tokens; the harness
  `cost-state` record is never read (it resets per process);
- a compaction is `manual`, `idle` (a "Compacted while idle" notice within 10 s of the boundary) or
  `limit`;
- session time comes from user and assistant records only (a "Remote Control disconnected" record is
  stamped into every open session);
- background gate runs have no completion record, so only foreground gate time is measured.

Two definitions the old reader (scripts/adw-metrics.sh, design §5.1) encoded, kept for every reader of
the PR evidence block: `review N/2` counts review rounds that APPLIED findings, so `0/2` is a clean
review, not a skipped one; and `progress-conditions` is hyphenated, so a grep for the spaced form
matches nothing and reads like "none fired".
"""
from __future__ import annotations

import collections
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime

from .pricing import Usage, family, message_cost

KNOWN_TYPES = {
    "user", "assistant", "system", "attachment", "queue-operation", "api-request", "api-request-blob",
    "api-request-shape", "bridge-session", "last-prompt", "atis-latch", "mode", "permission-mode", "ai-title",
    "custom-title", "agent-name", "agent-color", "pr-link", "file-history-snapshot", "file-history-delta",
    "history-suppression", "relocated", "worktree-state", "tools-used", "cost-state", "summary", "progress",
    "fork-context-ref",
}
CAPTURES = [
    re.compile(r"\.claude/worktrees/([A-Za-z0-9._+-]+)"),
    re.compile(r"\badw/([a-z0-9][a-z0-9.+-]+)"),
    re.compile(r"\[adw ([a-z0-9][a-z0-9.-]+)"),
    re.compile(r"/adw(?:-init|-build|-resume|-close|-smoke)?\s+([a-z0-9][a-z0-9-]+)"),
]
DENIALS = [
    ("doesn't want to proceed", "user_rejected"),
    ("denied by the Claude Code auto mode", "auto_mode_classifier"),
    ("classifier gave no verdict", "classifier_no_verdict"),
    ("built-in Claude Code safety", "builtin_safety"),
]
IDLE_NOTICE = "Compacted while idle"
SOURCE = re.compile(r"^[a-z_]{1,32}$")
TYPE = re.compile(r"^[a-z][a-z-]{0,39}$")


def safe(value, rx: re.Pattern) -> str:
    """Values that become output keys come from transcripts: keep only enum-shaped ones."""
    return value if isinstance(value, str) and rx.match(value) else "other"
INTERRUPT = "[Request interrupted by user"


@dataclass
class SessionFacts:
    path: str
    project_dir: str
    session_id: str
    agent_id: str | None = None
    tool_use_id: str | None = None
    parent_agent_id: str | None = None
    cwd: str | None = None
    branches: collections.Counter = field(default_factory=collections.Counter)
    first_ts: str | None = None
    last_ts: str | None = None
    turn_ts: list = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    compactions: list = field(default_factory=list)
    tool_calls: collections.Counter = field(default_factory=collections.Counter)
    tool_errors: collections.Counter = field(default_factory=collections.Counter)
    denials: collections.Counter = field(default_factory=collections.Counter)
    human_prompts: list = field(default_factory=list)
    interrupts: list = field(default_factory=list)
    pr_links: list = field(default_factory=list)
    captures: collections.Counter = field(default_factory=collections.Counter)
    dispatches: dict = field(default_factory=dict)
    gate_calls: list = field(default_factory=list)
    background_gate_calls: int = 0
    ran_analyzer: bool = False
    peak_context: int = 0
    unknown_types: collections.Counter = field(default_factory=collections.Counter)
    unknown_models: int = 0
    bad_lines: int = 0

    @property
    def cost(self) -> float:
        return sum(message_cost(u) for u in self.usage.values())

    @property
    def is_main(self) -> bool:
        return self.agent_id is None


def ts_seconds(ts: str) -> float:
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()


def capture(text: str, into: collections.Counter) -> None:
    for rx in CAPTURES:
        for m in rx.findall(text or ""):
            into[m] += 1


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    out = []
    for b in content or []:
        if isinstance(b, dict):
            if b.get("type") == "text":
                out.append(b.get("text") or "")
            elif b.get("type") == "tool_result":
                out.append(result_text(b))
    return "\n".join(out)


def result_text(block: dict) -> str:
    c = block.get("content")
    if isinstance(c, str):
        return c
    return " ".join(x.get("text") or "" for x in (c or []) if isinstance(x, dict))


def denial_source(text: str) -> str | None:
    for marker, source in DENIALS:
        if marker in text:
            return source
    if "hook error" in text and ("Block" in text or "BLOCK" in text):
        return "hook_block"
    return None


def read_meta(path: str) -> dict:
    try:
        with open(path[:-len(".jsonl")] + ".meta.json") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def read_session(path: str, gates: dict[str, str]) -> SessionFacts:
    parts = path.split(os.sep)
    if len(parts) >= 4 and parts[-2] == "subagents":
        name = parts[-1][:-len(".jsonl")]
        s = SessionFacts(path=path, project_dir=parts[-4], session_id=parts[-3],
                         agent_id=name[len("agent-"):] if name.startswith("agent-") else name)
        meta = read_meta(path)
        s.tool_use_id = meta.get("toolUseId")
        s.parent_agent_id = meta.get("parentAgentId")
        for k in ("worktreeBranch", "worktreePath"):
            capture(str(meta.get(k) or ""), s.captures)
    else:
        s = SessionFacts(path=path, project_dir=parts[-2], session_id=parts[-1][:-len(".jsonl")])
    gate_rx = {name: re.compile(rx) for name, rx in gates.items()}
    cwds = collections.Counter()
    pending = {}          # gate tool_use id -> (gate, ts)
    tool_names = {}       # tool_use id -> tool name
    boundaries = []       # (ts, trigger)
    idle_notices = []
    last_assistant = None
    with open(path, errors="replace") as f:
        for line in f:
            try:
                o = json.loads(line)
            except ValueError:
                s.bad_lines += 1
                continue
            if not isinstance(o, dict):
                s.bad_lines += 1
                continue
            t = o.get("type")
            ts = o.get("timestamp")
            if t not in KNOWN_TYPES:
                s.unknown_types[safe(t, TYPE)] += 1
                continue
            if o.get("gitBranch"):
                s.branches[o["gitBranch"]] += 1
                capture(o["gitBranch"], s.captures)
            if o.get("cwd"):
                cwds[o["cwd"]] += 1
                capture(o["cwd"], s.captures)
            if t in ("user", "assistant") and ts:
                s.turn_ts.append(ts)
            if t == "assistant":
                read_assistant(s, o, ts, gate_rx, pending, tool_names)
                last_assistant = ts or last_assistant
            elif t == "user":
                read_user(s, o, ts, last_assistant, pending, tool_names)
            elif t == "system":
                st = o.get("subtype")
                if st == "compact_boundary":
                    boundaries.append((ts, (o.get("compactMetadata") or {}).get("trigger")))
                elif IDLE_NOTICE in str(o.get("content") or ""):
                    idle_notices.append(ts)
            elif t == "pr-link" and o.get("prNumber") is not None:
                s.pr_links.append((o.get("prRepository"), int(o["prNumber"])))
    s.turn_ts.sort()
    if s.turn_ts:
        s.first_ts, s.last_ts = s.turn_ts[0], s.turn_ts[-1]
    if cwds:
        s.cwd = cwds.most_common(1)[0][0]
    for ts, trigger in boundaries:
        if trigger == "manual":
            kind = "manual"
        elif ts and any(n and abs(ts_seconds(n) - ts_seconds(ts)) <= 10 for n in idle_notices):
            kind = "idle"
        else:
            kind = "limit"
        s.compactions.append((ts, kind))
    for u in s.usage.values():
        s.peak_context = max(s.peak_context, u.context)
    return s


def read_assistant(s, o, ts, gate_rx, pending, tool_names) -> None:
    m = o.get("message") or {}
    model = m.get("model")
    if model and model != "<synthetic>":
        u = m.get("usage") or {}
        mid = m.get("id") or o.get("requestId") or o.get("uuid")
        prev = s.usage.get(mid)
        if prev is None or (u.get("output_tokens") or 0) > prev.output:
            cc = u.get("cache_creation") or {}
            w5 = cc.get("ephemeral_5m_input_tokens") or 0
            w1 = cc.get("ephemeral_1h_input_tokens") or 0
            if w5 + w1 == 0:
                w5 = u.get("cache_creation_input_tokens") or 0
            if prev is None and not family(model):
                s.unknown_models += 1
            s.usage[mid] = Usage(model=model, ts=ts or "", input=u.get("input_tokens") or 0,
                                 output=u.get("output_tokens") or 0, cache_read=u.get("cache_read_input_tokens") or 0,
                                 cache_write_5m=w5, cache_write_1h=w1)
    for b in m.get("content") or []:
        if not isinstance(b, dict) or b.get("type") != "tool_use":
            continue
        tid, name, inp = b.get("id"), b.get("name"), b.get("input") or {}
        if tid in tool_names:
            continue
        tool_names[tid] = name
        s.tool_calls[name] += 1
        if name in ("Agent", "Task"):
            caps = collections.Counter()
            capture(str(inp.get("prompt") or "") + " " + str(inp.get("description") or ""), caps)
            s.dispatches[tid] = caps
        elif name == "Bash":
            cmd = str(inp.get("command") or "")
            capture(cmd, s.captures)
            if "adw-analyze.py" in cmd:
                s.ran_analyzer = True
            gate = next((g for g, rx in gate_rx.items() if rx.search(cmd)), None)
            if gate:
                if inp.get("run_in_background"):
                    s.background_gate_calls += 1
                elif ts:
                    pending[tid] = (gate, ts)


def read_user(s, o, ts, last_assistant, pending, tool_names) -> None:
    m = o.get("message") or {}
    c = m.get("content")
    pdc = o.get("permissionDecision") or {}
    marked = 0
    has_result = False
    if isinstance(c, list):
        for b in c:
            if not isinstance(b, dict) or b.get("type") != "tool_result":
                continue
            has_result = True
            tid = b.get("tool_use_id")
            if tid in pending and ts:
                gate, start = pending.pop(tid)
                s.gate_calls.append((gate, start, ts_seconds(ts) - ts_seconds(start)))
            if b.get("is_error"):
                s.tool_errors[tool_names.get(tid, "?")] += 1
                src = denial_source(result_text(b))
                if src:
                    s.denials[src] += 1
                    marked += 1
    if pdc.get("decision") == "reject" and not marked:
        # a rejected call usually also carries a marker in its error text; count the denial once
        s.denials["permissionDecision:" + safe(pdc.get("source"), SOURCE)] += 1
    text = text_of(c) if not has_result else ""
    if INTERRUPT in text_of(c):
        s.interrupts.append(ts)
    human = (o.get("origin") or {}).get("kind") == "human" or o.get("promptSource") == "typed"
    if human and not o.get("isMeta") and not has_result:
        s.human_prompts.append((ts, last_assistant))
        capture(text, s.captures)
        if text.lstrip().startswith("/adw-analyze"):
            s.ran_analyzer = True
