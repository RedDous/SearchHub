from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def compose() -> dict:
    path = ROOT / "docker-compose.yml"
    assert path.exists(), "docker-compose.yml missing"
    return yaml.safe_load(path.read_text())


def test_searchhub_service_shape(compose: dict):
    svc = compose["services"]["searchhub"]
    assert svc["ports"] == ["8000:8000"]
    assert svc["volumes"] == ["./data:/data"]
    assert svc["environment"]["SEARCHHUB_DATA"] == "/data"
    assert svc["environment"]["ADMIN_PASSWORD"] == "${ADMIN_PASSWORD:-admin}"
    assert ":?" not in svc["environment"]["ADMIN_PASSWORD"]  # 已改为可选，不再强制
    assert svc["restart"] == "unless-stopped"
    assert "build" in svc


def test_sidecar_profiles(compose: dict):
    assert compose["services"]["searxng"]["profiles"] == ["sidecars"]
    assert compose["services"]["crawl4ai"]["profiles"] == ["sidecars"]
    assert "8080:8080" in compose["services"]["searxng"]["ports"]
    assert "11235:11235" in compose["services"]["crawl4ai"]["ports"]


def test_sidecars_are_opt_in(compose: dict):
    # 默认 up 不应拉起 sidecar：它们必须都在 profile 里
    for name in ("searxng", "crawl4ai"):
        assert compose["services"][name].get("profiles"), f"{name} missing profiles"


def test_env_example_exists_and_has_required_keys():
    env = (ROOT / ".env.example").read_text()
    assert "ADMIN_PASSWORD=" in env
    assert "SEARXNG_SECRET=" in env
