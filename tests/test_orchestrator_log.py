from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from searchhub.config import ConfigService, ProviderConfig
from searchhub.models import SearchItem
from searchhub.orchestrator import SearchHubEngine
from searchhub.storage.history import RequestLogRepo


class FakeProvider:
    id = "fake"
    capabilities = frozenset({"search", "extract"})

    def __init__(self, pid, fail=False):
        self.id = pid
        self.cfg = SimpleNamespace(id=pid, capabilities=["search", "extract"],
                                   weight=10, priority=100, max_results=8)
        self.fail = fail

    def supports(self, cap):
        return cap in self.capabilities

    async def search(self, query, limit):
        if self.fail:
            from searchhub.providers.base import ProviderError
            raise ProviderError(self.id, "boom")
        return [SearchItem(title=query, url=f"https://{self.id}.com", position=0, provider=self.id)]

    async def extract(self, urls, **kw):
        from searchhub.models import ExtractItem
        return [ExtractItem(url=u, content="c", provider=self.id) for u in urls]


def make_engine(data_dir: Path, fail=False):
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.providers = [ProviderConfig(id="fake", capabilities=["search", "extract"])]
    cs.save_config(cfg)
    engine = SearchHubEngine(cs, None, httpx.AsyncClient(),
                             history=RequestLogRepo(data_dir / "history.db"))
    engine._registry = {"fake": FakeProvider("fake", fail=fail)}
    engine._version = cs.config_version
    return engine


@pytest.mark.asyncio
async def test_search_records_history(data_dir):
    eng = make_engine(data_dir)
    resp = await eng.search("python", limit=3, token_name="agent-x")
    rows = await eng.history.query()
    assert len(rows) == 1
    r = rows[0]
    assert r["capability"] == "search"
    assert r["query"] == "python"
    assert r["token_name"] == "agent-x"
    assert r["success"] == 1
    assert r["result_count"] == 1
    assert r["cache_hit"] == 0
    assert "fake" in r["providers"]
    assert "python" in r["response_preview"]


@pytest.mark.asyncio
async def test_search_records_failure(data_dir):
    eng = make_engine(data_dir, fail=True)
    resp = await eng.search("python", token_name="a")
    assert resp.success is False
    rows = await eng.history.query()
    assert rows[0]["success"] == 0
    assert "boom" in rows[0]["error"]


@pytest.mark.asyncio
async def test_extract_records_history(data_dir):
    eng = make_engine(data_dir)
    await eng.extract(["https://a.com"], token_name="b")
    rows = await eng.history.query()
    assert rows[0]["capability"] == "extract"
    assert rows[0]["query"] == "https://a.com"
    assert rows[0]["token_name"] == "b"


@pytest.mark.asyncio
async def test_redact_queries(data_dir):
    eng = make_engine(data_dir)
    eng.config.get().history.redact_queries = True
    await eng.search("secret-query", token_name="a")
    rows = await eng.history.query()
    assert rows[0]["query"] != "secret-query"
    assert len(rows[0]["query"]) == 40  # sha1 hex


@pytest.mark.asyncio
async def test_log_failure_does_not_break_request(data_dir, monkeypatch):
    eng = make_engine(data_dir)

    async def broken_record(self, entry):
        raise RuntimeError("disk full")

    monkeypatch.setattr(eng.history, "record", broken_record)
    resp = await eng.search("python", token_name="a")
    assert resp.success is True


@pytest.mark.asyncio
async def test_no_history_engine_works(data_dir):
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.providers = [ProviderConfig(id="fake", capabilities=["search", "extract"])]
    cs.save_config(cfg)
    eng = SearchHubEngine(cs, None, httpx.AsyncClient())
    eng._registry = {"fake": FakeProvider("fake")}
    eng._version = cs.config_version
    resp = await eng.search("python")
    assert resp.success is True
