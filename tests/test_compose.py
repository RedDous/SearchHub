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
    assert svc["image"] == "ghcr.io/reddous/searchhub:latest"
    assert "build" not in svc
    assert svc["ports"] == ["8000:8000"]
    assert svc["volumes"] == ["./data:/data"]
    assert svc["restart"] == "unless-stopped"
    assert svc["environment"]["SEARCHHUB_DATA"] == "/data"
    assert svc["environment"]["ADMIN_PASSWORD"] == "${ADMIN_PASSWORD:-admin}"
    assert ":?" not in svc["environment"]["ADMIN_PASSWORD"]


def test_build_override_file(compose: dict):
    path = ROOT / "docker-compose.build.yml"
    assert path.exists()
    merged = yaml.safe_load(path.read_text())
    svc = merged["services"]["searchhub"]
    assert svc["build"]["context"] == "."
    assert "SEARCHHUB_COMMIT" in svc["build"]["args"]
    assert svc["image"] == "searchhub:local"


def test_only_searchhub_service(compose: dict):
    # 外部供应商（searxng/crawl4ai 等）由用户自行部署，SearchHub 不代为管理
    assert set(compose["services"]) == {"searchhub"}


def test_env_example_exists_and_has_required_keys():
    env = (ROOT / ".env.example").read_text()
    assert "ADMIN_PASSWORD=" in env
    assert "SEARXNG_SECRET" not in env
