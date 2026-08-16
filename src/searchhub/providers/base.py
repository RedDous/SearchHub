from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any

import httpx

from searchhub.config import ProviderConfig
from searchhub.models import ExtractItem, SearchItem
from searchhub.providers.keypool import KeyPool


class ProviderError(Exception):
    def __init__(self, provider_id: str, message: str, status: int | None = None):
        super().__init__(message)
        self.provider_id = provider_id
        self.message = message
        self.status = status


class Provider(ABC):
    id: str = ""
    capabilities: frozenset[str] = frozenset()

    def __init__(self, cfg: ProviderConfig, keys: list[str], http: httpx.AsyncClient):
        self.cfg = cfg
        self.keys = keys
        self.http = http
        if keys:
            self.key_pool = KeyPool(
                keys,
                max_concurrency=cfg.key_pool.max_concurrency,
                rps_limit=cfg.key_pool.rps_limit,
                cooldown_s=cfg.key_pool.cooldown_s,
            )
        else:
            self.key_pool = None

    def supports(self, cap: str) -> bool:
        return cap in self.capabilities

    @abstractmethod
    async def search(self, query: str, limit: int) -> list[SearchItem]: ...

    @abstractmethod
    async def extract(self, urls: list[str], *, fmt: str = "markdown",
                      max_chars: int = 15000) -> list[ExtractItem]: ...

    def truncate(self, text: str, max_chars: int) -> str:
        return text[:max_chars] if max_chars and len(text) > max_chars else text

    def _use_key(self):
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
