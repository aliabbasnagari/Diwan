from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import get_db
from .config import NAVIDROME_URL
from . import settings_service, navidrome_auth
from .auth import create_token, require_admin

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


@router.get("/config")
def auth_config():
    """Unauthenticated — lets the login page know whether the server is
    even set up, and where, before the person types anything."""
    return {"configured": bool(NAVIDROME_URL), "navidrome_url": NAVIDROME_URL or None}


@router.post("/login")
async def login(req: LoginRequest, db: Session = Depends(get_db)):
    s = settings_service.get_settings(db)
    base_url = NAVIDROME_URL or s.navidrome_url
    if not base_url:
        raise HTTPException(
            status_code=500,
            detail="NAVIDROME_URL is not configured on the server. Set it in the backend's environment and restart.",
        )

    try:
        result = await navidrome_auth.login(base_url, req.username, req.password)
    except navidrome_auth.NavidromeAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    if not result.get("isAdmin"):
        raise HTTPException(status_code=403, detail="Only admin accounts can access Diwan.")

    # Keep the Subsonic-integration credentials (used for scan triggers)
    # in sync with whoever just logged in — one login configures both.
    s.navidrome_url = base_url
    s.navidrome_username = req.username
    s.navidrome_password = req.password
    db.commit()

    token = create_token(req.username, s.session_secret)
    return {
        "token": token,
        "username": result.get("username", req.username),
        "name": result.get("name"),
        "navidrome_url": base_url,
    }


@router.get("/me")
async def me(username: str = Depends(require_admin)):
    return {"username": username}


@router.post("/logout")
async def logout():
    # Tokens are stateless (signed, not stored), so logout is just the
    # client discarding it. This endpoint exists for symmetry / future use.
    return {"ok": True}
