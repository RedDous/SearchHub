from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from searchhub.api.routes_health import router as health_router


def create_app(data_dir: Path | None = None) -> FastAPI:
    data_dir = Path(data_dir) if data_dir else Path.cwd() / "data"
    app = FastAPI(title="SearchHub", version="0.1.0")
    app.state.data_dir = data_dir
    app.include_router(health_router)
    return app
