from fastapi import APIRouter, Depends, Request

from searchhub.api.auth import require_token

router = APIRouter(prefix="/v1/providers", tags=["providers"], dependencies=[Depends(require_token)])


@router.get("")
async def list_providers(request: Request):
    return request.app.state.engine.provider_status()
