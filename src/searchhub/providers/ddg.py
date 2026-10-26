from __future__ import annotations

import asyncio

from searchhub.models import ExtractItem, SearchItem
from searchhub.providers.base import Provider
from searchhub.providers.schema import ProviderSchema


class DdgProvider(Provider):
    id = "ddg"
    capabilities = frozenset({"search"})
    REQUIRES_KEY = False
    schema = ProviderSchema(type="ddg", name="DuckDuckGo", capabilities=("search",),
                            show_max_results=True)

    async def extract(self, urls: list[str], *, fmt: str = "markdown",
                      max_chars: int = 15000) -> list[ExtractItem]:
        raise NotImplementedError

    async def search(self, query: str, limit: int) -> list[SearchItem]:
        try:
            results = await asyncio.to_thread(self._search_sync, query, limit)
        except Exception as e:
            raise type(e)(f"ddg: {e}") from e
        items: list[SearchItem] = []
        for r in results:
            if not isinstance(r, dict):
                continue
            url = (r.get("href") or r.get("url") or "").strip()
            if not url:  # ddgs 偶发返回空条目，直接丢弃
                continue
            title = (r.get("title") or "").strip()
            items.append(SearchItem(title=title or url, url=url,
                                    description=r.get("body") or "",
                                    position=len(items), provider=self.id))
        return items

    def _search_sync(self, query: str, limit: int) -> list[dict]:
        from ddgs import DDGS

        return DDGS().text(query, max_results=limit)
