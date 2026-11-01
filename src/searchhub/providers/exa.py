from __future__ import annotations

from typing import Any

from searchhub.models import ExtractItem, SearchItem
from searchhub.providers.base import Provider, ProviderError
from searchhub.providers.options import ExaOptions
from searchhub.providers.schema import (
    AuthSpec,
    EndpointSpec,
    FieldSpec,
    ProviderSchema,
    TestSpec,
)


class ExaProvider(Provider):
    id = "exa"
    capabilities = frozenset({"search", "extract"})
    options_model = ExaOptions
    schema = ProviderSchema(
        type="exa",
        name="Exa",
        capabilities=("search", "extract"),
        auth=AuthSpec(mode="header", header_name="x-api-key", required=True),
        endpoint=EndpointSpec(default="https://api.exa.ai", overridable=False),
        fields=(
            FieldSpec(
                key="search_type",
                label="providers.fields.exa.search_type",
                help="providers.fields.exa.search_type.help",
                type="enum",
                default="auto",
                choices=("auto", "lite", "deep"),
                capability="search",
                group="search",
            ),
            FieldSpec(
                key="category",
                label="providers.fields.exa.category",
                help="providers.fields.exa.category.help",
                type="string",
                default=None,
                capability="search",
                group="search",
            ),
            FieldSpec(
                key="include_domains",
                label="providers.fields.exa.include_domains",
                help="providers.fields.exa.include_domains.help",
                type="string_list",
                default=[],
                capability="search",
                group="filters",
            ),
            FieldSpec(
                key="exclude_domains",
                label="providers.fields.exa.exclude_domains",
                help="providers.fields.exa.exclude_domains.help",
                type="string_list",
                default=[],
                capability="search",
                group="filters",
            ),
            FieldSpec(
                key="start_published_date",
                label="providers.fields.exa.start_published_date",
                help="providers.fields.exa.start_published_date.help",
                type="string",
                default=None,
                capability="search",
                group="filters",
                advanced=True,
            ),
            FieldSpec(
                key="end_published_date",
                label="providers.fields.exa.end_published_date",
                help="providers.fields.exa.end_published_date.help",
                type="string",
                default=None,
                capability="search",
                group="filters",
                advanced=True,
            ),
            FieldSpec(
                key="include_text",
                label="providers.fields.exa.include_text",
                help="providers.fields.exa.include_text.help",
                type="bool",
                default=True,
                group="content",
            ),
            FieldSpec(
                key="include_highlights",
                label="providers.fields.exa.include_highlights",
                help="providers.fields.exa.include_highlights.help",
                type="bool",
                default=False,
                group="content",
            ),
            FieldSpec(
                key="include_summary",
                label="providers.fields.exa.include_summary",
                help="providers.fields.exa.include_summary.help",
                type="bool",
                default=False,
                group="content",
            ),
        ),
        tests=(
            TestSpec(capability="search", query="searchhub connection test"),
            TestSpec(
                capability="extract",
                urls=("https://example.com",),
                expect_content=True,
            ),
        ),
        key_pool_params="full",
        description_key="providers.desc.exa",
        docs_url="https://docs.exa.ai/reference/search",
    )
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
            if not 200 <= resp.status_code < 300:
                self._report(key, resp.status_code)
                raise ProviderError(self.id, f"exa http {resp.status_code}", status=resp.status_code)
        return mapper(resp.json(), **kw)

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
