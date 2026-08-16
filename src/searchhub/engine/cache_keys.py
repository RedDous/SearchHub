from __future__ import annotations

import hashlib


def _h(s: str) -> str:
    return hashlib.sha1(s.encode()).hexdigest()


def search_cache_key(query: str, limit: int, providers: str, strategy: str) -> str:
    return _h(f"search:{query}:{limit}:{providers}:{strategy}")


def extract_cache_key(url: str, fmt: str, max_chars: int) -> str:
    return _h(f"extract:{url}:{fmt}:{max_chars}")
