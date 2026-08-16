from __future__ import annotations

import logging

import httpx

from searchhub.config import AppConfig
from searchhub.providers.base import Provider

log = logging.getLogger(__name__)

PROVIDER_CLASSES: dict[str, type[Provider]] = {}


def build_registry(cfg: AppConfig, secrets: dict[str, str],
                   http: httpx.AsyncClient) -> dict[str, Provider]:
    registry: dict[str, Provider] = {}
    for pc in cfg.providers:
        if not pc.enabled:
            continue
        cls = PROVIDER_CLASSES.get(pc.id)
        if cls is None:
            log.warning("provider %s: unknown adapter class, skipped", pc.id)
            continue
        keys = [secrets[k] for k in sorted(
            (k for k in secrets if k.startswith(f"{pc.id.upper()}_KEY_") and k.rsplit("_", 1)[-1].isdigit()),
            key=lambda k: int(k.rsplit("_", 1)[-1]),
        )]
        if pc.capabilities and cls.REQUIRES_KEY and not keys:
            log.warning("provider %s: no API key configured, skipped", pc.id)
            continue
        registry[pc.id] = cls(pc, keys, http)
    return registry


def registry_for_capability(registry: dict[str, Provider], cap: str) -> list[Provider]:
    return sorted(
        (p for p in registry.values() if p.supports(cap)),
        key=lambda p: p.cfg.priority,
    )


from searchhub.providers import base  # noqa: F401  (ensure abstract base loaded)
from searchhub.providers.ddg import DdgProvider
from searchhub.providers.exa import ExaProvider
from searchhub.providers.jina import JinaProvider
from searchhub.providers.searxng import SearxngProvider
from searchhub.providers.tavily import TavilyProvider
from searchhub.providers.trafilatura_py import TrafilaturaProvider

PROVIDER_CLASSES.update({
    "exa": ExaProvider,
    "tavily": TavilyProvider,
    "ddg": DdgProvider,
    "searxng": SearxngProvider,
    "jina": JinaProvider,
    "trafilatura": TrafilaturaProvider,
})
