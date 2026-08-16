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
