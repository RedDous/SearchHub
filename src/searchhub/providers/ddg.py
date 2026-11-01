from __future__ import annotations

import asyncio

from searchhub.models import ExtractItem, SearchItem
from searchhub.providers.base import Provider
from searchhub.providers.options import DdgOptions
from searchhub.providers.schema import (
    AuthSpec,
    FieldSpec,
    ProviderSchema,
    TestSpec,
)


class DdgProvider(Provider):
    id = "ddg"
    capabilities = frozenset({"search"})
    REQUIRES_KEY = False
    options_model = DdgOptions
    schema = ProviderSchema(
        type="ddg",
        name="DuckDuckGo",
        capabilities=("search",),
        auth=AuthSpec(mode="none"),
        fields=(
            FieldSpec(
                key="region",
                label="providers.fields.ddg.region",
                help="providers.fields.ddg.region.help",
                type="string",
                default=None,
                capability="search",
                group="search",
            ),
            FieldSpec(
                key="safesearch",
                label="providers.fields.ddg.safesearch",
                help="providers.fields.ddg.safesearch.help",
                type="enum",
                default="moderate",
                choices=("on", "moderate", "off"),
                capability="search",
                group="search",
            ),
            FieldSpec(
                key="timelimit",
                label="providers.fields.ddg.timelimit",
                help="providers.fields.ddg.timelimit.help",
                type="enum",
                default="",
                choices=("", "d", "w", "m", "y"),
                capability="search",
                group="search",
            ),
            FieldSpec(
                key="backend",
                label="providers.fields.ddg.backend",
                help="providers.fields.ddg.backend.help",
                type="string",
                default=None,
                capability="search",
                group="advanced",
                advanced=True,
            ),
        ),
        tests=(
            TestSpec(capability="search", query="searchhub connection test"),
        ),
        description_key="providers.desc.ddg",
        docs_url="https://github.com/deedy5/ddgs",
    )

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
