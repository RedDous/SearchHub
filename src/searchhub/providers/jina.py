from __future__ import annotations

import re

from searchhub.models import ExtractItem, SearchItem
from searchhub.providers.base import Provider

_TITLE_RE = re.compile(r"^#+\s*(.+?)\s*$", re.M)


class JinaProvider(Provider):
    id = "jina"
    capabilities = frozenset({"extract"})
    REQUIRES_KEY = False
    BASE = "https://r.jina.ai/"

    async def search(self, query: str, limit: int) -> list[SearchItem]:
        raise NotImplementedError

    async def extract(self, urls: list[str], *, fmt: str = "markdown",
                      max_chars: int = 15000) -> list[ExtractItem]:
        items: list[ExtractItem] = []
        for url in urls:
            items.append(await self._extract_one(url, fmt, max_chars))
        return items

    async def _extract_one(self, url: str, fmt: str, max_chars: int) -> ExtractItem:
        headers = {"X-Return-Format": fmt}
        try:
            async with self._use_key() as k:
                if k is not None:
                    headers["Authorization"] = f"Bearer {k}"
                resp = await self.http.get(self.BASE + url, headers=headers)
            if not 200 <= resp.status_code < 300:
                if k is not None:
                    self._report(k, resp.status_code)
                return ExtractItem(url=url, error=f"jina http {resp.status_code}", provider=self.id)
        except Exception as e:
            return ExtractItem(url=url, error=f"jina: {e.__class__.__name__}", provider=self.id)
        text = resp.text
        title = ""
        m = _TITLE_RE.match(text.strip())
        if m:
            title = m.group(1)
            text = text[m.end():].lstrip()
        return ExtractItem(url=url, title=title, content=self.truncate(text, max_chars),
                           raw_content=text, provider=self.id)
