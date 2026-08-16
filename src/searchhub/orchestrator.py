from __future__ import annotations

import json
import time
from typing import Any

import httpx

from searchhub.config import ConfigService
from searchhub.engine.cache_keys import extract_cache_key, search_cache_key
from searchhub.engine.merge import merge_extract, merge_search
from searchhub.engine.strategies import Outcome, fanout, primary_fallback, rotation
from searchhub.models import (ExtractItem, ExtractResponse, SearchData,
                              SearchItem, SearchResponse)
from searchhub.providers import build_registry, registry_for_capability
from searchhub.providers.base import Provider
from searchhub.storage.cache import CacheRepo


class SearchHubEngine:
    def __init__(self, config: ConfigService, cache: CacheRepo | None, http: httpx.AsyncClient):
        self.config = config
        self.cache = cache
        self.http = http
        self._registry: dict[str, Provider] = {}
        self._version = -1
        self.stats: dict[str, dict[str, Any]] = {}

    def maybe_reload(self) -> bool:
        if self.config.maybe_reload() or self._version != self.config.config_version:
            self._registry = build_registry(self.config.get(), self.config.secrets(), self.http)
            self._version = self.config.config_version
            return True
        return False

    def _registry_for(self, cap: str) -> list[Provider]:
        self.maybe_reload()
        return registry_for_capability(self._registry, cap)

    def _filter(self, providers: list[Provider], only: str | None) -> list[Provider]:
        if not only:
            return providers
        wanted = {p.strip() for p in only.split(",") if p.strip()}
        return [p for p in providers if p.id in wanted]

    def _record(self, provider_id: str, ok: bool, took_ms: float) -> None:
        s = self.stats.setdefault(provider_id, {"calls": 0, "errors": 0, "sum_ms": 0.0})
        s["calls"] += 1
        s["sum_ms"] += took_ms
        if not ok:
            s["errors"] += 1

    async def search(self, query: str, limit: int = 5, providers: str | None = None,
                     strategy: str | None = None, cache: bool = True,
                     timeout: float | None = None) -> SearchResponse:
        start = time.monotonic()
        cfg = self.config.get()
        providers_list = self._filter(self._registry_for("search"), providers)
        if not providers_list:
            return SearchResponse(success=False, data=SearchData(web=[]),
                                  error=f"no search provider enabled",
                                  meta={"took_ms": 0})
        mode = strategy or cfg.strategy.default_mode
        t = timeout or cfg.strategy.timeout_s
        cache_key = search_cache_key(query, limit, providers or "all", mode)
        outcomes: list[Outcome] = []
        if self.cache and cache:
            hit = await self.cache.get(cache_key)
            if hit is not None:
                items = [SearchItem(**d) for d in json.loads(hit)]
                return SearchResponse(success=True, data=SearchData(web=items),
                                      meta={"took_ms": 0, "cached": True})
        if mode == "fanout":
            calls = [(p, p.search(query, min(limit, p.cfg.max_results))) for p in providers_list]
            outcomes = await fanout(calls, t)
        else:
            def call(p: Provider):
                return p.search(query, min(limit, p.cfg.max_results))

            if mode == "rotation":
                outcomes = [await rotation(providers_list, "search", t, call)]
            else:
                outcomes = [await primary_fallback(providers_list, "search", t, call)]
        for o in outcomes:
            self._record(o.provider_id, o.error is None, o.took_ms)
        if not any(o.items for o in outcomes if not o.error):
            details = "; ".join(f"{o.provider_id}: {o.error}" for o in outcomes)
            return SearchResponse(success=False, data=SearchData(web=[]), error=details,
                                  meta={"took_ms": (time.monotonic() - start) * 1000})
        merged = merge_search(outcomes, limit, self._registry)
        if self.cache and cache:
            await self.cache.put(cache_key, json.dumps([i.model_dump() for i in merged]),
                                 cfg.cache.search_ttl_s)
        return SearchResponse(success=True, data=SearchData(web=merged),
                              meta={"took_ms": (time.monotonic() - start) * 1000,
                                    "cached": False,
                                    "provider_stats": {
                                        o.provider_id: {"success": o.error is None,
                                                        "took_ms": round(o.took_ms, 1),
                                                        "count": len(o.items) if o.items else 0,
                                                        "error": o.error}
                                        for o in outcomes}})

    async def extract(self, urls: list[str], fmt: str = "markdown", max_chars: int = 15000,
                      strategy: str | None = None, cache: bool = True,
                      timeout: float | None = None) -> ExtractResponse:
        start = time.monotonic()
        cfg = self.config.get()
        providers_list = self._filter(self._registry_for("extract"), None)
        if not providers_list:
            return ExtractResponse(success=False,
                                   data=[ExtractItem(url=u, error="no extract provider enabled") for u in urls],
                                   meta={"took_ms": 0})
        mode = strategy or cfg.strategy.default_mode
        t = timeout or cfg.strategy.timeout_s
        final_items: list[ExtractItem] = []
        cached_any = False
        remaining: list[str] = []
        if self.cache and cache:
            for url in urls:
                hit = await self.cache.get(extract_cache_key(url, fmt, max_chars))
                if hit is not None:
                    final_items.append(ExtractItem(**json.loads(hit)))
                    cached_any = True
                else:
                    remaining.append(url)
        else:
            remaining = urls
        if remaining:
            if mode == "fanout":
                calls = [(p, p.extract(remaining, fmt=fmt, max_chars=max_chars)) for p in providers_list]
                outcomes = await fanout(calls, t)
            else:
                def call(p: Provider):
                    return p.extract(remaining, fmt=fmt, max_chars=max_chars)

                if mode == "rotation":
                    outcomes = [await rotation(providers_list, "extract", t, call)]
                else:
                    outcomes = [await primary_fallback(providers_list, "extract", t, call)]
            for o in outcomes:
                self._record(o.provider_id, o.error is None, o.took_ms)
            merged = merge_extract(outcomes, remaining, self._registry)
            if self.cache and cache:
                for item in merged:
                    if item.error is None:
                        await self.cache.put(extract_cache_key(item.url, fmt, max_chars),
                                             json.dumps(item.model_dump()), cfg.cache.extract_ttl_s)
            final_items.extend(merged)
        return ExtractResponse(success=True, data=final_items,
                               meta={"took_ms": (time.monotonic() - start) * 1000,
                                     "cached": cached_any})

    def provider_status(self) -> list[dict]:
        self.maybe_reload()
        result = []
        for pid, p in sorted(self._registry.items()):
            entry = {
                "id": pid,
                "capabilities": sorted(p.capabilities),
                "weight": p.cfg.weight,
                "priority": p.cfg.priority,
                "keys": [],
            }
            if p.key_pool is not None:
                entry["keys"] = p.key_pool.status()
            s = self.stats.get(pid)
            if s:
                entry["stats"] = {"calls": s["calls"], "errors": s["errors"],
                                  "avg_ms": round(s["sum_ms"] / max(1, s["calls"]), 1)}
            result.append(entry)
        return result
