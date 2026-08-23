from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel

from searchhub.api.admin.session import require_admin
from searchhub.providers import PROVIDER_CLASSES
from searchhub.api.admin import config_routes

router = APIRouter(prefix="/api/admin", tags=["admin"],
                   dependencies=[Depends(require_admin)])


class KeyBody(BaseModel):
    key: str


def _mask(key: str) -> str:
    if len(key) >= 9:
        return key[:5] + "****" + key[-4:]
    if len(key) >= 4:
        return key[:2] + "****" + key[-2:]
    return "****"


def _validate_key_for_provider(provider_id: str, key: str) -> str | None:
    """返回错误信息（None = 通过）。校验目标供应商自身前缀与跨供应商误贴。"""
    for pid, cls in PROVIDER_CLASSES.items():
        prefix = getattr(getattr(cls, "schema", None), "key_prefix", None)
        if not prefix or not key.startswith(prefix):
            continue
        if pid != provider_id:
            return f"该 Key 以 {prefix!r} 开头，疑似 {pid} 的 Key，请确认是否添加错供应商"
        return None
    cls = PROVIDER_CLASSES.get(provider_id)
    if cls is not None and getattr(cls.schema, "key_prefix", None):
        return f"该 Key 格式与 {provider_id} 不符（应以 {cls.schema.key_prefix!r} 开头）"
    return None


@router.get("/providers/{provider_id}/keys")
async def list_keys(provider_id: str, request: Request):
    svc = request.app.state.engine.config
    svc.maybe_reload()
    keys = svc.provider_keys(provider_id)
    pool_status = []
    for entry in request.app.state.engine.provider_status():
        if entry["id"] == provider_id:
            pool_status = entry.get("keys", [])
    result = []
    for i, k in enumerate(keys):
        status = pool_status[i] if i < len(pool_status) else None
        result.append({"index": i, "masked": _mask(k), "status": status})
    return {"success": True, "data": {"keys": result}}


@router.post("/providers/{provider_id}/keys")
async def add_key(provider_id: str, body: KeyBody, request: Request, background: BackgroundTasks):
    svc = request.app.state.engine.config
    key = body.key.strip()
    error = _validate_key_for_provider(provider_id, key)
    if error:
        raise HTTPException(status_code=400, detail=error)
    try:
        svc.add_provider_key(provider_id, key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    background.add_task(config_routes._auto_retest, request.app.state.engine, provider_id)
    return {"success": True}


@router.delete("/providers/{provider_id}/keys/{index}")
async def remove_key(provider_id: str, index: int, request: Request, background: BackgroundTasks):
    svc = request.app.state.engine.config
    try:
        svc.remove_provider_key(provider_id, index)
    except IndexError as e:
        raise HTTPException(status_code=404, detail=str(e))
    background.add_task(config_routes._auto_retest, request.app.state.engine, provider_id)
    return {"success": True}
