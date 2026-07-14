import secrets
from pathlib import Path

from sqlalchemy.orm import Session

from .config import (
    DEFAULT_DOWNLOAD_DIR, DEFAULT_LIBRARY_DIR, DEFAULT_ARTIST_IMAGE_DIR,
    DEFAULT_MAX_CONCURRENT_DOWNLOADS, NAVIDROME_URL,
)
from .models import AppSettings

SETTINGS_ID = 1


def get_settings(db: Session) -> AppSettings:
    row = db.get(AppSettings, SETTINGS_ID)
    if row is None:
        row = AppSettings(
            id=SETTINGS_ID,
            download_dir=str(DEFAULT_DOWNLOAD_DIR),
            library_dir=str(DEFAULT_LIBRARY_DIR),
            artist_image_dir=str(DEFAULT_ARTIST_IMAGE_DIR),
            max_concurrent_downloads=DEFAULT_MAX_CONCURRENT_DOWNLOADS,
            navidrome_auto_scan=False,
            navidrome_url=NAVIDROME_URL or None,
            session_secret=secrets.token_hex(32),
        )
        db.add(row)
        db.commit()
        db.refresh(row)

    dirty = False
    if not row.artist_image_dir:
        # backfill for rows created before this setting existed
        row.artist_image_dir = str(Path(row.library_dir) / ".artist-images")
        dirty = True
    if not row.session_secret:
        row.session_secret = secrets.token_hex(32)
        dirty = True
    if NAVIDROME_URL and row.navidrome_url != NAVIDROME_URL:
        # NAVIDROME_URL is env-controlled and always wins over whatever's stored
        row.navidrome_url = NAVIDROME_URL
        dirty = True
    if dirty:
        db.commit()
        db.refresh(row)
    return row


def update_settings(db: Session, patch: dict) -> AppSettings:
    row = get_settings(db)
    for key, value in patch.items():
        if value is None:
            continue
        if key == "navidrome_url" and NAVIDROME_URL:
            continue  # env-locked, ignore attempts to change it via the API
        if hasattr(row, key):
            setattr(row, key, value)
    db.commit()
    db.refresh(row)

    Path(row.download_dir).mkdir(parents=True, exist_ok=True)
    Path(row.library_dir).mkdir(parents=True, exist_ok=True)
    Path(row.artist_image_dir).mkdir(parents=True, exist_ok=True)
    return row


def library_dir(db: Session) -> Path:
    return Path(get_settings(db).library_dir)


def download_dir(db: Session) -> Path:
    return Path(get_settings(db).download_dir)


def artist_image_dir(db: Session) -> Path:
    return Path(get_settings(db).artist_image_dir)
