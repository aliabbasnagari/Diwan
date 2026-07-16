from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from .database import get_db
from .schemas import SettingsUpdateRequest
from . import settings_service, navidrome
from .config import BASE_DIR

router = APIRouter(prefix="/api/settings", tags=["settings"])

COOKIES_DIR = BASE_DIR / "cookies"
COOKIES_DIR.mkdir(parents=True, exist_ok=True)

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


@router.post("/cookies")
def upload_cookies(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload a cookies.txt file for yt-dlp to use."""
    if not file.filename:
        raise HTTPException(400, "No file provided")
    dest = COOKIES_DIR / "cookies.txt"
    content = file.file.read()
    # Basic validation: should be a text file, not empty
    if len(content) == 0:
        raise HTTPException(400, "Uploaded file is empty")
    dest.write_bytes(content)
    row = settings_service.get_settings(db)
    row.cookies_file_path = str(dest)
    row.cookies_enabled = True
    db.commit()
    db.refresh(row)
    return row.to_dict()
    

@router.delete("/cookies")
def delete_cookies(db: Session = Depends(get_db)):
    """Remove the uploaded cookies.txt file."""
    row = settings_service.get_settings(db)
    if row.cookies_file_path:
        p = Path(row.cookies_file_path)
        if p.exists():
            p.unlink()
    row.cookies_file_path = None
    row.cookies_enabled = False
    db.commit()
    db.refresh(row)
    return row.to_dict()


@router.post("/cookies/text")
def save_cookies_text(body: dict, db: Session = Depends(get_db)):
    """Save pasted cookies text as cookies.txt for yt-dlp."""
    text = body.get("text", "").strip()
    if not text:
        raise HTTPException(400, "Cookies text is empty")
    dest = COOKIES_DIR / "cookies.txt"
    dest.write_text(text, encoding="utf-8")
    row = settings_service.get_settings(db)
    row.cookies_file_path = str(dest)
    row.cookies_enabled = True
    db.commit()
    db.refresh(row)
    return row.to_dict()
