import base64
import hashlib
import hmac
import json
import time
from typing import Optional

from fastapi import Depends, HTTPException, Header, Query
from sqlalchemy.orm import Session

from .database import get_db
from . import settings_service

TOKEN_TTL_SECONDS = 60 * 60 * 24 * 30  # 30 days


def _sign(payload_b64: str, secret: str) -> str:
    return hmac.new(secret.encode(), payload_b64.encode(), hashlib.sha256).hexdigest()


def create_token(username: str, secret: str) -> str:
    payload = {"username": username, "exp": time.time() + TOKEN_TTL_SECONDS}
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{payload_b64}.{_sign(payload_b64, secret)}"


def verify_token(token: str, secret: str) -> dict:
    try:
        payload_b64, sig = token.split(".", 1)
    except ValueError:
        raise ValueError("Malformed token")
    if not hmac.compare_digest(sig, _sign(payload_b64, secret)):
        raise ValueError("Invalid signature")
    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded))
    if payload.get("exp", 0) < time.time():
        raise ValueError("Token expired")
    return payload


async def require_admin(
    authorization: Optional[str] = Header(default=None),
    token: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
) -> str:
    """Every protected route depends on this. Accepts the token as a
    Bearer header (used by the axios client) or a ?token= query param
    (used by plain <img>/<a> URLs, which can't set custom headers)."""
    raw = None
    if authorization and authorization.startswith("Bearer "):
        raw = authorization[len("Bearer "):]
    elif token:
        raw = token

    if not raw:
        raise HTTPException(status_code=401, detail="Not authenticated")

    secret = settings_service.get_settings(db).session_secret
    try:
        payload = verify_token(raw, secret)
    except ValueError:
        raise HTTPException(status_code=401, detail="Session expired — please log in again")
    return payload["username"]
