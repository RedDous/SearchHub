from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from searchhub.config import AppConfig


def _h(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()


def config_fingerprint(config: AppConfig) -> str:
    """Hash the effective runtime configuration, excluding secrets and settings
    that do not affect provider execution."""
    runtime = {
        "providers": [p.model_dump(mode="json") for p in config.providers],
        "strategy": config.strategy.model_dump(mode="json"),
    }
    canonical = json.dumps(runtime, ensure_ascii=False, sort_keys=True,
                           separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def search_cache_key(query: str, limit: int, providers: str, strategy: str,
                     fingerprint: str) -> str:
    """Cache key for a search request under one runtime configuration."""
    return _h(f"search:{query}:{limit}:{providers}:{strategy}:{fingerprint}")


def extract_cache_key(url: str, fmt: str, max_chars: int, fingerprint: str) -> str:
    """Cache key for an extract request under one runtime configuration."""
    return _h(f"extract:{url}:{fmt}:{max_chars}:{fingerprint}")
