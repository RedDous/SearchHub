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
