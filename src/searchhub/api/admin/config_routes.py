from __future__ import annotations

import asyncio
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from searchhub.api.admin.session import require_admin
from searchhub.config import CacheConfig, HistoryConfig, ProviderConfig, StrategyConfig
from searchhub.providers import PROVIDER_CLASSES

router = APIRouter(prefix="/api/admin", tags=["admin"],
                   dependencies=[Depends(require_admin)])


class SettingsBody(BaseModel):
    strategy: StrategyConfig | None = None
    cache: CacheConfig | None = None
    history: HistoryConfig | None = None


@router.get("/config")
async def get_config(request: Request):
    svc = request.app.state.engine.config
    svc.maybe_reload()
    cfg = svc.get()
    data = cfg.model_dump(mode="json")
    data["admin"]["password_hash"] = ""
    for t in data["auth"]["tokens"]:
        t["token_hash"] = t["token_hash"][:8] + "****"
    return {"success": True, "data": {"config": data,
                                      "config_version": svc.config_version,
                                      "updated_at": svc.updated_at}}


def _save(svc, cfg) -> None:
    try:
        svc.save_config(cfg)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/providers")
async def create_provider(body: ProviderConfig, request: Request):
    svc = request.app.state.engine.config
    if svc.get().provider(body.id) is not None:
        raise HTTPException(status_code=409, detail=f"provider {body.id} already exists")
    cfg = svc.get()
    cfg.providers.append(body)
    _save(svc, cfg)
    return {"success": True}


@router.put("/providers/{provider_id}")
async def update_provider(provider_id: str, body: ProviderConfig, request: Request):
    svc = request.app.state.engine.config
    cfg = svc.get()
    idx = next((i for i, p in enumerate(cfg.providers) if p.id == provider_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"provider {provider_id} not found")
    if body.id != provider_id:
        raise HTTPException(status_code=400, detail="provider id in body must match path")
    cfg.providers[idx] = body
    _save(svc, cfg)
    return {"success": True}


@router.delete("/providers/{provider_id}")
async def delete_provider(provider_id: str, request: Request):
    svc = request.app.state.engine.config
    cfg = svc.get()
    new = [p for p in cfg.providers if p.id != provider_id]
    if len(new) == len(cfg.providers):
        raise HTTPException(status_code=404, detail=f"provider {provider_id} not found")
    cfg.providers = new
    _save(svc, cfg)
    return {"success": True}


@router.post("/providers/{provider_id}/test")
async def test_provider(provider_id: str, request: Request):
    svc = request.app.state.engine.config
    svc.maybe_reload()
    pc = svc.get().provider(provider_id)
    cls = PROVIDER_CLASSES.get(provider_id)
    if pc is None or cls is None:
        raise HTTPException(status_code=404,
                            detail=f"provider {provider_id} not found or unsupported")
    keys = svc.provider_keys(provider_id)
    async with httpx.AsyncClient(timeout=10) as http:
        provider = cls(pc, keys, http)
        cap = "search" if "search" in pc.capabilities else "extract"
        try:
            start = time.monotonic()
            if cap == "search":
                items = await asyncio.wait_for(provider.search("searchhub connection test", 1), 10)
            else:
                items = await asyncio.wait_for(
                    provider.extract(["https://example.com"], max_chars=200), 10)
            return {"success": True, "data": {"capability": cap, "count": len(items),
                                              "took_ms": round(
                                                  (time.monotonic() - start) * 1000, 1)}}
        except Exception as e:
            return {"success": False, "error": f"{type(e).__name__}: {e}"}


@router.put("/settings")
async def update_settings(body: SettingsBody, request: Request):
    svc = request.app.state.engine.config
    cfg = svc.get()
    if body.strategy is not None:
        cfg.strategy = body.strategy
    if body.cache is not None:
        cfg.cache = body.cache
    if body.history is not None:
        cfg.history = body.history
    _save(svc, cfg)
    return {"success": True, "data": {"config_version": svc.config_version}}
