from __future__ import annotations

from typing import Any

from searchhub.models import ExtractItem, SearchItem
from searchhub.providers.base import Provider, ProviderError
from searchhub.providers.options import TavilyOptions
from searchhub.providers.schema import (
    AuthSpec,
    EndpointSpec,
    FieldSpec,
    ProviderSchema,
    TestSpec,
)


class TavilyProvider(Provider):
    id = "tavily"
    capabilities = frozenset({"search", "extract"})
    options_model = TavilyOptions
    schema = ProviderSchema(
        type="tavily",
        name="Tavily",
        capabilities=("search", "extract"),
        auth=AuthSpec(mode="bearer", required=True, key_prefix="tvly-"),
        endpoint=EndpointSpec(default="https://api.tavily.com", overridable=False),
        fields=(
            FieldSpec(
                key="search_depth",
                label="providers.fields.tavily.search_depth",
                help="providers.fields.tavily.search_depth.help",
                type="enum",
                default="basic",
                choices=("basic", "advanced"),
                capability="search",
                group="search",
            ),
            FieldSpec(
                key="topic",
                label="providers.fields.tavily.topic",
                help="providers.fields.tavily.topic.help",
                type="enum",
                default="general",
                choices=("general", "news", "finance"),
                capability="search",
                group="search",
            ),
            FieldSpec(
                key="include_domains",
                label="providers.fields.tavily.include_domains",
                help="providers.fields.tavily.include_domains.help",
                type="string_list",
                default=[],
                capability="search",
                group="filters",
            ),
            FieldSpec(
                key="exclude_domains",
                label="providers.fields.tavily.exclude_domains",
                help="providers.fields.tavily.exclude_domains.help",
                type="string_list",
                default=[],
                capability="search",
                group="filters",
            ),
            FieldSpec(
                key="include_answer",
                label="providers.fields.tavily.include_answer",
                help="providers.fields.tavily.include_answer.help",
                type="bool",
                default=False,
                capability="search",
                group="content",
            ),
            FieldSpec(
                key="include_raw_content",
                label="providers.fields.tavily.include_raw_content",
                help="providers.fields.tavily.include_raw_content.help",
                type="bool",
                default=False,
                capability="search",
                group="content",
            ),
            FieldSpec(
                key="days",
                label="providers.fields.tavily.days",
                help="providers.fields.tavily.days.help",
                type="int",
                default=None,
                capability="search",
                group="filters",
                advanced=True,
            ),
            FieldSpec(
                key="extract_depth",
                label="providers.fields.tavily.extract_depth",
                help="providers.fields.tavily.extract_depth.help",
                type="enum",
                default="basic",
                choices=("basic", "advanced"),
                capability="extract",
                group="extract",
            ),
            FieldSpec(
                key="include_images",
                label="providers.fields.tavily.include_images",
                help="providers.fields.tavily.include_images.help",
                type="bool",
                default=False,
                capability="extract",
                group="extract",
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
        description_key="providers.desc.tavily",
        docs_url="https://docs.tavily.com/documentation/api-reference",
    )
    SEARCH_URL = "https://api.tavily.com/search"
    EXTRACT_URL = "https://api.tavily.com/extract"

    async def search(self, query: str, limit: int) -> list[SearchItem]:
        opts = self.options
        body: dict[str, Any] = {
            "query": query,
            "max_results": limit,
            "search_depth": opts.search_depth,
            "topic": opts.topic,
            "include_answer": opts.include_answer,
            "include_raw_content": opts.include_raw_content,
        }
        if opts.include_domains:
            body["include_domains"] = opts.include_domains
        if opts.exclude_domains:
            body["exclude_domains"] = opts.exclude_domains
        if opts.days is not None:
            body["days"] = opts.days
        async with self._use_key() as key:
            headers = {"Authorization": f"Bearer {key}"}
            try:
                resp = await self.http.post(self.SEARCH_URL, json=body, headers=headers)
            except Exception as e:
                self._report(key, None)
                raise ProviderError(self.id, f"http error: {e.__class__.__name__}")
            if not 200 <= resp.status_code < 300:
                self._report(key, resp.status_code)
                raise ProviderError(self.id, f"tavily http {resp.status_code}", status=resp.status_code)
        return [
            SearchItem(title=r.get("title", ""), url=r.get("url", ""),
                       description=r.get("content", ""), position=i, provider=self.id)
            for i, r in enumerate(resp.json().get("results", []))
        ]

    async def extract(self, urls: list[str], *, fmt: str = "markdown",
                      max_chars: int = 15000) -> list[ExtractItem]:
        opts = self.options
        body: dict[str, Any] = {
            "urls": urls,
            "format": fmt,
            "extract_depth": opts.extract_depth,
            "include_images": opts.include_images,
        }
        async with self._use_key() as key:
            headers = {"Authorization": f"Bearer {key}"}
            try:
                resp = await self.http.post(self.EXTRACT_URL, json=body, headers=headers)
            except Exception as e:
                self._report(key, None)
                raise ProviderError(self.id, f"http error: {e.__class__.__name__}")
            if not 200 <= resp.status_code < 300:
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
