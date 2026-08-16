from pathlib import Path

import pytest

from searchhub.config import ConfigService


@pytest.fixture
def cs(data_dir: Path) -> ConfigService:
    c = ConfigService(data_dir)
    c.load()
    return c


def test_defaults_have_admin_and_history(cs):
    cfg = cs.get()
    assert cfg.admin.username == "admin"
    assert cfg.admin.password_hash == ""
    assert cfg.admin.session_ttl_hours == 24
    assert cfg.history.retention_days == 30
    assert cfg.history.redact_queries is False


def test_password_roundtrip(cs):
    assert cs.verify_admin_password("hunter2") is False
    cs.set_admin_password("hunter2")
    assert cs.verify_admin_password("hunter2") is True
    assert cs.verify_admin_password("wrong") is False
    assert cs.get().admin.password_hash != ""
    assert "hunter2" not in cs.get().admin.password_hash


def test_session_secret_persistent(cs):
    s1 = cs.session_secret()
    s2 = cs.session_secret()
    assert s1 == s2 and len(s1) == 32
    assert oct((cs.data_dir / "session_secret").stat().st_mode & 0o777) == "0o600"


def test_save_secrets_atomic_and_600(cs):
    cs.save_secrets({"EXA_KEY_1": "k1", "TAVILY_KEY_1": "k2"})
    assert cs.secrets()["EXA_KEY_1"] == "k1"
    assert oct((cs.data_dir / "secrets.env").stat().st_mode & 0o777) == "0o600"
    cs2 = ConfigService(cs.data_dir)
    cs2.load()
    assert cs2.provider_keys("exa") == ["k1"]
    assert cs2.provider_keys("tavily") == ["k2"]


def test_add_provider_key_uses_next_index(cs):
    cs.save_secrets({"EXA_KEY_1": "k1", "EXA_KEY_2": "k2", "OTHER_X": "zz"})
    cs.add_provider_key("exa", "k3")
    assert cs.provider_keys("exa") == ["k1", "k2", "k3"]
    assert "OTHER_X" in cs.secrets()
    with pytest.raises(ValueError):
        cs.add_provider_key("exa", "   ")


def test_remove_provider_key_renumbers(cs):
    cs.save_secrets({"EXA_KEY_1": "k1", "EXA_KEY_2": "k2", "EXA_KEY_3": "k3"})
    cs.remove_provider_key("exa", 0)
    assert cs.provider_keys("exa") == ["k2", "k3"]
    assert "EXA_KEY_1" not in cs.secrets()
    assert "EXA_KEY_2" in cs.secrets() and "EXA_KEY_3" in cs.secrets()
    with pytest.raises(IndexError):
        cs.remove_provider_key("exa", 5)


def test_updated_at_after_save(cs):
    before = cs.updated_at
    cfg = cs.get()
    cfg.strategy.default_mode = "rotation"
    cs.save_config(cfg)
    assert cs.updated_at >= before
