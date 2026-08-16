from __future__ import annotations

from typing import Any

from searchhub.models import ExtractItem, SearchItem
from searchhub.providers.base import Provider, ProviderError


class ExaProvider(Provider):
    id = "exa"
    capabilities = frozenset({"search", "extract"})
    REQUIRES_KEY = True
    SEARCH_URL = "https://api.exa.ai/search"
    CONTENTS_URL = "https://api.exa.ai/contents"

    async def search(self, query: str, limit: int) -> list[SearchItem]:
        body = {"query": query, "num_results": limit, "type": "auto", "contents": {"text": True}}
        return await self._run(self.SEARCH_URL, body, self._map_search, limit=limit)

    async def extract(self, urls: list[str], *, fmt: str = "markdown",
                      max_chars: int = 15000) -> list[ExtractItem]:
        body = {"urls": urls, "text": True}
        return await self._run(self.CONTENTS_URL, body, self._map_extract, max_chars=max_chars)

    async def _run(self, url: str, body: dict, mapper, **kw):
        async with self._use_key() as key:
            headers = {"x-api-key": key}
            try:
                resp = await self.http.post(url, json=body, headers=headers)
            except Exception as e:
                self._report(key, None)
                raise ProviderError(self.id, f"http error: {e.__class__.__name__}")
            if resp.status_code >= 400:
                self._report(key, resp.status_code)
                raise ProviderError(self.id, f"exa http {resp.status_code}", status=resp.status_code)
        return mapper(resp.json(), **kw)

    def _use_key(self):
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def ctx():
            if self.key_pool is None:
                yield None
                return
            async with self.key_pool.use() as key:
                yield key

        return ctx()

    def _report(self, key: str | None, status: int | None) -> None:
        if key is not None and self.key_pool is not None:
            self.key_pool.report_error(key, status)

    def _map_search(self, data: dict, limit: int) -> list[SearchItem]:
        items = []
        for i, r in enumerate(data.get("results", [])):
            items.append(SearchItem(
                title=r.get("title", ""),
                url=r.get("url", ""),
                description=self.truncate(r.get("text") or "", 300),
                position=i,
                provider=self.id,
                published_at=r.get("publishedDate"),
            ))
        return items

    def _map_extract(self, data: dict, max_chars: int) -> list[ExtractItem]:
        items = []
        for r in data.get("results", []):
            raw = r.get("text") or ""
            items.append(ExtractItem(
                url=r.get("url", ""),
                title=r.get("title", ""),
                content=self.truncate(raw, max_chars),
                raw_content=raw,
                provider=self.id,
            ))
        for f in data.get("failedResults", []):
            items.append(ExtractItem(url=f.get("url", ""), error=f.get("error", "extract failed"), provider=self.id))
        return items
