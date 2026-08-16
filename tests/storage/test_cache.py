import time
from pathlib import Path

import pytest

from searchhub.engine.cache_keys import extract_cache_key, search_cache_key
from searchhub.storage.cache import CacheRepo


@pytest.fixture
async def repo(data_dir: Path):
    r = CacheRepo(data_dir / "cache.db")
    yield r
    await r.close()


@pytest.mark.asyncio
async def test_put_get_roundtrip(repo):
    await repo.put("k1", "v1", ttl_s=600)
    assert await repo.get("k1") == "v1"


@pytest.mark.asyncio
async def test_expired_entry_purged(repo):
    await repo.put("k1", "v1", ttl_s=1)
    time.sleep(1.1)
    assert await repo.purge_expired() == 1
    assert await repo.get("k1") is None


@pytest.mark.asyncio
async def test_overwrite_extends(repo):
    await repo.put("k1", "v1", ttl_s=60)
    await repo.put("k1", "v2", ttl_s=60)
    assert await repo.get("k1") == "v2"


@pytest.mark.asyncio
async def test_cache_keys_stable_and_distinct():
    assert search_cache_key("q", 5, "all", "fanout") == search_cache_key("q", 5, "all", "fanout")
    assert search_cache_key("q", 5, "all", "fanout") != search_cache_key("q", 5, "all", "rotation")
    assert extract_cache_key("https://a.com", "markdown", 1000) != extract_cache_key("https://a.com", "text", 1000)
