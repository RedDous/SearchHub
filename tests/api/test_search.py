import hashlib

import pytest
from fastapi.testclient import TestClient

from searchhub.api.app import create_app
from searchhub.config import AuthConfig, ConfigService, ProviderConfig, TokenEntry


@pytest.fixture
def client(data_dir):
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.auth = AuthConfig(tokens=[TokenEntry(name="t", token_hash=hashlib.sha256(b"tok").hexdigest())])
    cfg.providers = [ProviderConfig(id="ddg", capabilities=["search"])]
    cs.save_config(cfg)
    app = create_app(data_dir)
    # 注入假 ddg 适配器：monkeypatch PROVIDER_CLASSES 之后重建
    with TestClient(app) as c:
        yield c


AUTH = {"Authorization": "Bearer tok"}


def test_search_get_shape(client):
    from searchhub.models import SearchItem
    from searchhub.providers.ddg import DdgProvider

    original = DdgProvider.search

    async def fake_search(self, query, limit):
        return [SearchItem(title="T", url="https://x.com", description="D", position=0, provider="ddg")]

    DdgProvider.search = fake_search
    try:
        r = client.get("/v1/search", params={"q": "python"}, headers=AUTH)
    finally:
        DdgProvider.search = original
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["web"][0]["title"] == "T"
    assert body["data"]["web"][0]["url"] == "https://x.com"
    assert body["data"]["web"][0]["position"] == 0
    assert "meta" in body


def test_search_missing_q(client):
    r = client.get("/v1/search", headers=AUTH)
    assert r.status_code == 400
    assert r.json()["success"] is False


def test_search_no_provider_returns_error(data_dir):
    cs = ConfigService(data_dir)
    cs.load()
    cs.get().auth = AuthConfig(tokens=[TokenEntry(name="t", token_hash=hashlib.sha256(b"tok").hexdigest())])
    cs.save_config(cs.get())
    with TestClient(create_app(data_dir)) as c:
        r = c.get("/v1/search", params={"q": "x"}, headers=AUTH)
        assert r.status_code == 200
        assert r.json()["success"] is False
