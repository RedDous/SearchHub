from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from searchhub import __version__
from searchhub.api.routes_extract import router as extract_router
from searchhub.api.routes_health import router as health_router
from searchhub.api.routes_providers import router as providers_router
from searchhub.api.routes_search import router as search_router
from searchhub.config import ConfigService
from searchhub.orchestrator import SearchHubEngine
from searchhub.storage.cache import CacheRepo

logger = logging.getLogger(__name__)


def create_app(data_dir: Path | None = None) -> FastAPI:
    data_dir = Path(data_dir) if data_dir else Path.cwd() / "data"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        config = ConfigService(data_dir)
        config.load()
        cache = CacheRepo(data_dir / "cache.db")
        http = httpx.AsyncClient(timeout=60)
        engine = SearchHubEngine(config, cache, http)
        engine.maybe_reload()
        app.state.engine = engine
        app.state.http = http
        yield
        await http.aclose()
        await cache.close()

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
    return app
