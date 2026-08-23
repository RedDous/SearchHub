import time
from pathlib import Path

import pytest

from searchhub.storage.history import RequestLogRepo


@pytest.fixture
async def repo(data_dir: Path):
    r = RequestLogRepo(data_dir / "history.db")
    yield r
    await r.close()


def entry(**kw) -> dict:
    base = {"ts": time.time(), "capability": "search", "query": "python",
            "params": "{}", "providers": "exa,ddg", "cache_hit": False,
            "took_ms": 120.0, "result_count": 5, "success": True,
            "error": "", "token_name": "agent1", "response_preview": "a | b",
            "response_full": '{"items": []}'}
    base.update(kw)
    return base


@pytest.mark.asyncio
async def test_record_and_query_all_fields(repo):
    await repo.record(entry())
    rows = await repo.query()
    assert len(rows) == 1
    r = rows[0]
    assert r["capability"] == "search"
    assert r["query"] == "python"
    assert r["cache_hit"] == 0
    assert r["token_name"] == "agent1"
    assert r["success"] == 1


@pytest.mark.asyncio
async def test_query_filters(repo):
    await repo.record(entry(capability="search", providers="exa", token_name="a", ts=1000.0))
    await repo.record(entry(capability="extract", providers="ddg", token_name="b", ts=2000.0))
    await repo.record(entry(capability="extract", providers="exa", token_name="b", ts=3000.0))
    assert len(await repo.query(capability="extract")) == 2
    assert len(await repo.query(provider="exa")) == 2
    assert len(await repo.query(token="a")) == 1
    assert len(await repo.query(from_ts=1500.0, to_ts=2500.0)) == 1
    assert len(await repo.query(q="python")) == 3
    assert len(await repo.query(q="nothing")) == 0
    assert len(await repo.query(limit=2)) == 2
    assert len(await repo.query(limit=1, offset=1)) == 1


@pytest.mark.asyncio
async def test_purge_before(repo):
    await repo.record(entry(ts=100.0))
    await repo.record(entry(ts=200.0))
    assert await repo.purge_before(150.0) == 1
    assert len(await repo.query()) == 1


@pytest.mark.asyncio
async def test_summary(repo):
    await repo.record(entry(capability="search", cache_hit=True, took_ms=100.0))
    await repo.record(entry(capability="search", cache_hit=False, took_ms=300.0, success=False,
                            error="boom"))
    await repo.record(entry(capability="extract", took_ms=200.0))
    s = await repo.summary(since=0.0)
    assert s["total"] == 3
    assert s["success"] == 2
    assert s["cache_hits"] == 1
    assert s["searches"] == 2
    assert s["extracts"] == 1
    assert s["success_rate"] == round(2 / 3, 3)
    assert s["avg_took_ms"] == round(200.0, 1)


@pytest.mark.asyncio
async def test_timeseries_buckets(repo):
    await repo.record(entry(ts=100.0, cache_hit=True))
    await repo.record(entry(ts=3500.0))
    await repo.record(entry(ts=3700.0))
    rows = await repo.timeseries(since=0.0, bucket_s=3600)
    assert [r["ts"] for r in rows] == [0, 3600]
    assert rows[0]["count"] == 1 and rows[0]["cache_hits"] == 1
    assert rows[1]["count"] == 2
