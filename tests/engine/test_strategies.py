import asyncio

import pytest

from searchhub.engine.strategies import Outcome, fanout, primary_fallback, rotation
from searchhub.providers.base import ProviderError


class FakeProvider:
    def __init__(self, pid, fail=False, slow=0, items=None):
        self.id = pid
        self.fail = fail
        self.slow = slow
        self.items = items if items is not None else [{"url": pid}]

    async def call(self):
        if self.fail:
            raise ProviderError(self.id, "boom", status=500)
        if self.slow:
            await asyncio.sleep(self.slow)
        return self.items


@pytest.mark.asyncio
async def test_fanout_returns_all_outcomes():
    calls = [(p, p.call()) for p in [FakeProvider("a"), FakeProvider("b", fail=True)]]
    outcomes = await fanout(calls, timeout_s=5)
    assert {o.provider_id: o.error is None for o in outcomes} == {"a": True, "b": False}
    assert outcomes[0].items == [{"url": "a"}]


@pytest.mark.asyncio
async def test_fanout_slow_provider_times_out_independently():
    calls = [(p, p.call()) for p in [FakeProvider("a", slow=1), FakeProvider("b")]]
    outcomes = await fanout(calls, timeout_s=0.1)
    by_id = {o.provider_id: o for o in outcomes}
    assert by_id["a"].error is not None
    assert by_id["b"].items == [{"url": "b"}]


@pytest.mark.asyncio
async def test_rotation_skips_failing_and_advances_cursor():
    outcomes = []
    for _ in range(2):
        o = await rotation(
            [FakeProvider("a", fail=True), FakeProvider("b")], "search", 1.0,
            lambda p: p.call(),
        )
        outcomes.append(o.provider_id)
    assert outcomes == ["b", "b"]


@pytest.mark.asyncio
async def test_rotation_all_fail_returns_error():
    o = await rotation([FakeProvider("a", fail=True)], "search", 1.0, lambda p: p.call())
    assert o.error is not None


@pytest.mark.asyncio
async def test_primary_fallback_first_success_wins():
    o = await primary_fallback(
        [FakeProvider("a"), FakeProvider("b")], "search", 1.0, lambda p: p.call(),
    )
    assert o.provider_id == "a"


@pytest.mark.asyncio
async def test_primary_fallback_falls_through():
    o = await primary_fallback(
        [FakeProvider("a", fail=True), FakeProvider("b")], "search", 1.0,
        lambda p: p.call(),
    )
    assert o.provider_id == "b"


@pytest.mark.asyncio
async def test_fanout_repropagates_cancellation():
    async def slow_call():
        await asyncio.sleep(1)

    calls = [(FakeProvider("a"), slow_call())]
    task = asyncio.create_task(fanout(calls, timeout_s=5))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
