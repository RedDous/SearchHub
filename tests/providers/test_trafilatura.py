import pytest

from searchhub.config import ProviderConfig
from searchhub.providers.trafilatura_py import TrafilaturaProvider


def make_provider():
    cfg = ProviderConfig(id="trafilatura", capabilities=["extract"])
    return TrafilaturaProvider(cfg, [], None)


@pytest.mark.asyncio
async def test_extract_uses_fetch_and_extract(monkeypatch):
    calls = {}

    def fake_fetch(url):
        calls["url"] = url
        return "<html><head><title>TT</title></head><body><p>Hello</p></body></html>"

    def fake_extract(html, output_format="txt"):
        calls["fmt"] = output_format
        return "Hello"

    monkeypatch.setattr("trafilatura.fetch_url", fake_fetch)
    monkeypatch.setattr("trafilatura.extract", fake_extract)
    items = await make_provider().extract(["https://a.com"], fmt="text")
    assert items[0].title == "TT"
    assert items[0].content == "Hello"
    assert calls["fmt"] == "txt"


@pytest.mark.asyncio
async def test_extract_failure_is_per_url(monkeypatch):
    def fake_fetch(url):
        raise RuntimeError("network down")

    monkeypatch.setattr("trafilatura.fetch_url", fake_fetch)
    items = await make_provider().extract(["https://a.com"])
    assert items[0].error is not None


@pytest.mark.asyncio
async def test_extract_offloaded_to_thread(monkeypatch):
    import threading
    seen = {}

    def fake_fetch(url):
        seen["t"] = threading.current_thread().name
        return "<html><title>T</title></html>"

    monkeypatch.setattr("trafilatura.fetch_url", fake_fetch)
    await make_provider().extract(["https://a.com"])
    assert seen["t"] != threading.main_thread().name
