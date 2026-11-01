import pytest

from searchhub.config import ProviderConfig
from searchhub.providers.ddg import DdgProvider


class FakeDDGS:
    def __init__(self, results):
        self.results = results

    def text(self, query, max_results=10, **kw):
        return self.results


def make_provider():
    cfg = ProviderConfig(id="ddg", capabilities=["search"])
    return DdgProvider(cfg, [], None)


@pytest.mark.asyncio
async def test_search_maps_href_and_body(monkeypatch):
    monkeypatch.setattr("ddgs.DDGS", lambda *a, **kw: FakeDDGS([
        {"title": "T1", "href": "https://a.com", "body": "desc1"},
        {"title": "T2", "href": "https://b.com", "body": "desc2"},
    ]))
    items = await make_provider().search("python", 3)
    assert [i.title for i in items] == ["T1", "T2"]
    assert items[0].url == "https://a.com"
    assert items[0].description == "desc1"
    assert items[0].position == 0
    assert items[1].position == 1


@pytest.mark.asyncio
async def test_search_empty_results(monkeypatch):
    monkeypatch.setattr("ddgs.DDGS", lambda *a, **kw: FakeDDGS([]))
    assert await make_provider().search("nothing", 3) == []


@pytest.mark.asyncio
async def test_search_is_offloaded_to_thread(monkeypatch):
    import threading
    seen = {}
    class TDDGS(FakeDDGS):
        def text(self, query, max_results=10, **kw):
            seen["thread"] = threading.current_thread().name
            return []
    monkeypatch.setattr("ddgs.DDGS", lambda *a, **kw: TDDGS([]))
    await make_provider().search("python", 3)
    assert seen["thread"] != threading.main_thread().name


def make_provider_with_options(**options):
    cfg = ProviderConfig(id="ddg", type="ddg", capabilities=["search"],
                         options=options)
    return DdgProvider(cfg, [], None)


def capture_kwargs(monkeypatch):
    captured = {}

    class CapturingDDGS:
        def text(self, query, **kwargs):
            captured.update(kwargs)
            return []

    monkeypatch.setattr("ddgs.DDGS", lambda *a, **kw: CapturingDDGS())
    return captured


def test_search_passes_configured_kwargs(monkeypatch):
    captured = capture_kwargs(monkeypatch)
    make_provider_with_options(region="cn-zh", safesearch="off")._search_sync("q", 5)
    assert captured["region"] == "cn-zh"
    assert captured["safesearch"] == "off"


def test_search_passes_all_configured_kwargs(monkeypatch):
    captured = capture_kwargs(monkeypatch)
    make_provider_with_options(
        region="us-en", safesearch="on", timelimit="w", backend="duckduckgo",
    )._search_sync("q", 5)
    assert captured == {
        "max_results": 5,
        "region": "us-en",
        "safesearch": "on",
        "timelimit": "w",
        "backend": "duckduckgo",
    }


def test_search_omits_unset_kwargs_with_default_options(monkeypatch):
    captured = capture_kwargs(monkeypatch)
    make_provider()._search_sync("q", 5)
    assert captured == {"max_results": 5, "safesearch": "moderate"}
