from __future__ import annotations

import asyncio
import time
from dataclasses import asdict

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, ValidationError

from searchhub.api.admin.session import require_admin
from searchhub.config import CacheConfig, HistoryConfig, ProviderConfig, StrategyConfig
from searchhub import build_info
from searchhub.providers import PROVIDER_CLASSES
from searchhub.providers.options import validate_options
from searchhub.providers.schema import ProviderSchema, TestSpec, validate_provider_config

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


def _schema_for_type(provider_type: str) -> ProviderSchema | None:
    """按适配器类型解析 schema；未知类型返回 None。"""
    cls = PROVIDER_CLASSES.get(provider_type)
    return cls.schema if cls is not None else None


def _validated_options(provider_type: str, raw: dict) -> dict:
    """校验并归一化 options（补全默认值）；未知键 → 400。"""
    try:
        return validate_options(provider_type, raw)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=f"invalid options: {e}") from e


def _schema_dict(schema: ProviderSchema) -> dict:
    """Serialize a schema, keeping the legacy derived flags in the response."""
    data = asdict(schema)
    data.update(
        requires_key=schema.requires_key,
        optional_key=schema.optional_key,
        requires_base_url=schema.requires_base_url,
        key_prefix=schema.key_prefix,
        show_max_results=schema.show_max_results,
        show_options=schema.show_options,
    )
    return data


@router.get("/provider-types")
async def provider_types():
    types = [_schema_dict(PROVIDER_CLASSES[pid].schema)
             for pid in sorted(PROVIDER_CLASSES)]
    return {"success": True, "data": {"types": types}}


@router.post("/providers")
async def create_provider(body: ProviderConfig, request: Request, background: BackgroundTasks):
    svc = request.app.state.engine.config
    svc.maybe_reload()
    if svc.get().provider(body.id) is not None:
        raise HTTPException(status_code=409, detail=f"provider {body.id} already exists")
    schema = _schema_for_type(body.type)
    if schema is None:
        raise HTTPException(status_code=400, detail=f"unknown provider type: {body.type!r}")
    errors = validate_provider_config(body.id, body.capabilities, body.base_url, schema)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    body.options = _validated_options(body.type, body.options)
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
    existing = cfg.providers[idx]
    if "type" in body.model_fields_set:
        if body.type != existing.type:
            raise HTTPException(status_code=400, detail="provider type cannot be changed")
    else:
        body.type = existing.type
    schema = _schema_for_type(body.type)
    if schema is None:
        raise HTTPException(status_code=400, detail=f"unknown provider type: {body.type!r}")
    errors = validate_provider_config(body.id, body.capabilities, body.base_url, schema)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    body.options = _validated_options(body.type, body.options)
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


async def _probe(provider, capability: str, spec: TestSpec) -> dict:
    """Run one capability probe described by the schema's TestSpec.

    The returned dict is the public per-capability result shape:
    ``{capability, success, count, took_ms, error?}``.
    """
    start = time.monotonic()
    try:
        if capability == "search":
            items = await asyncio.wait_for(
                provider.search(spec.query or "searchhub connection test", 1), 10)
            count = len(items)
            error = None
            if count < spec.min_results:
                error = (f"expected at least {spec.min_results} results, "
                         f"got {count}")
        else:
            items = await asyncio.wait_for(
                provider.extract(list(spec.urls) or ["https://example.com"],
                                 max_chars=spec.max_chars), 10)
            count = len(items)
            item_errors = [item.error for item in items if item.error]
            if item_errors:
                error = item_errors[0]
            elif spec.expect_content and (
                    not items
                    or any(not (item.content or "").strip() for item in items)):
                error = "extract returned empty content"
            else:
                error = None
        result = {"capability": capability, "success": error is None,
                  "count": count,
                  "took_ms": round((time.monotonic() - start) * 1000, 1)}
        if error is not None:
            result["error"] = error
        return result
    except Exception as e:
        return {"capability": capability, "success": False, "count": 0,
                "took_ms": round((time.monotonic() - start) * 1000, 1),
                "error": f"{type(e).__name__}: {e}"}


_DEFAULT_TESTS: dict[str, TestSpec] = {
    "search": TestSpec(capability="search", query="searchhub connection test"),
    "extract": TestSpec(capability="extract", urls=("https://example.com",),
                        expect_content=True),
}


def _test_specs(schema: ProviderSchema | None,
                capabilities: list[str]) -> list[TestSpec]:
    """Resolve the TestSpec for each enabled capability (defaults if absent)."""
    declared = {t.capability: t for t in (schema.tests if schema else ())}
    return [declared.get(cap, _DEFAULT_TESTS.get(cap, TestSpec(capability=cap)))
            for cap in capabilities]


