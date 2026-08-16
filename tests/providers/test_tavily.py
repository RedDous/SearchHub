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
