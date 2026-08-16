from pathlib import Path

import pytest

from searchhub.config import AppConfig, ConfigService, ProviderConfig


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
