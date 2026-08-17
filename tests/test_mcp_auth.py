from fastapi.testclient import TestClient

from searchhub.api.app import create_app
from searchhub.config import ConfigService, TokenEntry
import hashlib


def make_client(data_dir, tokens=()):
    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.auth.tokens = list(tokens)
    cs.save_config(cfg)
    return TestClient(create_app(data_dir))


def test_mcp_requires_token(data_dir):
    with make_client(data_dir) as c:
        r = c.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                 "params": {"protocolVersion": "2025-03-26",
                                            "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}})
        assert r.status_code == 401
        body = r.json()
        assert body["success"] is False
        assert body["error"] == "invalid token"


def test_mcp_rejects_wrong_token(data_dir):
    with make_client(data_dir) as c:
        r = c.post("/mcp", headers={"Authorization": "Bearer wrong"},
                   json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2025-03-26",
                                    "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}})
        assert r.status_code == 401


def test_mcp_accepts_valid_token(data_dir):
    token = "sekrit-token"
    entry = TokenEntry(name="t", token_hash=hashlib.sha256(token.encode()).hexdigest())
    with make_client(data_dir, tokens=[entry]) as c:
        r = c.post("/mcp", headers={"Authorization": f"Bearer {token}"},
                   json={"jsonrpc": "2.0", "id": 1, "method": "initialize",
                         "params": {"protocolVersion": "2025-03-26",
                                    "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}})
        assert r.status_code == 200
        assert "result" in r.json()


def test_mcp_mount_does_not_break_existing_routes(data_dir):
    with make_client(data_dir) as c:
        assert c.get("/healthz").status_code == 200
        assert c.get("/v1/providers").status_code == 401  # 调用方 token 校验仍在
        assert c.get("/api/admin/config").status_code == 401  # admin 会话仍在
