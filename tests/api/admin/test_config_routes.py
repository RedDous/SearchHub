import pytest


def test_config_shows_masked_secrets(admin_client):
    r = admin_client.get("/api/admin/config")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["config_version"] >= 0
    assert data["config"]["admin"]["password_hash"] == ""
    for t in data["config"]["auth"]["tokens"]:
        assert "****" in t["token_hash"]


def test_config_reports_default_password(admin_client):
    # admin_client fixture 预设了 testpass123（非默认）→ password_is_default=False
    data = admin_client.get("/api/admin/config").json()["data"]
    assert data["password_is_default"] is False


def test_config_reports_default_password_when_default(admin_client, data_dir):
    from searchhub.config import ConfigService

    # 手动把密码重置为默认 admin 模拟未改密用户
    cs = ConfigService(data_dir)
    cs.load()
    cs.set_admin_password("admin")
    data = admin_client.get("/api/admin/config").json()["data"]
    assert data["password_is_default"] is True


def test_provider_crud(admin_client):
    body = {"id": "ddg", "capabilities": ["search"], "enabled": True, "weight": 5}
    r = admin_client.post("/api/admin/providers", json=body)
    assert r.status_code == 200 and r.json()["success"] is True
    r = admin_client.post("/api/admin/providers", json=body)
    assert r.status_code == 409
    r = admin_client.put("/api/admin/providers/ddg", json={**body, "weight": 9})
    assert r.status_code == 200
    cfg = admin_client.get("/api/admin/config").json()["data"]["config"]
    assert cfg["providers"][0]["weight"] == 9
    r = admin_client.put("/api/admin/providers/ddg", json={**body, "id": "exa"})
    assert r.status_code == 400
    r = admin_client.delete("/api/admin/providers/ddg")
    assert r.status_code == 200
    r = admin_client.delete("/api/admin/providers/ddg")
    assert r.status_code == 404
    cfg = admin_client.get("/api/admin/config").json()["data"]["config"]
    assert cfg["providers"] == []


def test_provider_validation_rejected(admin_client):
    r = admin_client.post("/api/admin/providers",
                          json={"id": "bad", "capabilities": ["crawl"]})
    assert r.status_code == 400  # save_config 的 capabilities 校验


def test_provider_test_unknown(admin_client):
    r = admin_client.post("/api/admin/providers/nope/test")
    assert r.status_code == 404


def test_provider_test_search_probe(admin_client):
    from searchhub.models import SearchItem
    from searchhub.providers.ddg import DdgProvider

    original = DdgProvider.search

    async def fake_search(self, query, limit):
        return [SearchItem(title="t", url="https://x.com", provider="ddg")]

    DdgProvider.search = fake_search
    try:
        admin_client.post("/api/admin/providers",
                          json={"id": "ddg", "capabilities": ["search"]})
        r = admin_client.post("/api/admin/providers/ddg/test")
    finally:
        DdgProvider.search = original
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["capability"] == "search"
    assert body["data"]["count"] == 1


def test_settings_partial_update(admin_client):
    r = admin_client.put("/api/admin/settings",
                         json={"cache": {"enabled": False, "search_ttl_s": 60}})
    assert r.status_code == 200
    cfg = admin_client.get("/api/admin/config").json()["data"]["config"]
    assert cfg["cache"]["enabled"] is False
    assert cfg["cache"]["search_ttl_s"] == 60
    assert cfg["strategy"]["default_mode"] == "fanout"  # 未动
    r = admin_client.put("/api/admin/settings", json={"strategy": {"default_mode": "bad"}})
    assert r.status_code == 422


def test_settings_requires_auth(data_dir):
    from fastapi.testclient import TestClient

    from searchhub.api.app import create_app
    from searchhub.config import ConfigService

    cs = ConfigService(data_dir)
    cs.load()
    cs.set_admin_password("testpass123")
    with TestClient(create_app(data_dir)) as c:
        assert c.get("/api/admin/config").status_code == 401


def test_settings_update_preserves_out_of_band_provider(admin_client, data_dir):
    from searchhub.config import ConfigService, ProviderConfig

    r = admin_client.post("/api/admin/providers",
                          json={"id": "exa", "capabilities": ["search"]})
    assert r.status_code == 200
    cs2 = ConfigService(data_dir)
    cs2.load()
    cfg2 = cs2.get()
    cfg2.providers.append(ProviderConfig(id="exa2", capabilities=["search"]))
    cs2.save_config(cfg2)
    r = admin_client.put("/api/admin/settings", json={"cache": {"enabled": True}})
    assert r.status_code == 200
    cfg = admin_client.get("/api/admin/config").json()["data"]["config"]
    assert {p["id"] for p in cfg["providers"]} == {"exa", "exa2"}
    assert cfg["cache"]["enabled"] is True


def test_provider_types_endpoint(admin_client):
    r = admin_client.get("/api/admin/provider-types")
    assert r.status_code == 200
    types = {t["type"]: t for t in r.json()["data"]["types"]}
    assert set(types) == {"exa", "tavily", "ddg", "searxng", "jina", "trafilatura"}
    assert types["exa"]["requires_key"] is True
    assert types["exa"]["key_pool_params"] == "full"
    assert types["ddg"]["requires_key"] is False
    assert types["searxng"]["requires_base_url"] is True


def test_create_searxng_without_base_url_rejected(admin_client):
    r = admin_client.post("/api/admin/providers",
                          json={"id": "searxng", "capabilities": ["search"]})
    assert r.status_code == 400
    assert "base_url" in r.json()["error"]


def test_create_searxng_with_extract_rejected(admin_client):
    r = admin_client.post("/api/admin/providers",
                          json={"id": "searxng", "capabilities": ["search", "extract"],
                                "base_url": "http://searxng:8080"})
    assert r.status_code == 400
    assert "extract" in r.json()["error"]


def test_create_ddg_with_base_url_allowed(admin_client):
    # 宽松路径：非必填字段不拒绝（ddg 无 base_url 需求但提交了也不报错）
    r = admin_client.post("/api/admin/providers",
                          json={"id": "ddg", "capabilities": ["search"],
                                "base_url": "http://example.com"})
    assert r.status_code == 200


def test_config_reports_version_and_commit(admin_client, monkeypatch):
    from searchhub import __version__
    monkeypatch.setenv("SEARCHHUB_COMMIT", "abc1234")
    data = admin_client.get("/api/admin/config").json()["data"]
    assert data["version"] == __version__
    assert data["commit"] == "abc1234"


def test_config_commit_defaults_to_dev(admin_client, monkeypatch):
    monkeypatch.delenv("SEARCHHUB_COMMIT", raising=False)
    data = admin_client.get("/api/admin/config").json()["data"]
    assert data["commit"] == "dev"
