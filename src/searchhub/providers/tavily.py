from __future__ import annotations

from searchhub.models import ExtractItem, SearchItem
from searchhub.providers.base import Provider


class TavilyProvider(Provider):
    id = "tavily"
    capabilities = frozenset({"search", "extract"})
    REQUIRES_KEY = True

    async def search(self, query: str, limit: int) -> list[SearchItem]:
        raise NotImplementedError

    async def extract(self, urls: list[str], *, fmt: str = "markdown",
                      max_chars: int = 15000) -> list[ExtractItem]:
        raise NotImplementedError
