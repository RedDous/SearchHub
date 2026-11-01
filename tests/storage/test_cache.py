import time
from pathlib import Path

import pytest

from searchhub.config import AppConfig, ProviderConfig
from searchhub.engine.cache_keys import config_fingerprint, extract_cache_key, search_cache_key
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
    assert search_cache_key("q", 5, "all", "fanout", "fp") == \
        search_cache_key("q", 5, "all", "fanout", "fp")
    assert search_cache_key("q", 5, "all", "fanout", "fp") != \
        search_cache_key("q", 5, "all", "rotation", "fp")
    assert extract_cache_key("https://a.com", "markdown", 1000, "fp") != \
        extract_cache_key("https://a.com", "text", 1000, "fp")


def test_config_fingerprint_changes_keys():
    a = search_cache_key("q", 5, "all", "fanout", "old")
    b = search_cache_key("q", 5, "all", "fanout", "new")
    assert a != b
    assert extract_cache_key("https://a.com", "markdown", 1000, "old") != \
        extract_cache_key("https://a.com", "markdown", 1000, "new")


def test_config_fingerprint_is_stable_and_tracks_runtime_configuration():
    original = AppConfig(providers=[ProviderConfig(
        id="exa", type="exa", capabilities=["search"],
        base_url="https://api.exa.ai", weight=10,
        options={"search_type": "auto"},
    )])
    restored = AppConfig.model_validate(original.model_dump(mode="json"))
    assert config_fingerprint(original) == config_fingerprint(restored)

    mutations = (
        lambda c: c.providers[0].options.update(search_type="deep"),
        lambda c: setattr(c.providers[0], "base_url", "https://proxy.example"),
        lambda c: c.providers[0].capabilities.append("extract"),
        lambda c: setattr(c.providers[0], "weight", 20),
        lambda c: setattr(c.strategy, "default_mode", "rotation"),
    )
    for mutate in mutations:
        changed = original.model_copy(deep=True)
        mutate(changed)
        assert config_fingerprint(changed) != config_fingerprint(original)
