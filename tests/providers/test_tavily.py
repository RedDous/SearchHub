import json

import httpx
import respx
import pytest

from searchhub.config import ProviderConfig
from searchhub.providers.base import ProviderError
from searchhub.providers.tavily import TavilyProvider

TAVILY = "https://api.tavily.com"


def make_provider():
    cfg = ProviderConfig(id="tavily", capabilities=["search", "extract"])
    return TavilyProvider(cfg, ["k1"], httpx.AsyncClient())


@pytest.mark.asyncio
@respx.mock
async def test_search_maps_results():
    respx.post(f"{TAVILY}/search").mock(return_value=httpx.Response(200, json={
        "results": [{"title": "T", "url": "https://a.com", "content": "desc"}]
    }))
    items = await make_provider().search("python", 3)
    assert items[0].description == "desc"
    assert items[0].provider == "tavily"
    sent = respx.calls[0].request
    assert sent.headers["authorization"] == "Bearer k1"


@pytest.mark.asyncio
@respx.mock
async def test_search_401_raises():
    respx.post(f"{TAVILY}/search").mock(return_value=httpx.Response(401, json={"error": "bad key"}))
    with pytest.raises(ProviderError) as ei:
        await make_provider().search("python", 3)
    assert ei.value.status == 401


@pytest.mark.asyncio
@respx.mock
async def test_search_3xx_raises():
    respx.post(f"{TAVILY}/search").mock(return_value=httpx.Response(302))
    with pytest.raises(ProviderError) as ei:
        await make_provider().search("python", 3)
    assert ei.value.status == 302


@pytest.mark.asyncio
@respx.mock
async def test_extract_maps_results_and_failures():
    respx.post(f"{TAVILY}/extract").mock(return_value=httpx.Response(200, json={
        "results": [{"url": "https://a.com", "raw_content": "body"}],
        "failed_results": [{"url": "https://bad.com", "error": "failed to extract"}],
    }))
    items = await make_provider().extract(["https://a.com", "https://bad.com"])
    by_url = {i.url: i for i in items}
    assert by_url["https://a.com"].content == "body"
    assert by_url["https://bad.com"].error == "failed to extract"


def make_configured(options, capabilities=("search", "extract")):
    cfg = ProviderConfig(id="tavily", type="tavily", capabilities=list(capabilities),
                         options=options)
    return TavilyProvider(cfg, ["k1"], httpx.AsyncClient())


@pytest.mark.asyncio
@respx.mock
async def test_search_uses_configured_options():
    route = respx.post(f"{TAVILY}/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    provider = make_configured({
        "search_depth": "advanced",
        "topic": "news",
        "include_domains": ["a.com"],
        "exclude_domains": ["b.com"],
        "include_answer": True,
        "include_raw_content": True,
        "days": 7,
    }, capabilities=("search",))
    await provider.search("python", 3)
    body = json.loads(route.calls[0].request.content)
    assert body["query"] == "python"
    assert body["max_results"] == 3
    assert body["search_depth"] == "advanced"
    assert body["topic"] == "news"
    assert body["include_domains"] == ["a.com"]
    assert body["exclude_domains"] == ["b.com"]
    assert body["include_answer"] is True
    assert body["include_raw_content"] is True
    assert body["days"] == 7


@pytest.mark.asyncio
@respx.mock
async def test_search_default_options_preserve_body():
    route = respx.post(f"{TAVILY}/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    await make_configured({}, capabilities=("search",)).search("python", 3)
    body = json.loads(route.calls[0].request.content)
    assert body["search_depth"] == "basic"
    assert body["topic"] == "general"
    assert body["include_answer"] is False
    assert body["include_raw_content"] is False
    for key in ("include_domains", "exclude_domains", "days"):
        assert key not in body


@pytest.mark.asyncio
@respx.mock
async def test_extract_uses_configured_options():
    route = respx.post(f"{TAVILY}/extract").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    provider = make_configured({
        "extract_depth": "advanced",
        "include_images": True,
    }, capabilities=("extract",))
    await provider.extract(["https://a.com"])
    body = json.loads(route.calls[0].request.content)
    assert body["urls"] == ["https://a.com"]
    assert body["format"] == "markdown"
    assert body["extract_depth"] == "advanced"
    assert body["include_images"] is True


@pytest.mark.asyncio
@respx.mock
async def test_extract_default_options_preserve_body():
    route = respx.post(f"{TAVILY}/extract").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    await make_configured({}, capabilities=("extract",)).extract(["https://a.com"])
    body = json.loads(route.calls[0].request.content)
    assert body["urls"] == ["https://a.com"]
    assert body["format"] == "markdown"
    assert body["extract_depth"] == "basic"
    assert body["include_images"] is False
