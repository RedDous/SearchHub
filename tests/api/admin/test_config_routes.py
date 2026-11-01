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
    assert body["data"]["results"][0]["capability"] == "search"
    assert body["data"]["results"][0]["count"] == 1


def test_provider_test_runs_all_capabilities(admin_client, monkeypatch):
    from searchhub.models import ExtractItem, SearchItem
    from searchhub.providers.exa import ExaProvider

    async def fake_search(self, query, limit):
        return [SearchItem(title="t", url="https://x.com", provider=self.id)]

    async def fake_extract(self, urls, **kw):
        return [ExtractItem(url=urls[0], content="ok", provider=self.id)]

    monkeypatch.setattr(ExaProvider, "search", fake_search)
    monkeypatch.setattr(ExaProvider, "extract", fake_extract)
    admin_client.post("/api/admin/providers", json={
        "id": "exa", "type": "exa", "capabilities": ["search", "extract"],
    })
    r = admin_client.post("/api/admin/providers/exa/test")
    assert r.status_code == 200
    caps = {x["capability"] for x in r.json()["data"]["results"]}
    assert caps == {"search", "extract"}


def test_provider_test_capability_selector_runs_only_requested(admin_client, monkeypatch):
    from searchhub.models import ExtractItem, SearchItem
    from searchhub.providers.exa import ExaProvider

    seen: list[str] = []

    async def fake_search(self, query, limit):
        seen.append("search")
        return [SearchItem(title="t", url="https://x.com", provider=self.id)]

    async def fake_extract(self, urls, **kw):
        seen.append("extract")
        return [ExtractItem(url=urls[0], content="ok", provider=self.id)]

    monkeypatch.setattr(ExaProvider, "search", fake_search)
    monkeypatch.setattr(ExaProvider, "extract", fake_extract)
    assert admin_client.post("/api/admin/providers", json={
        "id": "exa", "type": "exa", "capabilities": ["search", "extract"],
    }).status_code == 200
    r = admin_client.post("/api/admin/providers/exa/test?capability=extract")
    assert r.status_code == 200
    assert [x["capability"] for x in r.json()["data"]["results"]] == ["extract"]
    assert seen == ["extract"]


def test_test_draft_capability_selector_runs_only_requested(admin_client, monkeypatch):
    from searchhub.models import ExtractItem, SearchItem
    from searchhub.providers.exa import ExaProvider

    seen: list[str] = []

    async def fake_search(self, query, limit):
        seen.append("search")
        return [SearchItem(title="t", url="https://x.com", provider=self.id)]

    async def fake_extract(self, urls, **kw):
        seen.append("extract")
        return [ExtractItem(url=urls[0], content="ok", provider=self.id)]

    monkeypatch.setattr(ExaProvider, "search", fake_search)
    monkeypatch.setattr(ExaProvider, "extract", fake_extract)
    r = admin_client.post("/api/admin/providers/test?capability=search", json={
        "id": "exa", "type": "exa", "capabilities": ["search", "extract"],
    })
    assert r.status_code == 200
    assert [x["capability"] for x in r.json()["data"]["results"]] == ["search"]
    assert seen == ["search"]


def test_provider_test_rejects_unsupported_capability(admin_client):
    assert admin_client.post("/api/admin/providers", json={
        "id": "ddg", "type": "ddg", "capabilities": ["search"],
    }).status_code == 200
    assert admin_client.post(
        "/api/admin/providers/ddg/test?capability=crawl").status_code == 400
    assert admin_client.post(
        "/api/admin/providers/ddg/test?capability=extract").status_code == 400
    assert admin_client.post("/api/admin/providers/test?capability=crawl", json={
        "id": "ddg", "type": "ddg", "capabilities": ["search"],
    }).status_code == 400


def test_extract_item_error_marks_test_failed(admin_client, monkeypatch):
    from searchhub.models import ExtractItem
    from searchhub.providers.trafilatura_py import TrafilaturaProvider

    async def fake_extract(self, urls, **kw):
        return [ExtractItem(url=urls[0], error="blocked", provider=self.id)]

    monkeypatch.setattr(TrafilaturaProvider, "extract", fake_extract)
    admin_client.post("/api/admin/providers", json={
        "id": "trafilatura", "type": "trafilatura", "capabilities": ["extract"],
    })
    r = admin_client.post("/api/admin/providers/trafilatura/test")
    assert r.json()["data"]["results"][0]["success"] is False


