from __future__ import annotations

import hashlib
import secrets as _secrets
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from searchhub.api.admin.session import require_admin
from searchhub.config import TokenEntry

router = APIRouter(prefix="/api/admin", tags=["admin"],
                   dependencies=[Depends(require_admin)])


class TokenCreateBody(BaseModel):
    name: str = Field(min_length=1, max_length=64)


@router.get("/tokens")
async def list_tokens(request: Request):
    tokens = request.app.state.engine.config.get().auth.tokens
    return {"success": True, "data": {"tokens": [
        {"id": t.id, "name": t.name, "created_at": t.created_at,
         "revoked": t.revoked, "hash_prefix": t.token_hash[:8]}
        for t in tokens]}}


@router.post("/tokens")
async def create_token(body: TokenCreateBody, request: Request):
    svc = request.app.state.engine.config
    raw = _secrets.token_urlsafe(32)
    entry = TokenEntry(name=body.name,
                       token_hash=hashlib.sha256(raw.encode()).hexdigest(),
                       id=_secrets.token_hex(8), created_at=time.time())
    cfg = svc.get()
    cfg.auth.tokens.append(entry)
    svc.save_config(cfg)
    return {"success": True, "data": {"id": entry.id, "name": entry.name, "token": raw}}


@router.delete("/tokens/{token_id}")
async def delete_token(token_id: str, request: Request):
    svc = request.app.state.engine.config
    cfg = svc.get()
    new = [t for t in cfg.auth.tokens if t.id != token_id]
    if len(new) == len(cfg.auth.tokens):
        raise HTTPException(status_code=404, detail="token not found")
    cfg.auth.tokens = new
    svc.save_config(cfg)
    return {"success": True}
