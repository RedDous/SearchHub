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
