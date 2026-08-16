from searchhub.config import ProviderConfig
from searchhub.engine.merge import merge_extract, merge_search, normalize_url
from searchhub.engine.strategies import Outcome
from searchhub.models import ExtractItem, SearchItem
from searchhub.providers.base import Provider


class _FakeProvider(Provider):
    async def search(self, query: str, limit: int) -> list[SearchItem]:
        return []

    async def extract(self, urls: list[str], *, fmt: str = "markdown",
                      max_chars: int = 15000) -> list[ExtractItem]:
        return []


def make_provider(pid, weight):
    p = _FakeProvider.__new__(_FakeProvider)
    p.id = pid
    p.cfg = ProviderConfig(id=pid, capabilities=["search"], weight=weight)
    return p


def test_normalize_url():
    assert normalize_url("HTTP://Example.com/path/") == "http://example.com/path"
    assert normalize_url("https://a.com/x?utm_source=1&q=2#top") == "https://a.com/x?q=2"
    assert normalize_url("https://a.com/x?fbclid=abc") == "https://a.com/x"


def test_merge_search_dedups_and_ranks():
    low = make_provider("ddg", 5)
    high = make_provider("exa", 10)
    items_low = [SearchItem(title="t", url="https://a.com/x", position=0, provider="ddg")]
    items_high = [
        SearchItem(title="better title here", url="https://a.com/x", position=0, provider="exa"),
        SearchItem(title="unique", url="https://b.com", position=1, provider="exa"),
    ]
    merged = merge_search(
        [Outcome("ddg", items_low), Outcome("exa", items_high)], 5,
        {"ddg": low, "exa": high},
    )
    assert len(merged) == 2
    assert merged[0].url == "https://a.com/x"  # 去重后保留高权重来源，且位置靠前得分最高
    assert merged[0].provider == "exa"
    assert merged[0].title == "better title here"
    assert merged[1].url == "https://b.com"


def test_merge_search_truncates_to_limit():
    prov = make_provider("exa", 10)
    items = [SearchItem(title=str(i), url=f"https://a.com/{i}", position=i, provider="exa") for i in range(5)]
    merged = merge_search([Outcome("exa", items)], 2, {"exa": prov})
    assert len(merged) == 2


def test_merge_extract_picks_best_provider_per_url():
    low = make_provider("jina", 5)
    high = make_provider("exa", 10)
    outcomes = [
        Outcome("jina", [ExtractItem(url="https://a.com", content="short", provider="jina")]),
        Outcome("exa", [ExtractItem(url="https://a.com", content="full content", provider="exa"),
                        ExtractItem(url="https://b.com", content="b", provider="exa")]),
    ]
    merged = merge_extract(outcomes, ["https://a.com", "https://b.com"], {"jina": low, "exa": high})
    assert [m.url for m in merged] == ["https://a.com", "https://b.com"]
    assert merged[0].provider == "exa"
    assert merged[1].content == "b"


def test_merge_extract_error_item_when_all_fail():
    prov = make_provider("jina", 5)
    outcomes = [Outcome("jina", None, error="boom")]
    merged = merge_extract(outcomes, ["https://a.com"], {"jina": prov})
    assert merged[0].error == "boom"
    assert merged[0].url == "https://a.com"
