import asyncio
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import yaml

from searchhub.config import AppConfig, ConfigService, ProviderConfig
from searchhub.models import SearchItem
from searchhub.orchestrator import SearchHubEngine


class FakeProvider:
    id = "fake"
    capabilities = frozenset({"search", "extract"})

    def __init__(self, pid, weight=10, fail=False, slow=0.0, empty=False):
        self.id = pid
        self.cfg = SimpleNamespace(id=pid, capabilities=["search", "extract"],
                                   weight=weight, priority=100, max_results=8)
        self.fail = fail
        self.slow = slow
        self.empty = empty
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
        if self.empty:
            return []
        return [SearchItem(title=f"{query}-{self.id}", url=f"https://{self.id}.com",
                           position=0, provider=self.id)]

    async def extract(self, urls, **kw):
        from searchhub.models import ExtractItem
        return [ExtractItem(url=u, content=f"{self.id}:{u}", provider=self.id) for u in urls]


class VersionBumpingProvider(FakeProvider):
    """Provider that saves config (bumping config_version) during extraction."""

    def __init__(self, pid, config_service):
        super().__init__(pid)
        self.config_service = config_service
        self.extract_calls = 0

    async def extract(self, urls, **kw):
        from searchhub.models import ExtractItem
        self.extract_calls += 1
        if self.extract_calls == 1:
            self.config_service.save_config(self.config_service.get())
        return [ExtractItem(url=u, content=f"call{self.extract_calls}:{u}",
                            provider=self.id) for u in urls]


class OptionsProvider(FakeProvider):
    def __init__(self, cfg):
        super().__init__(cfg.id)
        self.cfg = cfg

    async def search(self, query, limit):
        marker = self.cfg.options["region"]
        return [SearchItem(title=marker, url="https://example.com",
                           position=0, provider=self.id)]

    async def extract(self, urls, **kw):
        from searchhub.models import ExtractItem
        marker = self.cfg.options["region"]
        return [ExtractItem(url=u, content=marker, provider=self.id) for u in urls]


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


def make_restart_engine(data_dir: Path, marker: str) -> SearchHubEngine:
    from searchhub.storage.cache import CacheRepo

    if not (data_dir / "config.yaml").exists():
        data_dir.mkdir(parents=True, exist_ok=True)
        initial = AppConfig(providers=[ProviderConfig(
            id="ddg", type="ddg", capabilities=["search", "extract"],
            options={"region": "old"},
        )])
        (data_dir / "config.yaml").write_text(
            yaml.safe_dump(initial.model_dump(mode="json"), sort_keys=False)
        )
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.providers[0].options["region"] = marker
    cs.save_config(cfg)
    eng = SearchHubEngine(cs, CacheRepo(data_dir / "cache.db"), httpx.AsyncClient())
    eng._registry = {"ddg": OptionsProvider(cfg.providers[0])}
    eng._version = cs.config_version
    return eng


async def close_engine(eng: SearchHubEngine) -> None:
    await eng.http.aclose()
    if eng.cache is not None:
        await eng.cache.close()


@pytest.mark.asyncio
async def test_search_cache_does_not_reuse_version_after_restart_and_options_change(data_dir):
    first = make_restart_engine(data_dir, "old")
    try:
        assert first.config.config_version == 1
        r1 = await first.search("python")
        assert r1.data.web[0].title == "old"
    finally:
        await close_engine(first)

    second = make_restart_engine(data_dir, "new")
    try:
        assert second.config.config_version == 1
        r2 = await second.search("python")
        assert r2.meta["cached"] is False
        assert r2.data.web[0].title == "new"
    finally:
        await close_engine(second)


@pytest.mark.asyncio
async def test_extract_cache_does_not_reuse_version_after_restart_and_options_change(data_dir):
    first = make_restart_engine(data_dir, "old")
    try:
        assert first.config.config_version == 1
        r1 = await first.extract(["https://example.com"])
        assert r1.data[0].content == "old"
    finally:
        await close_engine(first)

    second = make_restart_engine(data_dir, "new")
    try:
        assert second.config.config_version == 1
        r2 = await second.extract(["https://example.com"])
        assert r2.meta["cached"] is False
        assert r2.data[0].content == "new"
    finally:
        await close_engine(second)


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
async def test_search_all_providers_zero_results_is_success(data_dir):
    eng = make_engine(data_dir, [{"id": "a", "obj": FakeProvider("a", empty=True)}])
    resp = await eng.search("python")
    assert resp.success is True
    assert resp.data.web == []


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
async def test_extract_uses_config_fingerprint_snapshot(data_dir):
    from searchhub.storage.cache import CacheRepo

    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.providers = [ProviderConfig(id="a", capabilities=["extract"])]
    cs.save_config(cfg)
    provider = VersionBumpingProvider("a", cs)
    eng = SearchHubEngine(cs, CacheRepo(data_dir / "cache.db"), httpx.AsyncClient())
    eng._registry = {"a": provider}
    eng._version = cs.config_version

    r1 = await eng.extract(["https://x.com"])
    assert r1.meta["cached"] is False
    assert r1.data[0].content == "call1:https://x.com"

    # A bookkeeping-only save does not change the effective runtime config,
    # so the result fetched under the same fingerprint is safe to serve.
    eng._registry = {"a": provider}
    eng._version = cs.config_version
    r2 = await eng.extract(["https://x.com"])
    assert r2.meta["cached"] is True
    assert r2.data[0].content == "call1:https://x.com"


def test_record_test_keeps_capabilities_separate(data_dir):
    cs = ConfigService(data_dir)
    cs.load()
    eng = SearchHubEngine(cs, None, httpx.AsyncClient())
    eng.record_test("exa", "search", success=True, count=1, took_ms=10)
    eng.record_test("exa", "extract", success=False, count=0, took_ms=20, error="boom")
    assert eng.provider_tests["exa"]["search"]["success"] is True
    assert eng.provider_tests["exa"]["extract"]["success"] is False


@pytest.mark.asyncio
async def test_real_calls_do_not_overwrite_manual_test_results(data_dir):
    eng = make_engine(data_dir, [{"id": "a", "obj": FakeProvider("a")}])
    try:
        eng.record_test("a", "search", success=False, count=0, took_ms=5,
                        error="manual search")
        eng.record_test("a", "extract", success=False, count=0, took_ms=6,
                        error="manual extract")
        manual = deepcopy(eng.provider_tests)

        await eng.search("python")
        await eng.extract(["https://x.com"])

        assert eng.provider_tests == manual
        assert eng.stats["a"]["calls"] == 2
    finally:
        await close_engine(eng)


def test_provider_status_reports_instance_capabilities_and_tests(data_dir):
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.providers = [ProviderConfig(id="ddg-work", type="ddg", capabilities=["search"])]
    cs.save_config(cfg)
    eng = SearchHubEngine(cs, None, httpx.AsyncClient())
    eng.record_test("ddg-work", "search", success=True, count=1, took_ms=10)
    entry = next(e for e in eng.provider_status() if e["id"] == "ddg-work")
    assert entry["type"] == "ddg"
    assert entry["capabilities"] == ["search"]
    assert entry["tests"]["search"]["success"] is True


@pytest.mark.asyncio
async def test_extract_rotation_mode(data_dir):
    eng = make_engine(data_dir, [
        {"id": "a", "obj": FakeProvider("a")},
        {"id": "b", "obj": FakeProvider("b")},
    ], strategy="rotation")
    resp = await eng.extract(["https://x.com"])
    assert resp.success and resp.data[0].content.endswith("https://x.com")
