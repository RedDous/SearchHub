"""MCP HTTP 鉴权层：Bearer token 名 → contextvar → 历史"调用方"。"""

import hashlib

import pytest
from fastapi.testclient import TestClient

from searchhub.config import TokenEntry
from searchhub.mcp_server import _auth_wrap, set_engine


def _asgi_echo_contextvar(var):
    """构造一个把 contextvar 当前值回写进响应体的微型 ASGI app。"""

    async def app(scope, receive, send):
        body = var.get().encode()
        await send({"type": "http.response.start",
                    "status": 200, "headers": [(b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

    return app


@pytest.fixture
def mcp_authed_app(app):
    from searchhub.mcp_server import _token_name

    with TestClient(app):
        set_engine(app.state.engine)
        inner = _asgi_echo_contextvar(_token_name)
        yield TestClient(_auth_wrap(inner))
        set_engine(None)


def test_mcp_auth_records_token_name(mcp_authed_app, data_dir):
    from searchhub.config import ConfigService

    cs = ConfigService(data_dir)
    cs.load()
    cfg = cs.get()
    cfg.auth.tokens.append(TokenEntry(
        name="opencode", token_hash=hashlib.sha256(b"secret-token").hexdigest()))
    cs.save_config(cfg)

    # 无 token → 401
    assert mcp_authed_app.get("/").status_code == 401
    # 无效 token → 401
    assert mcp_authed_app.get("/", headers={
        "Authorization": "Bearer wrong"}).status_code == 401
    # 有效 token → contextvar 携带令牌名
    r = mcp_authed_app.get("/", headers={"Authorization": "Bearer secret-token"})
    assert r.status_code == 200
    assert r.text == "opencode"