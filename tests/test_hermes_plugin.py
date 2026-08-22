import sys
import types
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "integrations/hermes/web-searchhub"))

# ---- hermes 契约垫片（与 agent/web_search_provider 的形状一致）----
def _install_hermes_shim() -> None:
    abc = types.ModuleType("agent.web_search_provider")
    provider_mod = types.ModuleType("agent")
    provider_mod.web_search_provider = abc
    sys.modules.setdefault("agent", provider_mod)
    sys.modules.setdefault("agent.web_search_provider", abc)
    # 在 abc 模块上定义 WebSearchProvider / get_provider_env
    code = """
from abc import ABC, abstractmethod

class WebSearchProvider(ABC):
    name = ""

    @abstractmethod
    def is_available(self) -> bool: ...

    def supports_search(self) -> bool:
        return True

    def supports_extract(self) -> bool:
        return False

    @abstractmethod
    def search(self, query: str, limit: int = 5): ...

    @abstractmethod
    def extract(self, urls, **kwargs): ...

def get_provider_env(key: str) -> str | None:
    import os
    return os.environ.get(key) or _env_file_get(key)

def _env_file_get(key: str) -> str | None:
    import os
    path = os.path.expanduser("~/.hermes/.env")
    try:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line.startswith(f"{key}="):
                return line[len(key) + 1:]
    except OSError:
        pass
    return None
"""
    exec(code, abc.__dict__)


_install_hermes_shim()

# httpx >= 0.25 移除了 Request.json()（venv 内为 0.28.1），垫一个等价实现
if not hasattr(httpx.Request, "json"):
    def _request_json(self):
        import json
        return json.loads(self.content)
    httpx.Request.json = _request_json  # type: ignore[attr-defined]

import provider  # noqa: E402


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("SEARCHHUB_URL", "http://searchhub:8000")
    monkeypatch.setenv("SEARCHHUB_TOKEN", "tok-123")


def test_is_available_requires_url_and_token(monkeypatch):
    monkeypatch.delenv("SEARCHHUB_URL", raising=False)
    monkeypatch.delenv("SEARCHHUB_TOKEN", raising=False)
    from provider import SearchHubProvider
    p = SearchHubProvider()
    assert p.is_available() is False
    monkeypatch.setenv("SEARCHHUB_URL", "http://x")
    monkeypatch.setenv("SEARCHHUB_TOKEN", "t")
    assert SearchHubProvider().is_available() is True


@pytest.mark.asyncio
async def test_search_passthrough(env):
    from provider import SearchHubProvider
    with respx.mock:
        route = respx.get("http://searchhub:8000/v1/search").mock(
            return_value=httpx.Response(200, json={"success": True, "data": {"web": [
                {"title": "T", "url": "https://a.com", "description": "D", "position": 0}]}}))
        p = SearchHubProvider()
        result = p.search("python", limit=3)
        assert result["success"] is True
        assert result["data"]["web"][0]["title"] == "T"
        sent = route.calls[0].request
        assert sent.url.params["q"] == "python"
        assert sent.headers["authorization"] == "Bearer tok-123"


@pytest.mark.asyncio
async def test_extract_passthrough_with_kwargs(env):
    from provider import SearchHubProvider
    with respx.mock:
        route = respx.post("http://searchhub:8000/v1/extract").mock(
            return_value=httpx.Response(200, json={"success": True, "data": [
                {"url": "https://a.com", "title": "T", "content": "c", "raw_content": "r", "metadata": {}}]}))
        p = SearchHubProvider()
        result = p.extract(["https://a.com"], format="markdown", max_chars=100, include_raw=True, unknown_future="x")
        assert result["success"] is True
        sent = route.calls[0].request
        body = sent.json()
        assert body["urls"] == ["https://a.com"]
        assert body["format"] == "markdown"
        assert "unknown_future" not in body


@pytest.mark.asyncio
async def test_failure_envelope(env):
    from provider import SearchHubProvider
    with respx.mock:
        respx.get("http://searchhub:8000/v1/search").mock(return_value=httpx.Response(500, json={"success": False, "error": "boom"}))
        p = SearchHubProvider()
        result = p.search("python")
        assert result["success"] is False
        assert result["error"] == "boom"


@pytest.mark.asyncio
async def test_transport_error_envelope(env):
    from provider import SearchHubProvider
    with respx.mock:
        respx.get("http://searchhub:8000/v1/search").mock(side_effect=httpx.ConnectError("down"))
        p = SearchHubProvider()
        result = p.search("python")
        assert result["success"] is False
        assert "down" in result["error"]
