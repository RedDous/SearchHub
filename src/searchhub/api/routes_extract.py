from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from searchhub.api.auth import require_token

router = APIRouter(prefix="/v1/extract", tags=["extract"], dependencies=[Depends(require_token)])

VALID_FORMATS = {"text", "markdown"}


class ExtractBody(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=20)
    format: str = "markdown"
    include_raw: bool = True
    max_chars: int = Field(default=15000, ge=100, le=1000000)
    cache: bool = True
    strategy: str | None = None
    timeout: float | None = None


async def _run(request: Request, urls: list[str], fmt: str, include_raw: bool, max_chars: int,
               cache: bool, strategy: str | None, timeout: float | None):
    if fmt not in VALID_FORMATS:
        raise HTTPException(status_code=400, detail="format must be text or markdown")
    resp = await request.app.state.engine.extract(
        urls, fmt=fmt, max_chars=max_chars, strategy=strategy, cache=cache, timeout=timeout,
        token_name=request.state.token_name)
    if not include_raw:
        for item in resp.data:
            item.raw_content = ""
    return resp


@router.get("")
async def extract_get(request: Request, urls: str, format: str = "markdown",
                      include_raw: bool = True, max_chars: int = 15000,
                      cache: bool = True, strategy: str | None = None,
                      timeout: float | None = None):
    url_list = [u.strip() for u in urls.split(",") if u.strip()]
    if not url_list:
        raise HTTPException(status_code=400, detail="urls is required")
    return await _run(request, url_list, format, include_raw, max_chars, cache, strategy, timeout)


@router.post("")
async def extract_post(request: Request, body: ExtractBody):
    return await _run(request, body.urls, body.format, body.include_raw, body.max_chars,
                      body.cache, body.strategy, body.timeout)
