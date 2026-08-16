from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

from searchhub.providers.base import Provider, ProviderError


@dataclass
class Outcome:
    provider_id: str
    items: list | None = None
    error: str | None = None
    took_ms: float = 0.0
    cache_hit: bool = False

    @classmethod
    def error_outcome(cls, provider_id: str, err: BaseException, took_ms: float = 0.0) -> "Outcome":
        if isinstance(err, ProviderError):
            message = err.message
        elif isinstance(err, TimeoutError):
            message = "provider timeout"
        else:
            message = str(err) or err.__class__.__name__
        return cls(provider_id=provider_id, error=message, took_ms=took_ms)


async def fanout(calls: list[tuple[Provider, Coroutine]], timeout_s: float) -> list[Outcome]:
    async def run(p: Provider, coro: Coroutine) -> Outcome:
        start = time.monotonic()
        try:
            items = await asyncio.wait_for(coro, timeout=timeout_s)
            return Outcome(provider_id=p.id, items=items, took_ms=(time.monotonic() - start) * 1000)
        except BaseException as e:
            return Outcome.error_outcome(p.id, e, (time.monotonic() - start) * 1000)

    return await asyncio.gather(*(run(p, c) for p, c in calls))


_ROTATION_CURSOR: dict[str, int] = {}


async def rotation(providers: list[Provider], cap: str, timeout_s: float,
                   call: Callable[[Provider], Coroutine]) -> Outcome:
    if not providers:
        return Outcome(provider_id="", error="no provider available")
    cursor = _ROTATION_CURSOR.get(cap, 0)
    last: Outcome = Outcome(provider_id="", error="no provider available")
    for i in range(len(providers)):
        p = providers[(cursor + i) % len(providers)]
        start = time.monotonic()
        try:
            items = await asyncio.wait_for(call(p), timeout=timeout_s)
            outcome = Outcome(provider_id=p.id, items=items,
                              took_ms=(time.monotonic() - start) * 1000)
            _ROTATION_CURSOR[cap] = (cursor + i + 1) % len(providers)
            return outcome
        except BaseException as e:
            last = Outcome.error_outcome(p.id, e, (time.monotonic() - start) * 1000)
    _ROTATION_CURSOR[cap] = (cursor + len(providers)) % len(providers)
    return last


async def primary_fallback(providers: list[Provider], cap: str, timeout_s: float,
                           call: Callable[[Provider], Coroutine]) -> Outcome:
    if not providers:
        return Outcome(provider_id="", error="no provider available")
    last: Outcome = Outcome(provider_id="", error="no provider available")
    for p in providers:
        start = time.monotonic()
        try:
            items = await asyncio.wait_for(call(p), timeout=timeout_s)
            return Outcome(provider_id=p.id, items=items,
                           took_ms=(time.monotonic() - start) * 1000)
        except BaseException as e:
            last = Outcome.error_outcome(p.id, e, (time.monotonic() - start) * 1000)
    return last
