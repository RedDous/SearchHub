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
        return [
            SearchItem(title=r.get("title", ""), url=r.get("href", ""),
                       description=r.get("body", ""), position=i, provider=self.id)
            for i, r in enumerate(results)
        ]

    def _search_sync(self, query: str, limit: int) -> list[dict]:
        from ddgs import DDGS

        return DDGS().text(query, max_results=limit)
