from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Annotated

import httpx
from mcp.server.mcpserver import MCPServer
from pydantic import Field

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


def build_mcp_asgi():
    return create_mcp_server().streamable_http_app()