def test_search_probe_requests_min_results(admin_client, monkeypatch):
    from dataclasses import replace

    from searchhub.models import SearchItem
    from searchhub.providers.ddg import DdgProvider
    from searchhub.providers.schema import TestSpec

    seen: dict[str, int] = {}

    async def fake_search(self, query, limit):
        seen["limit"] = limit
        return [SearchItem(title=str(i), url=f"https://x.com/{i}", provider=self.id)
                for i in range(limit)]

    monkeypatch.setattr(DdgProvider, "search", fake_search)
    monkeypatch.setattr(DdgProvider, "schema", replace(
        DdgProvider.schema,
        tests=(TestSpec(capability="search", query="q", min_results=2),)))
    admin_client.post("/api/admin/providers",
                      json={"id": "ddg", "capabilities": ["search"]})
    r = admin_client.post("/api/admin/providers/ddg/test")
    result = r.json()["data"]["results"][0]
    assert seen["limit"] == 2
    assert result["success"] is True
    assert result["count"] == 2


def test_removing_capability_prunes_stale_test_result(admin_client, monkeypatch):
    from searchhub.api.admin import config_routes as cr
    from searchhub.models import ExtractItem, SearchItem
    from searchhub.providers.exa import ExaProvider

    monkeypatch.setattr(cr, "_auto_retest", cr._REAL_AUTO_RETEST)

    async def fake_search(self, query, limit):
        return [SearchItem(title="t", url="https://x.com", provider=self.id)]

    async def fake_extract(self, urls, **kw):
        return [ExtractItem(url=urls[0], error="blocked", provider=self.id)]

    monkeypatch.setattr(ExaProvider, "search", fake_search)
    monkeypatch.setattr(ExaProvider, "extract", fake_extract)
    admin_client.post("/api/admin/providers", json={
        "id": "exa", "type": "exa", "capabilities": ["search", "extract"],
    })
    admin_client.post("/api/admin/providers/exa/keys", json={"key": "exa-test-key"})
    assert admin_client.post("/api/admin/providers/exa/test").status_code == 200
    st = admin_client.get("/api/admin/config").json()["data"]["provider_status"]["exa"]
    assert st["status"] == "failed"
    assert "extract" in st["tests"]
    r = admin_client.put("/api/admin/providers/exa", json={
        "id": "exa", "type": "exa", "capabilities": ["search"],
    })
    assert r.status_code == 200
    st = admin_client.get("/api/admin/config").json()["data"]["provider_status"]["exa"]
    assert "extract" not in st["tests"]
    assert st["status"] == "ok"


def test_provider_status_reports_per_capability_tests(admin_client, monkeypatch):
    from searchhub.models import ExtractItem, SearchItem
    from searchhub.providers.exa import ExaProvider

    async def fake_search(self, query, limit):
        return [SearchItem(title="t", url="https://x.com", provider=self.id)]

    async def fake_extract(self, urls, **kw):
        return [ExtractItem(url=urls[0], error="blocked", provider=self.id)]

    monkeypatch.setattr(ExaProvider, "search", fake_search)
    monkeypatch.setattr(ExaProvider, "extract", fake_extract)
    admin_client.post("/api/admin/providers", json={
        "id": "exa", "type": "exa", "capabilities": ["search", "extract"],
    })
    admin_client.post("/api/admin/providers/exa/keys", json={"key": "exa-test-key"})
    assert admin_client.post("/api/admin/providers/exa/test").status_code == 200
    st = admin_client.get("/api/admin/config").json()["data"]["provider_status"]["exa"]
    assert set(st["tests"]) == {"search", "extract"}
    assert st["tests"]["search"]["success"] is True
    assert st["tests"]["extract"]["success"] is False
    assert st["status"] == "failed"


def test_provider_status_invalid_config_discards_stale_tests(admin_client, data_dir, monkeypatch):
    from searchhub.config import ConfigService
    from searchhub.models import SearchItem
    from searchhub.providers.ddg import DdgProvider

    async def fake_search(self, query, limit):
        return [SearchItem(title="t", url="https://x.com", provider=self.id)]

    monkeypatch.setattr(DdgProvider, "search", fake_search)
    assert admin_client.post("/api/admin/providers", json={
        "id": "ddg", "type": "ddg", "capabilities": ["search"],
    }).status_code == 200
    assert admin_client.post("/api/admin/providers/ddg/test").status_code == 200

    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.providers[0].options = {"bogus": 1}
    cs.save_config(cfg)

    status = admin_client.get("/api/admin/config").json()["data"]["provider_status"]["ddg"]
    assert status == {"status": "invalid_config", "test": None, "tests": {}}


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


