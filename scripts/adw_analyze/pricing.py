"""One dated price table (spec §5.1: one window was restated after two analyses mixed price tables)."""
from __future__ import annotations

from dataclasses import dataclass

PRICES_AS_OF = "2026-10-22"
# $ per million tokens: input, output, cache read. Cache writes: 5 minutes 1.25 × input, 1 hour 2 × input.
PRICES = {"opus": (4.0, 20.0, 0.20), "sonnet": (2.0, 10.0, 0.20), "haiku": (1.0, 5.0, 0.10)}


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
    for k in PRICES:
        if k in m:
            return k
    return None


def message_cost(u: Usage) -> float:
    f = family(u.model)
    if not f:
        return 0.0
    i, o, r = PRICES[f]
    return (u.input * i + u.output * o + u.cache_read * r + u.cache_write_5m * i * 1.25 + u.cache_write_1h * i * 2) / 1e6
