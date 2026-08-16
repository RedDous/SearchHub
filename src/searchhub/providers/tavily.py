from __future__ import annotations

from searchhub.models import ExtractItem, SearchItem
from searchhub.providers.base import Provider, ProviderError


class TavilyProvider(Provider):
    id = "tavily"
    capabilities = frozenset({"search", "extract"})
    REQUIRES_KEY = True
    SEARCH_URL = "https://api.tavily.com/search"
    EXTRACT_URL = "https://api.tavily.com/extract"

    async def search(self, query: str, limit: int) -> list[SearchItem]:
        body = {"query": query, "max_results": limit, "search_depth": "basic"}
        async with self._use_key() as key:
            headers = {"Authorization": f"Bearer {key}"}
            try:
                resp = await self.http.post(self.SEARCH_URL, json=body, headers=headers)
            except Exception as e:
                self._report(key, None)
                raise ProviderError(self.id, f"http error: {e.__class__.__name__}")
            if resp.status_code >= 400:
                self._report(key, resp.status_code)
                raise ProviderError(self.id, f"tavily http {resp.status_code}", status=resp.status_code)
        return [
            SearchItem(title=r.get("title", ""), url=r.get("url", ""),
                       description=r.get("content", ""), position=i, provider=self.id)
            for i, r in enumerate(resp.json().get("results", []))
        ]

    async def extract(self, urls: list[str], *, fmt: str = "markdown",
                      max_chars: int = 15000) -> list[ExtractItem]:
        body = {"urls": urls, "format": fmt}
        async with self._use_key() as key:
            headers = {"Authorization": f"Bearer {key}"}
            try:
                resp = await self.http.post(self.EXTRACT_URL, json=body, headers=headers)
            except Exception as e:
                self._report(key, None)
                raise ProviderError(self.id, f"http error: {e.__class__.__name__}")
            if resp.status_code >= 400:
                self._report(key, resp.status_code)
                raise ProviderError(self.id, f"tavily http {resp.status_code}", status=resp.status_code)
        data = resp.json()
        items = []
        for r in data.get("results", []):
            raw = r.get("raw_content") or ""
            items.append(ExtractItem(url=r.get("url", ""), raw_content=raw,
                                     content=self.truncate(raw, max_chars), provider=self.id))
        for f in data.get("failed_results", []):
            items.append(ExtractItem(url=f.get("url", ""), error=f.get("error", "extract failed"), provider=self.id))
        return items
