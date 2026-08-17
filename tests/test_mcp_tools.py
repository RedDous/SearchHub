import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from searchhub.config import ConfigService, ProviderConfig
from searchhub.mcp_server import _get_engine, set_engine
from searchhub.models import SearchItem
from searchhub.orchestrator import SearchHubEngine


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
    engine = SearchHubEngine(cs, None, httpx.AsyncClient())
    engine._registry = {"fake": FakeProvider("fake", fail=fail)}
    engine._version = cs.config_version
    return engine


@pytest.fixture
def engine(data_dir: Path):
    e = make_engine(data_dir)
    set_engine(e)
    yield e
    set_engine(None)  # 钩子复位——set_engine 需支持传 None 清除


async def _call_tool(mcp, name, **kwargs):
    result = await mcp.call_tool(name, kwargs)
    sc = result.structured_content
    if sc is not None and "result" in sc:
        return sc["result"]
    return result.content[0].text


async def test_web_search_tool_returns_json_string(engine):
    from searchhub.mcp_server import create_mcp_server

    mcp = create_mcp_server()
    tools = {t.name: t for t in await mcp.list_tools()}
    assert "web_search" in tools and "web_extract" in tools
    result = await _call_tool(mcp, "web_search", query="python", limit=3)
    assert isinstance(result, str)
    data = json.loads(result)
    assert data["web"][0]["title"] == "python"
    assert data["web"][0]["url"] == "https://fake.com"


async def test_web_search_tool_failure_json(engine):
    from searchhub.mcp_server import create_mcp_server

    engine._registry["fake"].fail = True
    mcp = create_mcp_server()
    tools = {t.name: t for t in await mcp.list_tools()}
    result = json.loads(await _call_tool(mcp, "web_search", query="python", limit=3))
    assert result["success"] is False
    assert "boom" in result["error"]


async def test_web_extract_tool_returns_json_string(engine):
    from searchhub.mcp_server import create_mcp_server

    mcp = create_mcp_server()
    tools = {t.name: t for t in await mcp.list_tools()}
    result = json.loads(await _call_tool(mcp, "web_extract", urls=["https://a.com"], format="markdown", max_chars=15000))
    assert result[0]["url"] == "https://a.com"
    assert result[0]["content"] == "c"


async def test_get_engine_raises_when_unset():
    from searchhub.mcp_server import _get_engine

    set_engine(None)
    with pytest.raises(RuntimeError):
        _get_engine()