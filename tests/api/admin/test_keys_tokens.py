import hashlib

import pytest


def test_keys_list_add_remove(admin_client):
    admin_client.post("/api/admin/providers",
                      json={"id": "exa", "capabilities": ["search", "extract"]})
    r = admin_client.get("/api/admin/providers/exa/keys")
    assert r.json()["data"]["keys"] == []
    r = admin_client.post("/api/admin/providers/exa/keys", json={"key": "  "})
    assert r.status_code == 400
    r = admin_client.post("/api/admin/providers/exa/keys", json={"key": "sekrit-123"})
    assert r.status_code == 200
    r = admin_client.post("/api/admin/providers/exa/keys", json={"key": "sekrit-456"})
    assert r.status_code == 200
    r = admin_client.get("/api/admin/providers/exa/keys")
    keys = r.json()["data"]["keys"]
    assert len(keys) == 2
    assert keys[0]["masked"] == "sekri****3-123"[:5] + "****" + "sekrit-123"[-4:]
    assert "sekrit-123" not in r.text
    r = admin_client.delete("/api/admin/providers/exa/keys/0")
    assert r.status_code == 200
    keys = admin_client.get("/api/admin/providers/exa/keys").json()["data"]["keys"]
    assert len(keys) == 1
    assert keys[0]["masked"].endswith("456")
    r = admin_client.delete("/api/admin/providers/exa/keys/5")
    assert r.status_code == 404


def test_keys_status_populated(admin_client, monkeypatch):
    engine = admin_client.app.state.engine
    monkeypatch.setattr(engine, "provider_status", lambda: [
        {"id": "exa", "capabilities": ["search"], "keys": [
            {"key": "sekri****-123", "cooling_until": 0.0, "in_flight": 1, "ok": True}]}])
    admin_client.post("/api/admin/providers",
                      json={"id": "exa", "capabilities": ["search"]})
    admin_client.post("/api/admin/providers/exa/keys", json={"key": "sekrit-123"})
    r = admin_client.get("/api/admin/providers/exa/keys")
    keys = r.json()["data"]["keys"]
    assert len(keys) == 1
    assert keys[0]["status"] is not None
    assert keys[0]["status"]["in_flight"] == 1
    assert keys[0]["status"]["ok"] is True


def test_token_create_list_delete(admin_client):
    r = admin_client.get("/api/admin/tokens")
    assert r.json()["data"]["tokens"] == []
    r = admin_client.post("/api/admin/tokens", json={"name": "my-agent"})
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["name"] == "my-agent"
    assert len(body["token"]) >= 32
    token_id = body["id"]
    r = admin_client.get("/api/admin/tokens")
    tokens = r.json()["data"]["tokens"]
    assert len(tokens) == 1
    assert tokens[0]["hash_prefix"] == hashlib.sha256(body["token"].encode()).hexdigest()[:8]
    assert "token" not in tokens[0]  # 明文不回显
    r = admin_client.delete(f"/api/admin/tokens/{token_id}")
    assert r.status_code == 200
    r = admin_client.delete(f"/api/admin/tokens/{token_id}")
    assert r.status_code == 404


def test_created_token_works_on_public_api(admin_client):
    r = admin_client.post("/api/admin/tokens", json={"name": "agent"})
    raw = r.json()["data"]["token"]
    resp = admin_client.get("/v1/search", params={"q": "x"},
                            headers={"Authorization": f"Bearer {raw}"})
    assert resp.status_code == 200  # 无供应商也返回 200 success=false


def test_revoked_token_rejected(admin_client, data_dir):
    from searchhub.config import ConfigService

    r = admin_client.post("/api/admin/tokens", json={"name": "agent"})
    raw = r.json()["data"]["token"]
    token_id = r.json()["data"]["id"]
    resp = admin_client.get("/v1/search", params={"q": "x"},
                            headers={"Authorization": f"Bearer {raw}"})
    assert resp.status_code == 200
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    for t in cfg.auth.tokens:
        if t.id == token_id:
            t.revoked = True
    cs.save_config(cfg)
    resp = admin_client.get("/v1/search", params={"q": "x"},
                            headers={"Authorization": f"Bearer {raw}"})
    assert resp.status_code == 401


def test_add_wrong_provider_key_rejected(admin_client):
    # tvly- 前缀的 key 加到 exa → 400 提示疑似贴错
    r = admin_client.post("/api/admin/providers/exa/keys", json={"key": "tvly-abc123"})
    assert r.status_code == 400
    assert "tavily" in r.json()["error"]


def test_add_tavily_key_to_tavily_ok(admin_client):
    r = admin_client.post("/api/admin/providers/tavily/keys", json={"key": "tvly-abc123"})
    assert r.status_code == 200


def test_add_wrong_format_key_to_prefix_provider_rejected(admin_client):
    # tavily 自身前缀不匹配 → 400
    r = admin_client.post("/api/admin/providers/tavily/keys", json={"key": "abc123"})
    assert r.status_code == 400
    assert "tvly-" in r.json()["error"]


def test_add_key_to_prefixless_provider_lenient(admin_client):
    # exa/ddg 无前缀约束，任意 key 可加
    r = admin_client.post("/api/admin/providers/exa/keys", json={"key": "some-random-key-1"})
    assert r.status_code == 200


def test_jina_prefixed_key_into_tavily_reports_wrong_provider(admin_client):
    r = admin_client.post("/api/admin/providers/tavily/keys", json={"key": "jina_xyz"})
    assert r.status_code == 400
    assert "jina" in r.json()["error"]
