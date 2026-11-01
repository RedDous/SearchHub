from __future__ import annotations

from typing import Any

from searchhub.engine.rate_limit import TokenBucket
from searchhub.models import ExtractItem, SearchItem
from searchhub.providers.base import Provider, ProviderError
from searchhub.providers.options import SearxngOptions
from searchhub.providers.schema import (
    AuthSpec,
    EndpointSpec,
    FieldSpec,
    ProviderSchema,
    TestSpec,
)


class SearxngProvider(Provider):
    id = "searxng"
    capabilities = frozenset({"search"})
    options_model = SearxngOptions
    schema = ProviderSchema(
        type="searxng",
        name="SearXNG",
        capabilities=("search",),
        auth=AuthSpec(mode="none"),
        endpoint=EndpointSpec(overridable=True, required=True),
        fields=(
            FieldSpec(
                key="categories",
                label="providers.fields.searxng.categories",
                help="providers.fields.searxng.categories.help",
                type="string_list",
                default=["general"],
                capability="search",
                group="search",
            ),
            FieldSpec(
                key="language",
                label="providers.fields.searxng.language",
                help="providers.fields.searxng.language.help",
                type="string",
                default="all",
                capability="search",
                group="search",
            ),
            FieldSpec(
                key="safesearch",
                label="providers.fields.searxng.safesearch",
                help="providers.fields.searxng.safesearch.help",
                type="enum",
                default="1",
                choices=("0", "1", "2"),
                capability="search",
                group="search",
            ),
            FieldSpec(
                key="time_range",
                label="providers.fields.searxng.time_range",
                help="providers.fields.searxng.time_range.help",
                type="enum",
                default="",
                choices=("", "day", "week", "month", "year"),
                capability="search",
                group="search",
            ),
            FieldSpec(
                key="engines",
                label="providers.fields.searxng.engines",
                help="providers.fields.searxng.engines.help",
                type="string_list",
                default=[],
                capability="search",
                group="advanced",
                advanced=True,
            ),
        ),
        tests=(
            TestSpec(capability="search", query="searchhub connection test"),
        ),
        key_pool_params="rps",
        description_key="providers.desc.searxng",
        docs_url="https://docs.searxng.org/dev/search_api.html",
    )

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
        opts = self.options
        params: dict[str, Any] = {
            "q": query,
            "format": "json",
            "safesearch": opts.safesearch,
            "language": opts.language,
        }
        if opts.categories:
            params["categories"] = ",".join(opts.categories)
        if opts.time_range:
            params["time_range"] = opts.time_range
        if opts.engines:
            params["engines"] = ",".join(opts.engines)
        try:
            resp = await self.http.get(url, params=params)
        except Exception as e:
            raise ProviderError(self.id, f"http error: {e.__class__.__name__}")
        if not 200 <= resp.status_code < 300:
            raise ProviderError(self.id, f"searxng http {resp.status_code}", status=resp.status_code)
        return [
            SearchItem(title=r.get("title", ""), url=r.get("url", ""),
                       description=r.get("content", ""), position=i, provider=self.id)
            for i, r in enumerate(resp.json().get("results", []))
        ]
