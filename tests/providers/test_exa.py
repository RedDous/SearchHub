import httpx
import respx
import pytest

from searchhub.config import ProviderConfig
from searchhub.providers.base import ProviderError
from searchhub.providers.exa import ExaProvider

EXA = "https://api.exa.ai"


def make_provider():
    cfg = ProviderConfig(id="exa", capabilities=["search", "extract"])
    return ExaProvider(cfg, ["k1"], httpx.AsyncClient())


@pytest.mark.asyncio
@respx.mock
async def test_search_maps_results():
    respx.post(f"{EXA}/search").mock(return_value=httpx.Response(200, json={
        "results": [
            {"title": "T1", "url": "https://a.com", "text": "some text body", "publishedDate": "2024-01-01"},
        ]
    }))
    items = await make_provider().search("python", 3)
    assert len(items) == 1
    assert items[0].title == "T1"
    assert items[0].url == "https://a.com"
    assert items[0].description == "some text body"
    assert items[0].published_at == "2024-01-01"
    assert items[0].provider == "exa"


@pytest.mark.asyncio
@respx.mock
async def test_search_429_raises_provider_error():
    respx.post(f"{EXA}/search").mock(return_value=httpx.Response(429, json={"error": "rate"}))
    with pytest.raises(ProviderError) as ei:
        await make_provider().search("python", 3)
    assert ei.value.status == 429


@pytest.mark.asyncio
@respx.mock
async def test_search_3xx_raises_provider_error():
    respx.post(f"{EXA}/search").mock(return_value=httpx.Response(302))
    with pytest.raises(ProviderError) as ei:
        await make_provider().search("python", 3)
    assert ei.value.status == 302


@pytest.mark.asyncio
@respx.mock
async def test_extract_maps_contents_and_failures():
    respx.post(f"{EXA}/contents").mock(return_value=httpx.Response(200, json={
        "results": [{"url": "https://a.com", "title": "AT", "text": "x" * 500}],
        "failedResults": [{"url": "https://bad.com", "error": "not found"}],
    }))
    items = await make_provider().extract(["https://a.com", "https://bad.com"], max_chars=100)
    by_url = {i.url: i for i in items}
    assert by_url["https://a.com"].content == "x" * 100
    assert by_url["https://a.com"].raw_content == "x" * 500
    assert by_url["https://bad.com"].error == "not found"
