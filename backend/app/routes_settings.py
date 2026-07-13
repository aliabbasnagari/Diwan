from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .database import get_db
from .schemas import SettingsUpdateRequest
from . import settings_service, navidrome

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings(db: Session = Depends(get_db)):
    return settings_service.get_settings(db).to_dict()


@router.put("")
def update_settings(req: SettingsUpdateRequest, db: Session = Depends(get_db)):
    patch = req.model_dump(exclude_unset=True)
    row = settings_service.update_settings(db, patch)
    return row.to_dict()


@router.post("/navidrome/test")
async def test_navidrome(db: Session = Depends(get_db)):
    s = settings_service.get_settings(db)
    if not s.navidrome_url:
        raise HTTPException(status_code=400, detail="Navidrome URL is not configured")
    try:
        result = await navidrome.ping(s.navidrome_url, s.navidrome_username or "", s.navidrome_password or "")
    except navidrome.NavidromeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result
