from __future__ import annotations

from searchhub.engine.rate_limit import TokenBucket
from searchhub.models import ExtractItem, SearchItem
from searchhub.providers.base import Provider, ProviderError
from searchhub.providers.schema import ProviderSchema


class SearxngProvider(Provider):
    id = "searxng"
    capabilities = frozenset({"search"})
    REQUIRES_KEY = False
    schema = ProviderSchema(type="searxng", name="SearXNG", capabilities=("search",),
                            requires_base_url=True, key_pool_params="rps", show_max_results=True)

    def __init__(self, cfg, keys, http):
        super().__init__(cfg, keys, http)
        self._bucket = TokenBucket(cfg.key_pool.rps_limit, capacity=max(1.0, cfg.key_pool.rps_limit))

    async def extract(self, urls: list[str], *, fmt: str = "markdown",
                      max_chars: int = 15000) -> list[ExtractItem]:
        raise NotImplementedError

    async def search(self, query: str, limit: int) -> list[SearchItem]:
        if not self.cfg.base_url:
            raise ProviderError(self.id, "searxng base_url not configured")
        await self._bucket.acquire()
        url = self.cfg.base_url.rstrip("/") + "/search"
        try:
            resp = await self.http.get(url, params={"q": query, "format": "json", "safesearch": 1})
        except Exception as e:
            raise ProviderError(self.id, f"http error: {e.__class__.__name__}")
        if not 200 <= resp.status_code < 300:
            raise ProviderError(self.id, f"searxng http {resp.status_code}", status=resp.status_code)
        return [
            SearchItem(title=r.get("title", ""), url=r.get("url", ""),
                       description=r.get("content", ""), position=i, provider=self.id)
            for i, r in enumerate(resp.json().get("results", []))
        ]
