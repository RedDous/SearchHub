from __future__ import annotations

import hashlib
import hmac

from fastapi import HTTPException, Request

from searchhub.config import AppConfig


def _authorized(config: AppConfig, token: str) -> bool:
    digest = hashlib.sha256(token.encode()).hexdigest()
    return any(hmac.compare_digest(digest, t.token_hash) for t in config.auth.tokens)


async def require_token(request: Request) -> None:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="invalid token")
    token = header[len("Bearer "):].strip()
    if not _authorized(request.app.state.engine.config.get(), token):
        raise HTTPException(status_code=401, detail="invalid token")
