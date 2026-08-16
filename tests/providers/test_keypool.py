import asyncio
import time

import pytest

from searchhub.providers.keypool import KeyPool


@pytest.mark.asyncio
async def test_round_robin_order():
    pool = KeyPool(keys=["a", "b", "c"])
    seen = []
    for _ in range(6):
        async with pool.use() as key:
            seen.append(key)
    assert seen == ["a", "b", "c", "a", "b", "c"]


@pytest.mark.asyncio
async def test_error_puts_key_in_cooldown():
    pool = KeyPool(keys=["a", "b"], cooldown_s=60)
    async with pool.use() as key:
        pool.report_error(key, status=429)
    used = set()
    for _ in range(4):
        async with pool.use() as k:
            used.add(k)
    assert used == {"b"}


@pytest.mark.asyncio
async def test_concurrency_limited():
    pool = KeyPool(keys=["a"], max_concurrency=1)
    async def slow():
        async with pool.use():
            await asyncio.sleep(0.2)
    start = time.monotonic()
    await asyncio.gather(slow(), slow())
    assert time.monotonic() - start >= 0.35


@pytest.mark.asyncio
async def test_status_masks_key():
    pool = KeyPool(keys=["tvly-secret123"])
    async with pool.use():
        pass
    st = pool.status()[0]
    assert st["key"] != "tvly-secret123"
    assert st["key"].startswith("tvly-") and "****" in st["key"]
    assert st["ok"] is True


def test_status_masks_various_lengths():
    cases = {"abcdefghijklm": "abcde****jklm", "abcd1234": "ab****34", "abc": "****"}
    for key, expected in cases.items():
        pool = KeyPool(keys=[key])
        mask = pool.status()[0]["key"]
        assert mask == expected
        assert key not in mask


class _CountingEvent:
    def __init__(self, wrapped):
        self._wrapped = wrapped
        self.transitions = 0

    def clear(self):
        self.transitions += 1
        self._wrapped.clear()

    def set(self):
        self.transitions += 1
        self._wrapped.set()

    async def wait(self):
        await self._wrapped.wait()


@pytest.mark.asyncio
async def test_concurrency_saturation_blocks_without_spinning():
    pool = KeyPool(keys=["a"], max_concurrency=1)
    counter = _CountingEvent(pool._free_event)
    pool._free_event = counter  # type: ignore[assignment]

    async def holder():
        async with pool.use():
            await asyncio.sleep(0.2)

    start = time.monotonic()
    holder_task = asyncio.create_task(holder())
    await asyncio.sleep(0.01)
    async with pool.use():
        pass
    await holder_task
    assert time.monotonic() - start < 0.5
    assert counter.transitions < 100


@pytest.mark.asyncio
async def test_waits_for_earliest_cooldown_recovery():
    pool = KeyPool(keys=["a", "b"], cooldown_s=0.3)
    pool.report_error("a", status=429)
    pool.report_error("b", status=429)
    start = time.monotonic()
    async with pool.use() as key:
        assert key in {"a", "b"}
        assert time.monotonic() - start >= 0.25
