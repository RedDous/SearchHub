from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from searchhub.engine.strategies import Outcome
from searchhub.models import ExtractItem, SearchItem
from searchhub.providers.base import Provider

_TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}


def normalize_url(url: str) -> str:
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in _TRACKING]
    path = parts.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, urlencode(query), ""))


def _weight(providers: dict[str, Provider], pid: str) -> int:
    p = providers.get(pid)
    return p.cfg.weight if p else 1


def merge_search(outcomes: list[Outcome], limit: int,
                 providers: dict[str, Provider]) -> list[SearchItem]:
    best: dict[str, SearchItem] = {}
    for out in outcomes:
        if out.error or not out.items:
            continue
        w = _weight(providers, out.provider_id)
        for item in out.items:
            key = normalize_url(item.url)
            prev = best.get(key)
            if prev is None or _weight(providers, prev.provider) < w:
                item.score = w * (1 - min(item.position, 49) / 50)
                best[key] = item
            elif prev and len(prev.title) < len(item.title) and prev.provider == item.provider:
                best[key] = item
    ranked = sorted(best.values(), key=lambda i: i.score, reverse=True)
    return ranked[:limit]


def merge_extract(outcomes: list[Outcome], urls: list[str],
                  providers: dict[str, Provider]) -> list[ExtractItem]:
    by_url: dict[str, ExtractItem] = {}
    first_error: dict[str, str] = {}
    for out in outcomes:
        if out.error:
            for url in urls:
                first_error.setdefault(url, out.error)
            continue
        if not out.items:
            continue
        w = _weight(providers, out.provider_id)
        for item in out.items:
            if item.error is not None:
                first_error.setdefault(item.url, item.error)
                continue
            prev = by_url.get(item.url)
            if prev is None or _weight(providers, prev.provider) < w:
                by_url[item.url] = item
    result: list[ExtractItem] = []
    for url in urls:
        item = by_url.get(url)
        if item is None:
            result.append(ExtractItem(url=url, error=first_error.get(url) or "all providers failed"))
        else:
            result.append(item)
    return result
