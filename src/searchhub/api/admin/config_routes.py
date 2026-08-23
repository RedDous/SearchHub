from __future__ import annotations

import asyncio
import time
from dataclasses import asdict

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel

from searchhub.api.admin.session import require_admin
from searchhub.config import CacheConfig, HistoryConfig, ProviderConfig, StrategyConfig
from searchhub import build_info
from searchhub.providers import PROVIDER_CLASSES
from searchhub.providers.schema import validate_provider_config

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
    info = build_info()
    return {"success": True, "data": {"config": data,
                                      "config_version": svc.config_version,
                                      "updated_at": svc.updated_at,
                                      "password_is_default": svc.verify_admin_password("admin"),
                                      "version": info["version"],
                                      "commit": info["commit"],
                                      "provider_status": _provider_status_map(request.app.state.engine)}}


def _save(svc, cfg) -> None:
    try:
        svc.save_config(cfg)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/provider-types")
async def provider_types():
    types = [asdict(PROVIDER_CLASSES[pid].schema)
             for pid in sorted(PROVIDER_CLASSES)]
    return {"success": True, "data": {"types": types}}


@router.post("/providers")
async def create_provider(body: ProviderConfig, request: Request, background: BackgroundTasks):
    svc = request.app.state.engine.config
    svc.maybe_reload()
    if svc.get().provider(body.id) is not None:
        raise HTTPException(status_code=409, detail=f"provider {body.id} already exists")
    schema = PROVIDER_CLASSES[body.id].schema if body.id in PROVIDER_CLASSES else None
    errors = validate_provider_config(body.id, body.capabilities, body.base_url, schema)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    cfg = svc.get()
    cfg.providers.append(body)
    _save(svc, cfg)
    background.add_task(_auto_retest, request.app.state.engine, body.id)
    return {"success": True}


@router.put("/providers/{provider_id}")
async def update_provider(provider_id: str, body: ProviderConfig, request: Request, background: BackgroundTasks):
    svc = request.app.state.engine.config
    svc.maybe_reload()
    cfg = svc.get()
    idx = next((i for i, p in enumerate(cfg.providers) if p.id == provider_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"provider {provider_id} not found")
    if body.id != provider_id:
        raise HTTPException(status_code=400, detail="provider id in body must match path")
    schema = PROVIDER_CLASSES[body.id].schema if body.id in PROVIDER_CLASSES else None
    errors = validate_provider_config(body.id, body.capabilities, body.base_url, schema)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    cfg.providers[idx] = body
    _save(svc, cfg)
    background.add_task(_auto_retest, request.app.state.engine, body.id)
    return {"success": True}


@router.delete("/providers/{provider_id}")
async def delete_provider(provider_id: str, request: Request):
    svc = request.app.state.engine.config
    svc.maybe_reload()
    cfg = svc.get()
    new = [p for p in cfg.providers if p.id != provider_id]
    if len(new) == len(cfg.providers):
        raise HTTPException(status_code=404, detail=f"provider {provider_id} not found")
    cfg.providers = new
    _save(svc, cfg)
    request.app.state.engine.provider_tests.pop(provider_id, None)
    return {"success": True}


async def _probe(provider, cap: str) -> dict:
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


def _record_test(engine, provider_id: str, result: dict) -> dict:
    entry: dict = {"success": bool(result.get("success")), "at": time.time()}
    data = result.get("data")
    if data:
        entry.update({"capability": data.get("capability"), "count": data.get("count"),
                      "took_ms": data.get("took_ms")})
    if result.get("error"):
        entry["error"] = result["error"]
    engine.provider_tests[provider_id] = entry
    return result


def _provider_status_map(engine) -> dict:
    """每个已配置供应商的可用性：配置完整性（缺 Key/缺地址）优先，其次最近一次探测结果。"""
    svc = engine.config
    out: dict[str, dict] = {}
    for pc in svc.get().providers:
        cls = PROVIDER_CLASSES.get(pc.id)
        schema = cls.schema if cls else None
        if schema and schema.requires_key and not svc.provider_keys(pc.id):
            out[pc.id] = {"status": "missing_key", "test": None}
        elif schema and schema.requires_base_url and not pc.base_url:
            out[pc.id] = {"status": "missing_base_url", "test": None}
        elif pc.id in engine.provider_tests:
            test = engine.provider_tests[pc.id]
            out[pc.id] = {"status": "ok" if test["success"] else "failed", "test": test}
        else:
            out[pc.id] = {"status": "untested", "test": None}
    return out


async def _auto_retest(engine, provider_id: str):
    """配置/Key 变更后的后台自动探测：完整才联网，缺 Key/缺地址直接清记录。"""
    svc = engine.config
    svc.maybe_reload()
    pc = next((p for p in svc.get().providers if p.id == provider_id), None)
    if pc is None:
        engine.provider_tests.pop(provider_id, None)
        return
    cls = PROVIDER_CLASSES.get(provider_id)
    schema = cls.schema if cls else None
    if (schema and schema.requires_key and not svc.provider_keys(provider_id)) or (
            schema and schema.requires_base_url and not pc.base_url):
        engine.provider_tests.pop(provider_id, None)
        return
    if cls is None:
        engine.provider_tests.pop(provider_id, None)
        return
    keys = svc.provider_keys(provider_id)
    cap = "search" if "search" in pc.capabilities else "extract"
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            provider = cls(pc, keys, http)
            result = await _probe(provider, cap)
    except Exception as e:
        result = {"success": False, "error": f"{type(e).__name__}: {e}"}
    _record_test(engine, provider_id, result)


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
        return _record_test(request.app.state.engine, provider_id, await _probe(provider, cap))


@router.post("/providers/test")
async def test_provider_draft(body: ProviderConfig, request: Request):
    """用表单中未保存的配置测试（新建模式）。供应商需为已知类型。"""
    svc = request.app.state.engine.config
    svc.maybe_reload()
    cls = PROVIDER_CLASSES.get(body.id)
    if cls is None:
        raise HTTPException(status_code=404,
                            detail=f"provider {body.id} not found or unsupported")
    schema = cls.schema
    errors = validate_provider_config(body.id, body.capabilities, body.base_url, schema)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    keys = svc.provider_keys(body.id)
    async with httpx.AsyncClient(timeout=10) as http:
        provider = cls(body, keys, http)
        cap = "search" if "search" in body.capabilities else "extract"
        return _record_test(request.app.state.engine, body.id, await _probe(provider, cap))


@router.put("/settings")
async def update_settings(body: SettingsBody, request: Request):
    svc = request.app.state.engine.config
    svc.maybe_reload()
    cfg = svc.get()
    if body.strategy is not None:
        cfg.strategy = body.strategy
    if body.cache is not None:
        cfg.cache = body.cache
    if body.history is not None:
        cfg.history = body.history
    _save(svc, cfg)
    return {"success": True, "data": {"config_version": svc.config_version}}