async def _run_tests(provider, specs: list[TestSpec]) -> list[dict]:
    return [await _probe(provider, spec.capability, spec) for spec in specs]


def _record_test(engine, provider_id: str, results: list[dict]) -> dict:
    for result in results:
        engine.record_test(provider_id, result["capability"],
                           success=bool(result.get("success")),
                           count=result.get("count", 0),
                           took_ms=result.get("took_ms", 0.0),
                           error=result.get("error"))
    return {"success": True, "data": {"results": results}}


def _provider_status_map(engine) -> dict:
    """每个已配置供应商的可用性：配置完整性（缺 Key/缺地址）优先，其次各能力探测结果。"""
    svc = engine.config
    out: dict[str, dict] = {}
    for pc in svc.get().providers:
        cls = PROVIDER_CLASSES.get(pc.type)
        schema = cls.schema if cls else None
        if schema and schema.requires_key and not svc.provider_keys(pc.id):
            out[pc.id] = {"status": "missing_key", "test": None, "tests": {}}
        elif schema and schema.requires_base_url and not pc.base_url:
            out[pc.id] = {"status": "missing_base_url", "test": None, "tests": {}}
        else:
            tests = engine.provider_tests.get(pc.id, {})
            if any(not t["success"] for t in tests.values()):
                status = "failed"
            elif any(t["success"] for t in tests.values()):
                status = "ok"
            else:
                status = "untested"
            latest = max(tests.values(), key=lambda t: t["at"]) if tests else None
            out[pc.id] = {"status": status, "test": latest, "tests": tests}
    return out


async def _auto_retest(engine, provider_id: str):
    """配置/Key 变更后的后台自动探测：完整才联网，缺 Key/缺地址直接清记录。"""
    svc = engine.config
    svc.maybe_reload()
    pc = next((p for p in svc.get().providers if p.id == provider_id), None)
    if pc is None:
        engine.provider_tests.pop(provider_id, None)
        return
    cls = PROVIDER_CLASSES.get(pc.type)
    schema = cls.schema if cls else None
    if (schema and schema.requires_key and not svc.provider_keys(provider_id)) or (
            schema and schema.requires_base_url and not pc.base_url):
        engine.provider_tests.pop(provider_id, None)
        return
    if cls is None:
        engine.provider_tests.pop(provider_id, None)
        return
    keys = svc.provider_keys(provider_id)
    specs = _test_specs(schema, pc.capabilities)
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            provider = cls(pc, keys, http)
            results = await _run_tests(provider, specs)
    except Exception as e:
        results = [{"capability": spec.capability, "success": False, "count": 0,
                    "took_ms": 0.0, "error": f"{type(e).__name__}: {e}"}
                   for spec in specs]
    _record_test(engine, provider_id, results)


@router.post("/providers/{provider_id}/test")
async def test_provider(provider_id: str, request: Request):
    svc = request.app.state.engine.config
    svc.maybe_reload()
    pc = svc.get().provider(provider_id)
    cls = PROVIDER_CLASSES.get(pc.type) if pc is not None else None
    if pc is None or cls is None:
        raise HTTPException(status_code=404,
                            detail=f"provider {provider_id} not found or unsupported")
    keys = svc.provider_keys(provider_id)
    specs = _test_specs(cls.schema, pc.capabilities)
    async with httpx.AsyncClient(timeout=10) as http:
        provider = cls(pc, keys, http)
        results = await _run_tests(provider, specs)
    return _record_test(request.app.state.engine, provider_id, results)


@router.post("/providers/test")
async def test_provider_draft(body: ProviderConfig, request: Request):
    """用表单中未保存的配置测试（新建模式）。供应商需为已知类型。"""
    svc = request.app.state.engine.config
    svc.maybe_reload()
    cls = PROVIDER_CLASSES.get(body.type)
    if cls is None:
        raise HTTPException(status_code=404,
                            detail=f"provider {body.type} not found or unsupported")
    schema = cls.schema
    errors = validate_provider_config(body.id, body.capabilities, body.base_url, schema)
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    keys = svc.provider_keys(body.id)
    specs = _test_specs(schema, body.capabilities)
    async with httpx.AsyncClient(timeout=10) as http:
        provider = cls(body, keys, http)
        results = await _run_tests(provider, specs)
    return _record_test(request.app.state.engine, body.id, results)


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
