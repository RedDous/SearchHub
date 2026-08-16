import httpx
import respx
import pytest

from searchhub.config import ProviderConfig
from searchhub.providers.jina import JinaProvider


def make_provider(keys=None):
    cfg = ProviderConfig(id="jina", capabilities=["extract"])
    return JinaProvider(cfg, keys or [], httpx.AsyncClient())


@pytest.mark.asyncio
@respx.mock
async def test_extract_plain_text():
    respx.get("https://r.jina.ai/https://a.com").mock(
        return_value=httpx.Response(200, text="# Page Title\n\nBody text here"))
    items = await make_provider().extract(["https://a.com"])
    assert items[0].title == "Page Title"
    assert items[0].content == "Body text here"
    assert items[0].provider == "jina"


@pytest.mark.asyncio
@respx.mock
async def test_extract_sends_key_when_available():
    respx.get("https://r.jina.ai/https://a.com").mock(return_value=httpx.Response(200, text="x"))
    await make_provider(["jk"]).extract(["https://a.com"])
    assert respx.calls[0].request.headers.get("authorization") == "Bearer jk"


@pytest.mark.asyncio
@respx.mock
async def test_extract_rotates_keys_round_robin():
    respx.get("https://r.jina.ai/https://a.com").mock(return_value=httpx.Response(200, text="x"))
    provider = make_provider(["ka", "kb"])
    await provider.extract(["https://a.com"])
    await provider.extract(["https://a.com"])
    auths = [c.request.headers.get("authorization") for c in respx.calls]
    assert auths == ["Bearer ka", "Bearer kb"]


@pytest.mark.asyncio
@respx.mock
async def test_extract_3xx_is_per_url_error():
    respx.get("https://r.jina.ai/https://redirect.com").mock(return_value=httpx.Response(302))
    items = await make_provider().extract(["https://redirect.com"])
    assert items[0].error == "jina http 302"
    assert items[0].url == "https://redirect.com"


@pytest.mark.asyncio
@respx.mock
async def test_extract_failure_is_per_url():
    respx.get("https://r.jina.ai/https://bad.com").mock(return_value=httpx.Response(500))
    items = await make_provider().extract(["https://bad.com"])
    assert items[0].error is not None
    assert items[0].url == "https://bad.com"
