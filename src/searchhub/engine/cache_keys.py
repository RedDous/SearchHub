from __future__ import annotations

import hashlib


def _h(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()


def search_cache_key(query: str, limit: int, providers: str, strategy: str,
                     config_version: int) -> str:
    """Cache key for a search request.

    ``config_version`` is part of the key so that a saved configuration change
    (which bumps ``ConfigService.config_version``) does not keep serving
    results produced under different provider options. External edits to
    config files that do not bump ``config_version`` may not invalidate the
    cache; the normal save path does bump it.
    """
    return _h(f"search:{query}:{limit}:{providers}:{strategy}:{config_version}")


def extract_cache_key(url: str, fmt: str, max_chars: int, config_version: int) -> str:
    """Cache key for an extract request.

    See :func:`search_cache_key` for the role of ``config_version``.
    """
    return _h(f"extract:{url}:{fmt}:{max_chars}:{config_version}")
