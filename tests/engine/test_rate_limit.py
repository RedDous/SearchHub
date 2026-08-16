import asyncio
import time

import pytest

from searchhub.engine.rate_limit import TokenBucket


@pytest.mark.asyncio
async def test_allows_up_to_rate():
    bucket = TokenBucket(rate=10)
    start = time.monotonic()
    for _ in range(10):
        await bucket.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.5


@pytest.mark.asyncio
async def test_throttles_beyond_rate():
    bucket = TokenBucket(rate=5)
    for _ in range(5):
        await bucket.acquire()
    start = time.monotonic()
    await bucket.acquire()
    elapsed = time.monotonic() - start
    assert elapsed >= 0.15


@pytest.mark.asyncio
async def test_parallel_acquisitions_are_serialized():
    bucket = TokenBucket(rate=4, capacity=1)
    start = time.monotonic()
    await asyncio.gather(*(bucket.acquire() for _ in range(4)))
    elapsed = time.monotonic() - start
    assert elapsed >= 0.6
