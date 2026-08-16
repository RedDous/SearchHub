from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from searchhub.api.auth import require_token

router = APIRouter(prefix="/v1/search", tags=["search"], dependencies=[Depends(require_token)])


class SearchBody(BaseModel):
    q: str = ""
    limit: int = Field(default=5, ge=1, le=50)
    providers: str | None = None
    strategy: str | None = None
    cache: bool = True
    timeout: float | None = None


@router.get("")
async def search_get(request: Request, q: str = "", limit: int = 5, providers: str | None = None,
                     strategy: str | None = None, cache: bool = True,
                     timeout: float | None = None):
    if not q:
        raise HTTPException(status_code=400, detail="q is required")
    return await request.app.state.engine.search(
        q, limit=limit, providers=providers, strategy=strategy, cache=cache, timeout=timeout)


@router.post("")
async def search_post(request: Request, body: SearchBody):
    if not body.q:
        raise HTTPException(status_code=400, detail="q is required")
    return await request.app.state.engine.search(
        body.q, limit=body.limit, providers=body.providers, strategy=body.strategy,
        cache=body.cache, timeout=body.timeout)
