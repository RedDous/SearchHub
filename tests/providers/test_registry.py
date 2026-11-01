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


def test_build_registry_uses_type_not_id(cfg):
    cfg.providers = [
        ProviderConfig(id="exa-work", type="exa", capabilities=["search"]),
    ]
    registry = build_registry(cfg, {"EXA_WORK_KEY_1": "k1"}, httpx.AsyncClient())
    assert set(registry) == {"exa-work"}
    assert registry["exa-work"].cfg.type == "exa"


def test_provider_uses_instance_id(cfg):
    cfg.providers = [
        ProviderConfig(id="exa-work", type="exa", capabilities=["search"]),
    ]
    registry = build_registry(cfg, {"EXA_WORK_KEY_1": "k1"}, httpx.AsyncClient())
    assert registry["exa-work"].id == "exa-work"
    assert registry["exa-work"].cfg.type == "exa"


def test_registry_for_capability_respects_instance_capabilities(cfg):
    cfg.providers = [
        ProviderConfig(id="exa", type="exa", capabilities=["search"]),
    ]
    registry = build_registry(cfg, {"EXA_KEY_1": "k1"}, httpx.AsyncClient())
    assert [p.id for p in registry_for_capability(registry, "search")] == ["exa"]
    assert registry_for_capability(registry, "extract") == []


def test_invalid_options_skips_provider(cfg):
    cfg.providers = [
        ProviderConfig(id="exa", type="exa", capabilities=["search"],
                       options={"bogus": 1}),
    ]
    registry = build_registry(cfg, {"EXA_KEY_1": "k1"}, httpx.AsyncClient())
    assert registry == {}


def test_provider_exposes_validated_options(cfg):
    from searchhub.providers.options import ExaOptions

    cfg.providers = [
        ProviderConfig(id="exa", type="exa", capabilities=["search"],
                       options={"search_type": "deep"}),
    ]
    registry = build_registry(cfg, {"EXA_KEY_1": "k1"}, httpx.AsyncClient())
    options = registry["exa"].options
    assert isinstance(options, ExaOptions)
    assert options.search_type == "deep"
    assert options.include_text is True
