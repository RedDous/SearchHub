from __future__ import annotations

import hashlib
import hmac

from fastapi import HTTPException, Request

from searchhub.config import AppConfig, TokenEntry


def _authorized(config: AppConfig, token: str) -> TokenEntry | None:
    digest = hashlib.sha256(token.encode()).hexdigest()
    return next((t for t in config.auth.tokens
                 if hmac.compare_digest(digest, t.token_hash) and not t.revoked), None)


async def require_token(request: Request) -> None:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="invalid token")
    token = header[len("Bearer "):].strip()
    request.app.state.engine.config.maybe_reload()
    entry = _authorized(request.app.state.engine.config.get(), token)
    if entry is None:
        raise HTTPException(status_code=401, detail="invalid token")
    request.state.token_name = entry.name
