import hashlib

import pytest
from fastapi.testclient import TestClient

from searchhub.api.app import create_app
from searchhub.config import AuthConfig, ConfigService, ProviderConfig, TokenEntry


def test_providers_lists_capabilities(data_dir):
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.auth = AuthConfig(tokens=[TokenEntry(name="t", token_hash=hashlib.sha256(b"tok").hexdigest())])
    cfg.providers = [
        ProviderConfig(id="ddg", capabilities=["search"]),
        ProviderConfig(id="trafilatura", capabilities=["extract"]),
    ]
    cs.save_config(cfg)
    with TestClient(create_app(data_dir)) as c:
        r = c.get("/v1/providers", headers={"Authorization": "Bearer tok"})
    assert r.status_code == 200
    caps = {p["id"]: p["capabilities"] for p in r.json()}
    assert caps["ddg"] == ["search"]
    assert caps["trafilatura"] == ["extract"]
