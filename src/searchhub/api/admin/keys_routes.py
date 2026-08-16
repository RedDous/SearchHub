from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from searchhub.api.admin.session import require_admin

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


@router.get("/providers/{provider_id}/keys")
async def list_keys(provider_id: str, request: Request):
    svc = request.app.state.engine.config
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
async def add_key(provider_id: str, body: KeyBody, request: Request):
    svc = request.app.state.engine.config
    try:
        svc.add_provider_key(provider_id, body.key)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"success": True}


@router.delete("/providers/{provider_id}/keys/{index}")
async def remove_key(provider_id: str, index: int, request: Request):
    svc = request.app.state.engine.config
    try:
        svc.remove_provider_key(provider_id, index)
    except IndexError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"success": True}
