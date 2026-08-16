from fastapi.testclient import TestClient

from searchhub.api.app import create_app
from searchhub.config import ConfigService


def test_first_boot_uses_env_password(data_dir, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "envpass123")
    with TestClient(create_app(data_dir)) as c:
        r = c.post("/api/admin/login",
                   json={"username": "admin", "password": "envpass123"})
        assert r.status_code == 200
    cs = ConfigService(data_dir)
    cs.load()
    assert cs.verify_admin_password("envpass123") is True


def test_first_boot_defaults_to_admin(data_dir, monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    with TestClient(create_app(data_dir)) as c:
        r = c.post("/api/admin/login", json={"username": "admin", "password": "admin"})
        assert r.status_code == 200


def test_existing_password_not_overwritten(data_dir):
    cs = ConfigService(data_dir)
    cs.load()
    cs.set_admin_password("keepme123")
    with TestClient(create_app(data_dir)) as c:
        r = c.post("/api/admin/login", json={"username": "admin", "password": "keepme123"})
        assert r.status_code == 200
        r = c.post("/api/admin/login", json={"username": "admin", "password": "admin"})
        assert r.status_code == 401


def test_admin_routes_mounted(admin_client):
    assert admin_client.get("/api/admin/config").status_code == 200
    assert admin_client.get("/api/admin/tokens").status_code == 200
    assert admin_client.get("/api/admin/history").status_code == 200
    assert admin_client.get("/api/admin/stats/summary").status_code == 200
    assert admin_client.post("/api/admin/providers/nope/test").status_code == 404
