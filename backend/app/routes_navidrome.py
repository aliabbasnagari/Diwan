from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .database import get_db
from . import settings_service, navidrome

router = APIRouter(prefix="/api/navidrome", tags=["navidrome"])


def _creds(db: Session):
    s = settings_service.get_settings(db)
    if not s.navidrome_url:
        raise HTTPException(status_code=400, detail="Navidrome URL is not configured. Set it in Settings first.")
    return s.navidrome_url, s.navidrome_username or "", s.navidrome_password or ""


@router.post("/scan")
async def trigger_scan(db: Session = Depends(get_db)):
    url, user, pw = _creds(db)
    try:
        return await navidrome.start_scan(url, user, pw)
    except navidrome.NavidromeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/scan/status")
async def get_scan_status(db: Session = Depends(get_db)):
    url, user, pw = _creds(db)
    try:
        return await navidrome.scan_status(url, user, pw)
    except navidrome.NavidromeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/ping")
async def ping(db: Session = Depends(get_db)):
    url, user, pw = _creds(db)
    try:
        return await navidrome.ping(url, user, pw)
    except navidrome.NavidromeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
