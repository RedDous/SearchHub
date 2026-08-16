import hashlib

import pytest
from fastapi.testclient import TestClient

from searchhub.api.app import create_app
from searchhub.config import AuthConfig, ConfigService, TokenEntry


@pytest.fixture
def app_with_token(data_dir):
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.auth = AuthConfig(tokens=[TokenEntry(name="test", token_hash=hashlib.sha256(b"sekrit").hexdigest())])
    cs.save_config(cfg)
    return create_app(data_dir)


def test_healthz_needs_no_token(app):
    with TestClient(app) as c:
        assert c.get("/healthz").status_code == 200


def test_providers_requires_token(app_with_token):
    with TestClient(app_with_token) as c:
        assert c.get("/v1/providers").status_code == 401
        assert c.get("/v1/providers", headers={"Authorization": "Bearer wrong"}).status_code == 401
        r = c.get("/v1/providers", headers={"Authorization": "Bearer sekrit"})
        assert r.status_code == 200


def test_search_requires_token(app_with_token):
    with TestClient(app_with_token) as c:
        assert c.post("/v1/search", json={"q": "x"}).status_code == 401
