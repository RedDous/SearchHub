from __future__ import annotations

import asyncio
import re

from searchhub.engine.rate_limit import TokenBucket
from searchhub.models import ExtractItem, SearchItem
from searchhub.providers.base import Provider
from searchhub.providers.options import TrafilaturaOptions
from searchhub.providers.schema import (
    AuthSpec,
    FieldSpec,
    ProviderSchema,
    TestSpec,
)

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


class TrafilaturaProvider(Provider):
    id = "trafilatura"
    capabilities = frozenset({"extract"})
    REQUIRES_KEY = False
    options_model = TrafilaturaOptions
    schema = ProviderSchema(
        type="trafilatura",
        name="Trafilatura",
        capabilities=("extract",),
        auth=AuthSpec(mode="none"),
        fields=(
            FieldSpec(
                key="favor_precision",
                label="providers.fields.trafilatura.favor_precision",
                help="providers.fields.trafilatura.favor_precision.help",
                type="bool",
                default=False,
                capability="extract",
                group="extract",
            ),
            FieldSpec(
                key="favor_recall",
                label="providers.fields.trafilatura.favor_recall",
                help="providers.fields.trafilatura.favor_recall.help",
                type="bool",
                default=False,
                capability="extract",
                group="extract",
            ),
            FieldSpec(
                key="include_comments",
                label="providers.fields.trafilatura.include_comments",
                help="providers.fields.trafilatura.include_comments.help",
                type="bool",
                default=True,
                capability="extract",
                group="extract",
            ),
            FieldSpec(
                key="include_tables",
                label="providers.fields.trafilatura.include_tables",
                help="providers.fields.trafilatura.include_tables.help",
                type="bool",
                default=True,
                capability="extract",
                group="extract",
            ),
            FieldSpec(
                key="deduplicate",
                label="providers.fields.trafilatura.deduplicate",
                help="providers.fields.trafilatura.deduplicate.help",
                type="bool",
                default=False,
                capability="extract",
                group="advanced",
                advanced=True,
            ),
            FieldSpec(
                key="target_language",
                label="providers.fields.trafilatura.target_language",
                help="providers.fields.trafilatura.target_language.help",
                type="string",
                default=None,
                capability="extract",
                group="advanced",
                advanced=True,
            ),
        ),
        tests=(
            TestSpec(
                capability="extract",
                urls=("https://example.com",),
                expect_content=True,
            ),
        ),
        key_pool_params="rps",
        description_key="providers.desc.trafilatura",
        docs_url="https://trafilatura.readthedocs.io/en/latest/usage-python.html",
    )

    def __init__(self, cfg, keys, http):
        super().__init__(cfg, keys, http)
        self._bucket = TokenBucket(cfg.key_pool.rps_limit, capacity=max(1.0, cfg.key_pool.rps_limit))

    async def search(self, query: str, limit: int) -> list[SearchItem]:
        raise NotImplementedError

    async def extract(self, urls: list[str], *, fmt: str = "markdown",
                      max_chars: int = 15000) -> list[ExtractItem]:
        return await asyncio.gather(*(self._extract_one(u, fmt, max_chars) for u in urls))

    async def _extract_one(self, url: str, fmt: str, max_chars: int) -> ExtractItem:
        await self._bucket.acquire()
        try:
            result = await asyncio.to_thread(self._extract_sync, url, fmt)
        except Exception as e:
            return ExtractItem(url=url, error=f"trafilatura: {e.__class__.__name__}", provider=self.id)
        if result is None or result[1] is None:
            return ExtractItem(url=url, error="trafilatura: no content extracted", provider=self.id)
        html, text = result
        m = _TITLE_RE.search(html or "")
        title = m.group(1).strip() if m else ""
        return ExtractItem(url=url, title=title, content=self.truncate(text, max_chars),
                           raw_content=text, provider=self.id)

    def _extract_sync(self, url: str, fmt: str) -> tuple[str | None, str | None]:
        from trafilatura import extract, fetch_url

        html = fetch_url(url)
        text = extract(html, output_format="markdown" if fmt == "markdown" else "txt")
        return html, text
