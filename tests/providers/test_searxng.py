import httpx
import respx
import pytest

from searchhub.config import ProviderConfig
from searchhub.providers.base import ProviderError
from searchhub.providers.searxng import SearxngProvider


def make_provider(base_url="http://searxng:8080"):
    cfg = ProviderConfig(id="searxng", capabilities=["search"], base_url=base_url)
    return SearxngProvider(cfg, [], httpx.AsyncClient())


@pytest.mark.asyncio
@respx.mock
async def test_search_maps_results():
    respx.get("http://searxng:8080/search").mock(return_value=httpx.Response(200, json={
        "results": [{"title": "T", "url": "https://a.com", "content": "desc"}]
    }))
    items = await make_provider().search("python", 3)
    assert items[0].title == "T"
    assert items[0].url == "https://a.com"
    assert items[0].description == "desc"
    assert "format=json" in str(respx.calls[0].request.url)


@pytest.mark.asyncio
@respx.mock
async def test_search_500_raises():
    respx.get("http://searxng:8080/search").mock(return_value=httpx.Response(500))
    with pytest.raises(ProviderError):
        await make_provider().search("python", 3)


@pytest.mark.asyncio
@respx.mock
async def test_search_3xx_raises():
    respx.get("http://searxng:8080/search").mock(return_value=httpx.Response(301))
    with pytest.raises(ProviderError):
        await make_provider().search("python", 3)


@pytest.mark.asyncio
async def test_search_without_base_url_raises():
    with pytest.raises(ProviderError):
        await make_provider(base_url=None).search("python", 3)
