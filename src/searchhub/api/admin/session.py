from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

COOKIE_NAME = "sh_session"


class SessionStore:
    def __init__(self, secret: bytes):
        self._secret = secret

    def create(self, username: str, ttl_hours: int) -> str:
        payload = {"u": username, "exp": time.time() + ttl_hours * 3600}
        b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        sig = hmac.new(self._secret, b64.encode(), hashlib.sha256).hexdigest()
        return f"{b64}.{sig}"

    def verify(self, token: str) -> str | None:
        try:
            b64, sig = token.rsplit(".", 1)
            if not hmac.compare_digest(
                hmac.new(self._secret, b64.encode(), hashlib.sha256).hexdigest(), sig
            ):
                return None
            raw = json.loads(base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4)))
            if raw.get("exp", 0) < time.time():
                return None
            return raw.get("u") or None
        except Exception:
            return None


router = APIRouter(prefix="/api/admin", tags=["admin"])


class LoginBody(BaseModel):
    username: str
    password: str


class ChangePasswordBody(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8, max_length=128)


async def require_admin(request: Request,
                        sh_session: str | None = Cookie(default=None)) -> None:
    store: SessionStore = request.app.state.session_store
    if not sh_session or store.verify(sh_session) is None:
        raise HTTPException(status_code=401, detail="unauthorized")


@router.post("/login")
async def login(body: LoginBody, request: Request, response: Response):
    cfg = request.app.state.engine.config
    app_cfg = cfg.get()
    if body.username != app_cfg.admin.username or not cfg.verify_admin_password(body.password):
        raise HTTPException(status_code=401, detail="invalid credentials")
    token = request.app.state.session_store.create(
        app_cfg.admin.username, app_cfg.admin.session_ttl_hours)
    response.set_cookie(COOKIE_NAME, token, httponly=True, samesite="lax",
                        max_age=app_cfg.admin.session_ttl_hours * 3600)
    return {"success": True, "data": {"username": app_cfg.admin.username}}


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"success": True}


@router.post("/change-password", dependencies=[Depends(require_admin)])
async def change_password(body: ChangePasswordBody, request: Request):
    cfg = request.app.state.engine.config
    if not cfg.verify_admin_password(body.old_password):
        raise HTTPException(status_code=400, detail="old password is incorrect")
    cfg.set_admin_password(body.new_password)
    return {"success": True}
