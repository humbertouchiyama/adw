"""Session and subagent → intent slug (spec §5.1). Counting every session that merely names a slug
mixed parallel intents and gave a 21 h lead time for a 7 h one; `native-painel` is a prefix of four
slugs. So: longest slug first, a high bar for main threads, and the dispatching prompt for subagents."""
from __future__ import annotations

import collections
import re

from .transcripts import SessionFacts

MIN_HITS = 20
MIN_RATIO = 3
PREFIXES = ("adw-close-", "pr-ready-", "adw-", "adw/")
SUFFIX = re.compile(r"(?:-u\d+(?:\+u\d+)*|-close-v\d+)$")


def normalize(capture: str, known: set[str]) -> str | None:
    c = capture
    for p in PREFIXES:
        if c.startswith(p):
            c = c[len(p):]
            break
    c = SUFFIX.sub("", c)
    if c in known:
        return c
    hits = [k for k in known if c.startswith(k + "-")]
    return max(hits, key=len) if hits else None


def tally(captures: collections.Counter, known: set[str]) -> collections.Counter:
    out = collections.Counter()
    for c, n in captures.items():
        slug = normalize(c, known)
        if slug:
            out[slug] += n
    return out


def attribute_session(s: SessionFacts, known: set[str], adw_pr_slugs: dict[int, str], repo_slug: str | None = None) -> str | None:
    linked = {adw_pr_slugs[n] for r, n in s.pr_links if (repo_slug is None or r in (None, repo_slug)) and n in adw_pr_slugs}
    if len(linked) == 1:
        return next(iter(linked))
    top = tally(s.captures, known).most_common(2)
    if not top or top[0][1] < MIN_HITS:
        return None
    if len(top) == 2 and top[0][1] < MIN_RATIO * top[1][1]:
        return None
    return top[0][0]


def unique_top(counts: collections.Counter) -> str | None:
    top = counts.most_common(2)
    if not top or (len(top) == 2 and top[0][1] == top[1][1]):
        return None
    return top[0][0]


def attribute_all(sessions: list[SessionFacts], known: set[str], adw_pr_slugs: dict[int, str],
                  repo_slug: str | None = None) -> dict[str, str | None]:
    mains = {s.session_id: s for s in sessions if s.is_main}
    agents = {(s.session_id, s.agent_id): s for s in sessions if not s.is_main}
    out = {s.path: attribute_session(s, known, adw_pr_slugs, repo_slug) for s in mains.values()}

    def parent_of(a: SessionFacts) -> SessionFacts | None:
        if a.parent_agent_id:
            return agents.get((a.session_id, a.parent_agent_id)) or mains.get(a.session_id)
        return mains.get(a.session_id)

    def resolve(a: SessionFacts, depth: int = 0) -> str | None:
        if a.path in out:
            return out[a.path]
        parent = parent_of(a)
        prompt = parent.dispatches.get(a.tool_use_id, collections.Counter()) if parent else collections.Counter()
        slug = unique_top(tally(prompt, known)) or unique_top(tally(a.captures, known))
        if slug is None and parent is not None and depth < 8:
            slug = resolve(parent, depth + 1) if not parent.is_main else out.get(parent.path)
        out[a.path] = slug
        return slug

    for a in agents.values():
        resolve(a)
    return out
