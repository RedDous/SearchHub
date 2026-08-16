from __future__ import annotations

import asyncio
import re

from searchhub.engine.rate_limit import TokenBucket
from searchhub.models import ExtractItem, SearchItem
from searchhub.providers.base import Provider

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


class TrafilaturaProvider(Provider):
    id = "trafilatura"
    capabilities = frozenset({"extract"})
    REQUIRES_KEY = False

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
