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
    cfg.providers = [ProviderConfig(id="trafilatura", capabilities=["extract"])]
    cs.save_config(cfg)
    app = create_app(data_dir)
    with TestClient(app) as c:
        yield c


AUTH = {"Authorization": "Bearer tok"}


def test_extract_get_and_post(client):
    from searchhub.models import ExtractItem
    from searchhub.providers.trafilatura_py import TrafilaturaProvider

    original = TrafilaturaProvider.extract

    async def fake_extract(self, urls, fmt="markdown", max_chars=15000):
        return [ExtractItem(url=u, title="TT", content=f"c-{u}", provider="trafilatura") for u in urls]

    TrafilaturaProvider.extract = fake_extract
    try:
        r = client.get("/v1/extract", params={"urls": "https://a.com,https://b.com"}, headers=AUTH)
        post = client.post("/v1/extract", json={"urls": ["https://a.com"]}, headers=AUTH)
    finally:
        TrafilaturaProvider.extract = original
    assert r.status_code == 200
    assert [i["url"] for i in r.json()["data"]] == ["https://a.com", "https://b.com"]
    assert post.json()["data"][0]["title"] == "TT"


def test_extract_include_raw_false(client):
    from searchhub.models import ExtractItem
    from searchhub.providers.trafilatura_py import TrafilaturaProvider

    original = TrafilaturaProvider.extract

    async def fake_extract(self, urls, fmt="markdown", max_chars=15000):
        return [ExtractItem(url=u, content="c", raw_content="RAW", provider="trafilatura") for u in urls]

    TrafilaturaProvider.extract = fake_extract
    try:
        r = client.get("/v1/extract", params={"urls": "https://a.com", "include_raw": "false"}, headers=AUTH)
    finally:
        TrafilaturaProvider.extract = original
    assert r.json()["data"][0]["raw_content"] == ""


def test_extract_invalid_format(client):
    r = client.get("/v1/extract", params={"urls": "https://a.com", "format": "pdf"}, headers=AUTH)
    assert r.status_code == 400
