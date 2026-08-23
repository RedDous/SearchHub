import time

import pytest


@pytest.fixture
def caller_token(admin_client):
    r = admin_client.post("/api/admin/tokens", json={"name": "test-agent"})
    return r.json()["data"]["token"]


def test_history_records_and_lists(admin_client, caller_token):
    headers = {"Authorization": f"Bearer {caller_token}"}
    r = admin_client.get("/api/admin/history")
    assert r.json()["data"]["rows"] == []
    admin_client.get("/v1/search", params={"q": "hello"}, headers=headers)
    rows = admin_client.get("/api/admin/history").json()["data"]["rows"]
    assert len(rows) == 1
    assert rows[0]["capability"] == "search"
    assert rows[0]["query"] == "hello"
    assert rows[0]["success"] == 0  # 无供应商
    assert rows[0]["token_name"] == "test-agent"


def test_history_filters_and_pagination(admin_client, caller_token):
    headers = {"Authorization": f"Bearer {caller_token}"}
    for i in range(5):
        admin_client.get("/v1/search", params={"q": f"q{i}"}, headers=headers)
    r = admin_client.get("/api/admin/history", params={"limit": 2})
    assert len(r.json()["data"]["rows"]) == 2
    r = admin_client.get("/api/admin/history", params={"limit": 2, "offset": 2})
    assert len(r.json()["data"]["rows"]) == 2
    r = admin_client.get("/api/admin/history", params={"q": "q3"})
    assert len(r.json()["data"]["rows"]) == 1
    r = admin_client.get("/api/admin/history", params={"capability": "extract"})
    assert r.json()["data"]["rows"] == []


def test_history_negative_limit_is_clamped(admin_client, caller_token):
    headers = {"Authorization": f"Bearer {caller_token}"}
    for i in range(3):
        admin_client.get("/v1/search", params={"q": f"q{i}"}, headers=headers)
    r = admin_client.get("/api/admin/history", params={"limit": -5})
    assert r.status_code == 200
    rows = r.json()["data"]["rows"]
    assert len(rows) == 0


def test_stats_summary_and_timeseries(admin_client, caller_token):
    headers = {"Authorization": f"Bearer {caller_token}"}
    for i in range(3):
        admin_client.get("/v1/search", params={"q": f"q{i}"}, headers=headers)
    r = admin_client.get("/api/admin/stats/summary")
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total"] == 3
    assert data["searches"] == 3
    assert data["extracts"] == 0
    assert data["success"] == 0
    assert data["success_rate"] == 0.0
    assert "providers" in data
    r = admin_client.get("/api/admin/stats/timeseries")
    rows = r.json()["data"]["rows"]
    assert len(rows) >= 1
    assert sum(x["count"] for x in rows) == 3


def test_history_has_full_flag_and_endpoint(admin_client, caller_token):
    headers = {"Authorization": f"Bearer {caller_token}"}
    # 无供应商时 search 失败 → web 为空，全量 items 为空
    r = admin_client.get("/v1/search", params={"q": "hello"}, headers=headers)
    assert r.status_code == 200
    rows = admin_client.get("/api/admin/history").json()["data"]["rows"]
    row = rows[0]
    assert "has_full" in row
    assert row["has_full"] == 1  # 失败响应也记录全量（空 items）
    full = admin_client.get(f"/api/admin/history/{row['id']}/full")
    assert full.status_code == 200
    data = full.json()["data"]["response_full"]
    import json
    parsed = json.loads(data)
    assert "items" in parsed
    assert parsed["items"] == []


def test_history_full_search_items(admin_client, caller_token):
    import json
    from searchhub.models import SearchItem
    from searchhub.providers.ddg import DdgProvider

    headers = {"Authorization": f"Bearer {caller_token}"}
    body = {"id": "ddg", "capabilities": ["search"], "enabled": True,
            "weight": 10, "priority": 100, "max_results": 8, "base_url": None,
            "key_pool": {"max_concurrency": 2, "rps_limit": 10, "cooldown_s": 60},
            "options": {}}
    assert admin_client.post("/api/admin/providers", json=body).status_code == 200
    original = DdgProvider.search

    async def fake_search(self, query, limit):
        return [SearchItem(title=f"t{i}", url=f"https://a{i}.example",
                           description="d1", position=i, provider="ddg")
                for i in range(3)]

    DdgProvider.search = fake_search
    try:
        admin_client.get("/v1/search", params={"q": "hello"}, headers=headers)
    finally:
        DdgProvider.search = original
    rows = admin_client.get("/api/admin/history").json()["data"]["rows"]
    row = rows[0]
    full = json.loads(
        admin_client.get(f"/api/admin/history/{row['id']}/full").json()["data"]["response_full"])
    assert len(full["items"]) == 3
    assert full["items"][0]["title"] == "t0"
    assert full["items"][0]["url"] == "https://a0.example"
    assert full["items"][0]["provider"] == "ddg"


def test_history_full_extract_and_redaction(admin_client, caller_token):
    import json
    from searchhub.models import ExtractItem
    from searchhub.providers.trafilatura_py import TrafilaturaProvider
    from searchhub.config import ConfigService

    headers = {"Authorization": f"Bearer {caller_token}"}
    body = {"id": "trafilatura", "capabilities": ["extract"], "enabled": True,
            "weight": 10, "priority": 100, "max_results": 8, "base_url": None,
            "key_pool": {"max_concurrency": 2, "rps_limit": 10, "cooldown_s": 60},
            "options": {}}
    assert admin_client.post("/api/admin/providers", json=body).status_code == 200
    original = TrafilaturaProvider.extract

    async def fake_extract(self, urls, fmt="markdown", max_chars=15000, include_raw=True):
        return [ExtractItem(url="https://b.example", title="t", content="c" * 100,
                            provider="trafilatura")]

    TrafilaturaProvider.extract = fake_extract
    try:
        r = admin_client.post("/v1/extract", json={"urls": ["https://b.example"]},
                              headers=headers)
        assert r.status_code == 200
    finally:
        TrafilaturaProvider.extract = original
    rows = admin_client.get("/api/admin/history").json()["data"]["rows"]
    assert rows[0]["capability"] == "extract"
    row = rows[0]
    full = json.loads(
        admin_client.get(f"/api/admin/history/{row['id']}/full").json()["data"]["response_full"])
    assert full["items"][0]["content"] == "c" * 100
