import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from searchhub.config import ConfigService, ProviderConfig
from searchhub.models import SearchItem
from searchhub.orchestrator import SearchHubEngine
from searchhub.providers import build_registry


class FakeProvider:
    id = "fake"
    capabilities = frozenset({"search", "extract"})

    def __init__(self, pid, weight=10, fail=False, slow=0.0):
        self.id = pid
        self.cfg = SimpleNamespace(id=pid, capabilities=["search", "extract"],
                                   weight=weight, priority=100, max_results=8)
        self.fail = fail
        self.slow = slow
        self.calls = 0

    def supports(self, cap):
        return cap in self.capabilities

    async def search(self, query, limit):
        self.calls += 1
        if self.fail:
            from searchhub.providers.base import ProviderError
            raise ProviderError(self.id, "boom")
        if self.slow:
            await asyncio.sleep(self.slow)
        return [SearchItem(title=f"{query}-{self.id}", url=f"https://{self.id}.com",
                           position=0, provider=self.id)]

    async def extract(self, urls, **kw):
        from searchhub.models import ExtractItem
        return [ExtractItem(url=u, content=f"{self.id}:{u}", provider=self.id) for u in urls]


def make_engine(data_dir: Path, providers, strategy="fanout"):
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.providers = [ProviderConfig(id=p["id"], capabilities=["search", "extract"])
                     for p in providers]
    cfg.strategy.default_mode = strategy
    cs.save_config(cfg)
    from searchhub.storage.cache import CacheRepo
    eng = SearchHubEngine(cs, CacheRepo(data_dir / "cache.db"), httpx.AsyncClient())
    eng._registry = {p["id"]: p["obj"] for p in providers}
    eng._version = cs.config_version
    return eng


@pytest.mark.asyncio
async def test_search_fanout_merges(data_dir):
    eng = make_engine(data_dir, [
        {"id": "a", "obj": FakeProvider("a", weight=5)},
        {"id": "b", "obj": FakeProvider("b", weight=10)},
    ])
    resp = await eng.search("python")
    assert resp.success
    assert len(resp.data.web) == 2
    assert resp.data.web[0].provider == "b"
    assert resp.meta["cached"] is False


@pytest.mark.asyncio
async def test_search_fanout_tolerates_failure(data_dir):
    eng = make_engine(data_dir, [
        {"id": "a", "obj": FakeProvider("a", fail=True)},
        {"id": "b", "obj": FakeProvider("b")},
    ])
    resp = await eng.search("python")
    assert resp.success
    assert [i.provider for i in resp.data.web] == ["b"]


@pytest.mark.asyncio
async def test_search_all_fail_returns_error(data_dir):
    eng = make_engine(data_dir, [{"id": "a", "obj": FakeProvider("a", fail=True)}])
    resp = await eng.search("python")
    assert resp.success is False
    assert "a" in resp.error


@pytest.mark.asyncio
async def test_search_caches_and_hits(data_dir):
    eng = make_engine(data_dir, [{"id": "a", "obj": FakeProvider("a")}])
    r1 = await eng.search("python")
    r2 = await eng.search("python")
    assert r1.meta["cached"] is False
    assert r2.meta["cached"] is True
    assert len(r2.data.web) == 1


@pytest.mark.asyncio
async def test_search_providers_filter(data_dir):
    eng = make_engine(data_dir, [
        {"id": "a", "obj": FakeProvider("a")},
        {"id": "b", "obj": FakeProvider("b")},
    ])
    resp = await eng.search("python", providers="b")
    assert [i.provider for i in resp.data.web] == ["b"]


@pytest.mark.asyncio
async def test_extract_merges_and_caches(data_dir):
    eng = make_engine(data_dir, [{"id": "a", "obj": FakeProvider("a")}])
    r1 = await eng.extract(["https://x.com"])
    r2 = await eng.extract(["https://x.com"])
    assert r1.success and r1.data[0].content == "a:https://x.com"
    assert r2.meta["cached"] is True


@pytest.mark.asyncio
async def test_extract_rotation_mode(data_dir):
    eng = make_engine(data_dir, [
        {"id": "a", "obj": FakeProvider("a")},
        {"id": "b", "obj": FakeProvider("b")},
    ], strategy="rotation")
    resp = await eng.extract(["https://x.com"])
    assert resp.success and resp.data[0].content.endswith("https://x.com")
