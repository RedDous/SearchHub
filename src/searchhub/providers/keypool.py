from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

from searchhub.engine.rate_limit import TokenBucket


class _KeyState:
    def __init__(self, key: str, max_concurrency: int, rps_limit: float, cooldown_s: float):
        self.key = key
        self.max_concurrency = max_concurrency
        self.sem = asyncio.Semaphore(max_concurrency)
        self.bucket = TokenBucket(rps_limit)
        self.cooldown_s = cooldown_s
        self.cooldown_until = 0.0
        self.in_flight = 0
        self.ok = True


class KeyPool:
    def __init__(self, keys: list[str], max_concurrency: int = 2,
                 rps_limit: float = 10, cooldown_s: float = 60.0):
        self._keys = [_KeyState(k, max_concurrency, rps_limit, cooldown_s) for k in keys]
        self._cursor = 0
        self._free_event = asyncio.Event()
        self._free_event.set()

    @asynccontextmanager
    async def use(self) -> AsyncIterator[str]:
        key = await self._acquire()
        try:
            yield key.key
        finally:
            key.in_flight -= 1
            key.sem.release()
            self._free_event.set()

    async def _acquire(self) -> _KeyState:
        while True:
            state = self._pick()
            if state is not None:
                await state.sem.acquire()
                await state.bucket.acquire()
                state.in_flight += 1
                return state
            if not self._keys:
                raise RuntimeError("KeyPool has no keys")
            self._free_event.clear()
            wake = asyncio.create_task(self._free_event.wait())
            earliest = min(state.cooldown_until - time.monotonic()
                           for state in self._keys)
            try:
                await asyncio.wait_for(wake, timeout=max(0.0, earliest))
            except asyncio.TimeoutError:
                pass
            finally:
                wake.cancel()
                self._free_event.set()

    def _pick(self) -> _KeyState | None:
        n = len(self._keys)
        if n == 0:
            return None
        now = time.monotonic()
        for _ in range(n):
            state = self._keys[self._cursor % n]
            self._cursor += 1
            if state.cooldown_until <= now and state.sem._value > 0:
                return state
        return None

    def report_error(self, key: str, status: int | None = None) -> None:
        for state in self._keys:
            if state.key == key:
                if status in (429, 432):
                    state.cooldown_until = time.monotonic() + state.cooldown_s
                elif status in (401, 403):
                    state.cooldown_until = time.monotonic() + state.cooldown_s * 10
                    state.ok = False
                else:
                    state.cooldown_until = time.monotonic() + min(5.0, state.cooldown_s)
                return

    def status(self) -> list[dict]:
        now = time.monotonic()
        result = []
        for state in self._keys:
            mask = state.key[:8] + "****" + state.key[-4:]
            result.append({
                "key": mask,
                "cooling_until": max(0.0, state.cooldown_until - now),
                "in_flight": state.in_flight,
                "ok": state.ok and state.cooldown_until <= now,
            })
        return result