def test_test_draft_known_type(admin_client):
    from searchhub.models import SearchItem
    from searchhub.providers.ddg import DdgProvider

    original = DdgProvider.search

    async def fake_search(self, query, limit):
        return [SearchItem(title="t", url="https://x.com", provider="ddg")]

    DdgProvider.search = fake_search
    try:
        r = admin_client.post("/api/admin/providers/test",
                              json={"id": "ddg", "capabilities": ["search"],
                                    "enabled": True, "weight": 10, "priority": 100,
                                    "max_results": 8, "base_url": None,
                                    "key_pool": {"max_concurrency": 2, "rps_limit": 10,
                                                 "cooldown_s": 60}, "options": {}})
    finally:
        DdgProvider.search = original
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["results"][0]["capability"] == "search"


def test_test_draft_invalid_options_rejected(data_dir):
    from fastapi.testclient import TestClient

    from searchhub.api.app import create_app
    from searchhub.config import ConfigService

    cs = ConfigService(data_dir)
    cs.load()
    cs.set_admin_password("testpass123")
    with TestClient(create_app(data_dir), raise_server_exceptions=False) as client:
        login = client.post("/api/admin/login",
                            json={"username": "admin", "password": "testpass123"})
        assert login.status_code == 200
        r = client.post("/api/admin/providers/test", json={
            "id": "ddg", "type": "ddg", "capabilities": ["search"],
            "options": {"bogus": 1},
        })
    assert r.status_code == 400
    assert "invalid options" in r.json()["error"]


def test_test_draft_unknown_type_rejected(admin_client):
    r = admin_client.post("/api/admin/providers/test",
                          json={"id": "nope", "capabilities": ["search"],
                                "enabled": True, "weight": 10, "priority": 100,
                                "max_results": 8, "base_url": None,
                                "key_pool": {"max_concurrency": 2, "rps_limit": 10,
                                             "cooldown_s": 60}, "options": {}})
    assert r.status_code == 404


def test_test_draft_schema_validation(admin_client):
    # searxng 缺 base_url → 400（复用 schema 校验）
    r = admin_client.post("/api/admin/providers/test",
                          json={"id": "searxng", "capabilities": ["search"],
                                "enabled": True, "weight": 10, "priority": 100,
                                "max_results": 8, "base_url": None,
                                "key_pool": {"max_concurrency": 2, "rps_limit": 10,
                                             "cooldown_s": 60}, "options": {}})
    assert r.status_code == 400
    assert "base_url" in r.json()["error"]


def test_provider_tests_recorded_after_draft_test(admin_client):
    from searchhub.models import SearchItem
    from searchhub.providers.ddg import DdgProvider

    body = {"id": "ddg", "capabilities": ["search"], "enabled": True,
            "weight": 10, "priority": 100, "max_results": 8, "base_url": None,
            "key_pool": {"max_concurrency": 2, "rps_limit": 10, "cooldown_s": 60},
            "options": {}}
    assert admin_client.post("/api/admin/providers", json=body).status_code == 200
    original = DdgProvider.search

    async def fake_search(self, query, limit):
        return [SearchItem(title="t", url="https://x.com", provider="ddg")]

    DdgProvider.search = fake_search
    try:
        assert admin_client.post("/api/admin/providers/test", json=body).status_code == 200
    finally:
        DdgProvider.search = original
    data = admin_client.get("/api/admin/config").json()["data"]
    st = data["provider_status"]["ddg"]
    assert st["status"] == "ok"
    assert st["test"]["capability"] == "search"
    assert st["test"]["count"] == 1


def test_provider_status_missing_key_and_base_url(admin_client, data_dir):
    from searchhub.models import SearchItem
    from searchhub.providers.ddg import DdgProvider
    from searchhub.providers.tavily import TavilyProvider

    body = {"id": "ddg", "capabilities": ["search"], "enabled": True,
            "weight": 10, "priority": 100, "max_results": 8, "base_url": None,
            "key_pool": {"max_concurrency": 2, "rps_limit": 10, "cooldown_s": 60},
            "options": {}}
    assert admin_client.post("/api/admin/providers", json=body).status_code == 200
    # ddg 无 key 需求 → 测过则 ok
    original = DdgProvider.search

    async def fake_search(self, query, limit):
        return [SearchItem(title="t", url="https://x.com", provider="ddg")]

    DdgProvider.search = fake_search
    try:
        admin_client.post("/api/admin/providers/test", json=body)
    finally:
        DdgProvider.search = original
    data = admin_client.get("/api/admin/config").json()["data"]
    assert data["provider_status"]["ddg"]["status"] == "ok"
    # tavily 需 key 且未配置 → missing_key（未配置的都不算）
    assert "tavily" not in data["provider_status"]
    # searxng 需 base_url 且未填 → missing_base_url（保存后把配置里的 base_url 清掉模拟）
    from searchhub.config import ConfigService
    from searchhub.providers.schema import validate_provider_config
    from searchhub.providers.searxng import SearxngProvider

    searxng = {"id": "searxng", "capabilities": ["search"], "enabled": True,
               "weight": 10, "priority": 100, "max_results": 8, "base_url": None,
               "key_pool": {"max_concurrency": 2, "rps_limit": 10, "cooldown_s": 60},
               "options": {}}
    r = admin_client.post("/api/admin/providers", json=searxng)
    assert r.status_code == 400  # 未填 base_url 无法保存
    searxng["base_url"] = "https://searx.example"
    assert admin_client.post("/api/admin/providers", json=searxng).status_code == 200
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    p = next(x for x in cfg.providers if x.id == "searxng")
    p.base_url = None
    cs.save_config(cfg)
    data = admin_client.get("/api/admin/config").json()["data"]
    assert data["provider_status"]["searxng"]["status"] == "missing_base_url"
    assert data["provider_status"]["searxng"]["test"] is None


