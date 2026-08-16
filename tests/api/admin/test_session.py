import pytest
from fastapi.testclient import TestClient

from searchhub.api.admin.session import SessionStore
from searchhub.api.app import create_app
from searchhub.config import ConfigService


def make_app_client(data_dir, password="testpass123"):
    cs = ConfigService(data_dir)
    cs.load()
    cs.set_admin_password(password)
    app = create_app(data_dir)
    return TestClient(app)


def test_login_logout_flow(data_dir):
    with make_app_client(data_dir) as c:
        r = c.post("/api/admin/login", json={"username": "admin", "password": "wrong"})
        assert r.status_code == 401
        r = c.post("/api/admin/login", json={"username": "admin", "password": "testpass123"})
        assert r.status_code == 200
        assert r.json()["success"] is True
        assert c.cookies.get("sh_session")
        r = c.post("/api/admin/logout")
        assert r.status_code == 200
        assert c.cookies.get("sh_session") is None


def test_admin_routes_require_session(data_dir):
    with make_app_client(data_dir) as c:
        r = c.post("/api/admin/change-password",
                   json={"old_password": "nope", "new_password": "newpass123"})
        assert r.status_code == 401
        assert r.json()["error"] == "unauthorized"


def test_change_password(data_dir):
    with make_app_client(data_dir) as c:
        c.post("/api/admin/login", json={"username": "admin", "password": "testpass123"})
        r = c.post("/api/admin/change-password",
                   json={"old_password": "nope", "new_password": "newpass123"})
        assert r.status_code == 400
        r = c.post("/api/admin/change-password",
                   json={"old_password": "testpass123", "new_password": "newpass123"})
        assert r.status_code == 200
        c.post("/api/admin/logout")
        r = c.post("/api/admin/login", json={"username": "admin", "password": "testpass123"})
        assert r.status_code == 401
        r = c.post("/api/admin/login", json={"username": "admin", "password": "newpass123"})
        assert r.status_code == 200


def test_short_password_rejected(data_dir):
    with make_app_client(data_dir) as c:
        c.post("/api/admin/login", json={"username": "admin", "password": "testpass123"})
        r = c.post("/api/admin/change-password",
                   json={"old_password": "testpass123", "new_password": "short"})
        assert r.status_code == 422


def test_session_store_signs_and_verifies():
    store = SessionStore(b"x" * 32)
    token = store.create("admin", ttl_hours=1)
    assert store.verify(token) == "admin"
    assert store.verify(token + "x") is None
    assert store.verify("garbage") is None


def test_expired_session_rejected():
    store = SessionStore(b"x" * 32)
    token = store.create("admin", ttl_hours=-1)
    assert store.verify(token) is None
