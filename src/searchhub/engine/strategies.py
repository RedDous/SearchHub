from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Outcome:
    provider_id: str
    items: list | None = None
    error: str | None = None
    took_ms: float = 0.0
    cache_hit: bool = False
