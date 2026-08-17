from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from searchhub import __version__
from searchhub.api.admin.config_routes import router as admin_config_router
from searchhub.api.admin.keys_routes import router as admin_keys_router
from searchhub.api.admin.session import SessionStore, router as admin_session_router
from searchhub.api.admin.stats_routes import router as admin_stats_router
from searchhub.api.admin.token_routes import router as admin_token_router
from searchhub.api.routes_extract import router as extract_router
from searchhub.api.routes_health import router as health_router
from searchhub.api.routes_providers import router as providers_router
from searchhub.api.routes_search import router as search_router
from searchhub.config import ConfigService
from searchhub.mcp_server import build_mcp_route, create_mcp_server, set_engine as mcp_set_engine
from searchhub.orchestrator import SearchHubEngine
from searchhub.storage.cache import CacheRepo
from searchhub.storage.history import RequestLogRepo

logger = logging.getLogger(__name__)


async def _cleanup_loop(history: RequestLogRepo, cache: CacheRepo | None,
                        config: ConfigService) -> None:
    while True:
        try:
            cfg = config.get()
            await history.purge_before(time.time() - cfg.history.retention_days * 86400)
            if cache is not None:
                await cache.purge_expired()
        except Exception:
            logger.exception("cleanup loop error")
        await asyncio.sleep(3600)


def create_app(data_dir: Path | None = None) -> FastAPI:
    data_dir = Path(data_dir) if data_dir else Path.cwd() / "data"
    mcp_server = create_mcp_server()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        config = ConfigService(data_dir)
        config.load()
        cache = CacheRepo(data_dir / "cache.db")
        http = httpx.AsyncClient(timeout=60)
        history = RequestLogRepo(data_dir / "history.db")
        cfg = config.get()
        if not cfg.admin.password_hash:
            default = os.environ.get("ADMIN_PASSWORD") or "admin"
            if not os.environ.get("ADMIN_PASSWORD"):
                logger.warning("ADMIN_PASSWORD not set — using default password 'admin'. "
                               "Change it from the UI as soon as possible.")
            config.set_admin_password(default)
        engine = SearchHubEngine(config, cache, http, history=history)
        engine.maybe_reload()
        mcp_set_engine(engine)
        app.state.engine = engine
        app.state.http = http
        app.state.history = history
        app.state.data_dir = data_dir
        app.state.mcp = mcp_server
        app.state.session_store = SessionStore(config.session_secret())
        cleanup_task = asyncio.create_task(_cleanup_loop(history, cache, config))
        async with mcp_server.session_manager.run():
            yield
        cleanup_task.cancel()
        await http.aclose()
        await cache.close()
        await history.close()

    app = FastAPI(title="SearchHub", version=__version__, lifespan=lifespan)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code,
                            content={"success": False, "error": exc.detail})

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        errors = exc.errors()
        first = errors[0] if errors else {}
        loc = ".".join(str(p) for p in first.get("loc", ()))
        msg = first.get("msg", "invalid request")
        summary = f"{loc}: {msg}" if loc else msg
        return JSONResponse(status_code=422,
                            content={"success": False, "error": f"validation error: {summary}"})

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception in %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500,
                            content={"success": False, "error": "internal error"})

    app.include_router(health_router)
    app.include_router(search_router)
    app.include_router(extract_router)
    app.include_router(providers_router)
    app.include_router(admin_session_router)
    app.include_router(admin_config_router)
    app.include_router(admin_keys_router)
    app.include_router(admin_token_router)
    app.include_router(admin_stats_router)

    # Exact-path route (not a Mount): Starlette 1.6 mounts only match
    # sub-paths, which would let the static catch-all below swallow /mcp.
    app.router.routes.append(build_mcp_route(mcp_server))

    dist = Path(os.environ.get("SEARCHHUB_WEB_DIST", "")) if os.environ.get("SEARCHHUB_WEB_DIST") else Path(__file__).resolve().parents[3] / "frontend" / "dist"
    if dist.is_dir():
        assets_dir = dist / "assets"
        if assets_dir.is_dir():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        index_html = dist / "index.html"

        @app.get("/{full_path:path}", include_in_schema=False)
        async def spa_fallback(full_path: str):
            if full_path in {"api", "v1"} or full_path.startswith(("api/", "v1/", "healthz", "readyz")):
                raise HTTPException(404, "not found")
            if any(seg == ".." for seg in full_path.split("/")) or "\\" in full_path:
                raise HTTPException(404, "not found")
            target = (dist / full_path).resolve()
            if not target.is_relative_to(dist.resolve()):
                raise HTTPException(404, "not found")
            if full_path and target.is_file():
                return FileResponse(target)
            if not index_html.is_file():
                raise HTTPException(404, "not found")
            return FileResponse(index_html)

        @app.get("/", include_in_schema=False)
        async def spa_index():
            if not index_html.is_file():
                raise HTTPException(404, "not found")
            return FileResponse(index_html)

    return app
