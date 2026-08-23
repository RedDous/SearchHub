from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, Request

from searchhub.api.admin.session import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"],
                   dependencies=[Depends(require_admin)])


@router.get("/history")
async def list_history(request: Request, capability: str | None = None,
                       provider: str | None = None, token: str | None = None,
                       from_ts: float | None = None, to_ts: float | None = None,
                       q: str | None = None, limit: int = 100, offset: int = 0):
    rows = await request.app.state.engine.history.query(
        capability=capability, provider=provider, token=token,
        from_ts=from_ts, to_ts=to_ts, q=q,
        limit=max(min(limit, 500), 0), offset=max(offset, 0))
    return {"success": True, "data": {"rows": rows}}


@router.get("/history/{row_id}/full")
async def history_full(row_id: int, request: Request):
    full = await request.app.state.engine.history.get_full(row_id)
    if full is None:
        raise HTTPException(status_code=404, detail=f"history row {row_id} not found")
    return {"success": True, "data": {"response_full": full}}


@router.get("/stats/summary")
async def stats_summary(request: Request, hours: float = 24):
    since = time.time() - hours * 3600
    data = await request.app.state.engine.history.summary(since)
    data["providers"] = request.app.state.engine.provider_status()
    return {"success": True, "data": data}


@router.get("/stats/timeseries")
async def stats_timeseries(request: Request, hours: int = 24):
    since = time.time() - hours * 3600
    rows = await request.app.state.engine.history.timeseries(since, 3600)
    return {"success": True, "data": {"rows": rows}}
