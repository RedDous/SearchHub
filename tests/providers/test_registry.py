import httpx
import pytest

from searchhub.config import AppConfig, ConfigService, ProviderConfig
from searchhub.providers import build_registry, registry_for_capability


@pytest.fixture
def cfg(data_dir) -> AppConfig:
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.providers = [
        ProviderConfig(id="ddg", capabilities=["search"], weight=5, priority=1),
        ProviderConfig(id="exa", capabilities=["search", "extract"], weight=10, priority=2),
        ProviderConfig(id="unknown-thing", capabilities=["search"]),
    ]
    return cfg


def test_build_registry_instantiates_enabled(cfg):
    http = httpx.AsyncClient()
    registry = build_registry(cfg, {"EXA_KEY_1": "k1"}, http)
    assert set(registry) == {"ddg", "exa"}


def test_unknown_provider_id_is_skipped(cfg):
    http = httpx.AsyncClient()
    registry = build_registry(cfg, {}, http)
    assert "unknown-thing" not in registry


def test_registry_for_capability_orders_by_priority(cfg):
    http = httpx.AsyncClient()
    registry = build_registry(cfg, {"EXA_KEY_1": "k1"}, http)
    assert [p.id for p in registry_for_capability(registry, "search")] == ["ddg", "exa"]
    assert [p.id for p in registry_for_capability(registry, "extract")] == ["exa"]


def test_cloud_provider_without_key_is_skipped(cfg):
    cfg.providers = [ProviderConfig(id="exa", capabilities=["search"])]
    http = httpx.AsyncClient()
    registry = build_registry(cfg, {}, http)
    assert "exa" not in registry
