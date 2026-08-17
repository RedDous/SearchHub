from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Annotated

import httpx
from fastapi.responses import JSONResponse
from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field
from starlette.routing import BaseRoute, Match, compile_path

from searchhub.api.auth import _authorized
from searchhub.config import ConfigService
from searchhub.orchestrator import SearchHubEngine
from searchhub.storage.cache import CacheRepo
from searchhub.storage.history import RequestLogRepo

logger = logging.getLogger(__name__)

_engine: SearchHubEngine | None = None


def set_engine(engine: SearchHubEngine | None) -> None:
    global _engine
    _engine = engine


def _get_engine() -> SearchHubEngine:
    if _engine is None:
        raise RuntimeError("MCP engine not set")
    return _engine


def create_mcp_server() -> MCPServer:
    mcp = MCPServer("SearchHub")

    @mcp.tool()
    async def web_search(
        query: str,
        limit: Annotated[int, Field(ge=1, le=50)] = 5,
        providers: str | None = None,
        strategy: str | None = None,
    ) -> str:
        """Search the web and return results as a JSON string."""
        resp = await _get_engine().search(
            query, limit=limit, providers=providers, strategy=strategy)
        if not resp.success:
            return json.dumps({"success": False, "error": resp.error}, ensure_ascii=False)
        return json.dumps(resp.data.model_dump(), ensure_ascii=False)

    @mcp.tool()
    async def web_extract(
        urls: list[str],
        format: str = "markdown",
        max_chars: Annotated[int, Field(ge=100, le=1_000_000)] = 15000,
    ) -> str:
        """Extract content from web pages and return a JSON string."""
        resp = await _get_engine().extract(urls, fmt=format, max_chars=max_chars)
        if not resp.success:
            return json.dumps({"success": False, "error": resp.error}, ensure_ascii=False)
        return json.dumps([i.model_dump() for i in resp.data], ensure_ascii=False)

    return mcp


async def _run_stdio() -> None:
    data_dir = Path(os.environ.get("SEARCHHUB_DATA", "data"))
    config = ConfigService(data_dir)
    config.load()
    cache = CacheRepo(data_dir / "cache.db")
    http = httpx.AsyncClient(timeout=60)
    history = RequestLogRepo(data_dir / "history.db")
    engine = SearchHubEngine(config, cache, http, history=history)
    engine.maybe_reload()
    set_engine(engine)
    try:
        await create_mcp_server().run_stdio_async()
    finally:
        await http.aclose()
        await cache.close()
        await history.close()


def main() -> None:
    asyncio.run(_run_stdio())


class _ExactPathRoute(BaseRoute):
    """Dispatch an ASGI app for exactly one path, without prefix stripping.

    Starlette 1.6 Mounts only match sub-paths (``/mcp/x``), letting a
    ``/{full_path:path}`` catch-all swallow the bare ``/mcp``. This route
    matches the exact path so the raw MCP ASGI app runs on POST /mcp.
    """

    def __init__(self, path: str, app):
        self.path_regex, _, _ = compile_path(path)
        self.app = app

    def matches(self, scope):
        if scope["type"] not in ("http", "websocket"):
            return Match.NONE, {}
        if self.path_regex.match(scope["path"]):
            return Match.FULL, {}
        return Match.NONE, {}

    async def handle(self, scope, receive, send):
        await self.app(scope, receive, send)


def _auth_wrap(inner_app):
    """Wrap an ASGI app so HTTP requests require a valid bearer token."""

    async def app(scope, receive, send):
        if scope["type"] != "http":
            await inner_app(scope, receive, send)
            return
        token = None
        for key, value in scope["headers"]:
            if key.lower() == b"authorization":
                header = value.decode("latin-1")
                if header.startswith("Bearer "):
                    token = header[len("Bearer "):].strip()
                break
        if token is None:
            response = JSONResponse({"success": False, "error": "invalid token"},
                                    status_code=401)
            await response(scope, receive, send)
            return
        engine = _get_engine()
        engine.config.maybe_reload()
        if _authorized(engine.config.get(), token) is None:
            response = JSONResponse({"success": False, "error": "invalid token"},
                                    status_code=401)
            await response(scope, receive, send)
            return
        await inner_app(scope, receive, send)

    return app


def build_mcp_asgi(mcp_server: MCPServer | None = None):
    if mcp_server is None:
        mcp_server = create_mcp_server()
    sdk_app = mcp_server.streamable_http_app(
        json_response=True,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    return _auth_wrap(sdk_app)


def build_mcp_route(mcp_server: MCPServer) -> _ExactPathRoute:
    """Return a route serving the authenticated MCP app at exactly /mcp."""
    return _ExactPathRoute("/mcp", build_mcp_asgi(mcp_server))