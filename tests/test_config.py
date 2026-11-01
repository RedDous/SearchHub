from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from searchhub.config import AppConfig, ConfigService, ProviderConfig, StrategyConfig


def test_load_creates_defaults(data_dir: Path):
    cs = ConfigService(data_dir)
    cs.load()
    assert (data_dir / "config.yaml").exists()
    assert (data_dir / "secrets.env").exists()
    cfg = cs.get()
    assert cfg.strategy.default_mode == "fanout"
    assert cfg.cache.search_ttl_s == 600


def test_roundtrip_save(data_dir: Path):
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.strategy.default_mode = "rotation"
    cfg.providers = [ProviderConfig(id="exa", capabilities=["search", "extract"])]
    cs.save_config(cfg)
    cs2 = ConfigService(data_dir)
    cs2.load()
    assert cs2.get().strategy.default_mode == "rotation"
    assert cs2.get().providers[0].id == "exa"


def test_secrets_parsing(data_dir: Path):
    cs = ConfigService(data_dir)
    cs.load()
    (data_dir / "secrets.env").write_text(
        "EXA_KEY_1=alpha\nEXA_KEY_2=beta\n# comment\nTAVILY_KEY_1=gamma\n"
    )
    cs.maybe_reload()
    assert cs.provider_keys("exa") == ["alpha", "beta"]
    assert cs.provider_keys("tavily") == ["gamma"]
    assert cs.provider_keys("ddg") == []


def test_hot_reload_on_mtime_change(data_dir: Path):
    cs = ConfigService(data_dir)
    cs.load()
    assert not cs.maybe_reload()
    (data_dir / "config.yaml").write_text(
        (data_dir / "config.yaml").read_text() + "\n# touched\n"
    )
    assert cs.maybe_reload()
    assert not cs.maybe_reload()


def test_save_backs_up_previous(data_dir: Path):
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cs.save_config(cfg)
    cs.save_config(cfg)
    assert len(list(data_dir.glob("config.yaml.bak*"))) >= 1


def test_invalid_yaml_raises(data_dir: Path):
    cs = ConfigService(data_dir)
    cs.load()
    (data_dir / "config.yaml").write_text("strategy: [unclosed")
    with pytest.raises(Exception):
        cs.maybe_reload()


def test_invalid_provider_capability_rejected_on_save(data_dir: Path):
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.providers = [ProviderConfig(id="exa", capabilities=["search", "crawl"])]
    with pytest.raises(Exception):
        cs.save_config(cfg)


def test_save_failure_leaves_disk_and_memory_unchanged(data_dir: Path, monkeypatch):
    cs = ConfigService(data_dir)
    cs.load()
    old_cfg = cs.get()
    old_cfg.strategy.default_mode = "primary_fallback"
    cs.save_config(old_cfg)
    new_cfg = AppConfig(
        strategy=StrategyConfig(default_mode="rotation"),
        providers=[ProviderConfig(id="exa", capabilities=["search"])],
    )

    def boom(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(yaml, "safe_dump", boom)
    with pytest.raises(OSError):
        cs.save_config(new_cfg)

    assert cs.get() is old_cfg
    on_disk = AppConfig.model_validate(
        yaml.safe_load((data_dir / "config.yaml").read_text()) or {}
    )
    assert on_disk.strategy.default_mode == "primary_fallback"
    assert not list(data_dir.glob("config.yaml.tmp"))


def test_provider_config_defaults_type_to_id():
    p = ProviderConfig(id="exa", capabilities=["search"])
    assert p.type == "exa"


def test_provider_config_allows_type_different_from_id():
    p = ProviderConfig(id="exa-work", type="exa", capabilities=["search"])
    assert p.type == "exa"


def test_provider_id_rejects_leading_digit():
    with pytest.raises(ValidationError):
        ProviderConfig(id="1exa", type="exa", capabilities=["search"])


def test_duplicate_canonical_key_prefixes_rejected_on_model_validation():
    with pytest.raises(ValidationError, match="canonical key prefix"):
        AppConfig(providers=[
            ProviderConfig(id="exa-work", type="exa", capabilities=["search"]),
            ProviderConfig(id="exa_work", type="exa", capabilities=["extract"]),
        ])


def test_duplicate_canonical_key_prefixes_rejected_on_save(data_dir):
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.providers = [
        ProviderConfig(id="exa-work", type="exa", capabilities=["search"]),
        ProviderConfig(id="exa_work", type="exa", capabilities=["extract"]),
    ]
    with pytest.raises(ValueError, match="canonical key prefix"):
        cs.save_config(cfg)


def test_legacy_config_without_type_loads(data_dir):
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "config.yaml").write_text(
        "providers:\n- id: ddg\n  capabilities: [search]\n"
    )
    cs = ConfigService(data_dir)
    cs.load()
    assert cs.get().providers[0].type == "ddg"


def test_duplicate_provider_ids_rejected():
    with pytest.raises(ValidationError):
        AppConfig(providers=[
            ProviderConfig(id="exa", type="exa", capabilities=["search"]),
            ProviderConfig(id="exa", type="exa", capabilities=["extract"]),
        ])


def test_key_prefix_for_sanitizes_instance_id():
    from searchhub.config import key_prefix_for

    assert key_prefix_for("exa-work") == "EXA_WORK_KEY_"
    assert key_prefix_for("exa") == "EXA_KEY_"


def test_provider_keys_support_hyphenated_instance_id(data_dir):
    cs = ConfigService(data_dir)
    cs.load()
    cs.add_provider_key("exa-work", "k1")
    assert cs.provider_keys("exa-work") == ["k1"]
    assert cs.provider_keys("exa") == []
    # 前缀必须能写回 secrets.env 并被重新解析（连字符会破坏 KEY=VALUE 语法）
    cs2 = ConfigService(data_dir)
    cs2.load()
    assert cs2.provider_keys("exa-work") == ["k1"]
    cs2.remove_provider_key("exa-work", 0)
    assert cs2.provider_keys("exa-work") == []