def test_auto_retest_after_key_add(admin_client):
    from searchhub.models import SearchItem
    from searchhub.providers.tavily import TavilyProvider

    # tavily 需 key：先创建（无 key，不联网），加 key 触发后台自动重测（真实 _auto_retest）
    from searchhub.api.admin import config_routes as cr

    body = {"id": "tavily", "capabilities": ["search"], "enabled": True,
            "weight": 10, "priority": 100, "max_results": 8, "base_url": None,
            "key_pool": {"max_concurrency": 2, "rps_limit": 10, "cooldown_s": 60},
            "options": {}}
    assert admin_client.post("/api/admin/providers", json=body).status_code == 200
    original = TavilyProvider.search

    async def fake_search(self, query, limit):
        return [SearchItem(title="t", url="https://x.com", provider="tavily")]

    TavilyProvider.search = fake_search
    cr._auto_retest = lambda *a, **k: None  # 先屏蔽
    try:
        # 无 key：加 key 前状态为 missing_key
        data = admin_client.get("/api/admin/config").json()["data"]
        assert data["provider_status"]["tavily"]["status"] == "missing_key"
        # 恢复真实自动重测后加 key → 触发探测
        cr._auto_retest = cr._REAL_AUTO_RETEST
        r = admin_client.post("/api/admin/providers/tavily/keys",
                              json={"key": "tvly-abc123"})
        assert r.status_code == 200
    finally:
        TavilyProvider.search = original
        cr._auto_retest = cr._REAL_AUTO_RETEST
    data = admin_client.get("/api/admin/config").json()["data"]
    st = data["provider_status"]["tavily"]
    assert st["status"] == "ok"
    assert st["test"]["capability"] == "search"


def test_create_provider_with_type_and_custom_id(admin_client):
    r = admin_client.post("/api/admin/providers", json={
        "id": "exa-work", "type": "exa", "capabilities": ["search"],
    })
    assert r.status_code == 200
    cfg = admin_client.get("/api/admin/config").json()["data"]["config"]
    assert cfg["providers"][0]["type"] == "exa"
    assert cfg["providers"][0]["id"] == "exa-work"


def test_create_provider_unknown_type_rejected(admin_client):
    r = admin_client.post("/api/admin/providers", json={
        "id": "nope", "type": "nope", "capabilities": ["search"],
    })
    assert r.status_code == 400


def test_update_provider_type_immutable(admin_client):
    admin_client.post("/api/admin/providers", json={
        "id": "exa", "type": "exa", "capabilities": ["search"],
    })
    r = admin_client.put("/api/admin/providers/exa", json={
        "id": "exa", "type": "tavily", "capabilities": ["search"],
    })
    assert r.status_code == 400


def test_update_provider_without_type_keeps_existing_type(admin_client):
    admin_client.post("/api/admin/providers", json={
        "id": "exa-work", "type": "exa", "capabilities": ["search"],
    })
    r = admin_client.put("/api/admin/providers/exa-work", json={
        "id": "exa-work", "capabilities": ["search"], "weight": 42,
    })
    assert r.status_code == 200
    cfg = admin_client.get("/api/admin/config").json()["data"]["config"]
    assert cfg["providers"][0]["type"] == "exa"
    assert cfg["providers"][0]["weight"] == 42


def test_create_provider_invalid_options_rejected(admin_client):
    r = admin_client.post("/api/admin/providers", json={
        "id": "exa", "type": "exa", "capabilities": ["search"],
        "options": {"bogus": 1},
    })
    assert r.status_code == 400
