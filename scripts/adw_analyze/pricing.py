"""One dated price table (spec §5.1: one window was restated after two analyses mixed price tables)."""
from __future__ import annotations

from dataclasses import dataclass

PRICES_AS_OF = "2026-10-28"
# $ per million tokens by model id prefix, longest prefix first: input, output, cache read.
# Cache writes: 5 minutes 1.25 × input, 1 hour 2 × input. Opus 5.5, Sonnet 5.5 and Fable 5.1 cache reads
# are the published ones; the rest assume the usual 0.1 × input. Haiku 5.5 is the price up to 100K prompts.
PRICES = {
    "claude-fable-5": (10.0, 50.0, 0.25),
    "claude-mythos-5": (10.0, 50.0, 0.25),
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-opus-5": (5.0, 25.0, 0.50),
    "claude-opus-4": (5.0, 25.0, 0.50),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20),
    "claude-sonnet-5": (2.0, 10.0, 0.20),
    "claude-sonnet-4": (3.0, 15.0, 0.30),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
    "claude-haiku-4": (1.0, 5.0, 0.10),
}
FAMILIES = ("fable", "mythos", "opus", "sonnet", "haiku")


@dataclass
class Usage:
    model: str
    ts: str
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write_5m: int = 0
    cache_write_1h: int = 0

    @property
    def context(self) -> int:
        return self.input + self.cache_read + self.cache_write_5m + self.cache_write_1h


def family(model: str) -> str | None:
    m = (model or "").lower()
    return next((k for k in FAMILIES if k in m), None)


def price_of(model: str) -> tuple | None:
    m = (model or "").lower()
    hits = [k for k in PRICES if m.startswith(k)]
    return PRICES[max(hits, key=len)] if hits else None


def message_cost(u: Usage) -> float:
    p = price_of(u.model)
    if not p:
        return 0.0
    i, o, r = p
    return (u.input * i + u.output * o + u.cache_read * r + u.cache_write_5m * i * 1.25 + u.cache_write_1h * i * 2) / 1e6
