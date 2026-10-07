from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import os

from .config import CORS_ORIGINS
from .database import init_db, SessionLocal
from .models import Download, DownloadStatus, ConversionJob, ConversionStatus
from . import downloader, converter, settings_service, audio_editor
from .auth import require_admin
from .routes_auth import router as auth_router
from .routes_downloads import router as downloads_router
from .routes_library import router as library_router
from .routes_settings import router as settings_router
from .routes_navidrome import router as navidrome_router
from .routes_suggestions import router as suggestions_router
from .routes_convert import router as convert_router
from .routes_editor import router as editor_router

app = FastAPI(title="Diwan — Music Library Manager API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# /api/health and /api/auth/* are the only unprotected routes — everything
# else requires a valid admin session (see app/auth.py).
app.include_router(auth_router)
app.include_router(downloads_router)
app.include_router(library_router, dependencies=[Depends(require_admin)])
app.include_router(settings_router, dependencies=[Depends(require_admin)])
app.include_router(navidrome_router, dependencies=[Depends(require_admin)])
app.include_router(suggestions_router, dependencies=[Depends(require_admin)])
app.include_router(convert_router, dependencies=[Depends(require_admin)])
app.include_router(editor_router, dependencies=[Depends(require_admin)])

ACTIVE_DOWNLOAD_STATUSES = [
    DownloadStatus.DOWNLOADING, DownloadStatus.QUEUED,
    DownloadStatus.FETCHING_INFO, DownloadStatus.PROCESSING, DownloadStatus.TAGGING,
]

@app.on_event("startup")
def on_startup():
    init_db()
    db = SessionLocal()
    try:
        settings_service.get_settings(db)  # ensures the settings row + dirs exist
    finally:
        db.close()

    audio_editor.cleanup_all()  # drop editor working files left by a previous run
    downloader.start_workers()
    converter.start_workers()

    # Resume anything left mid-flight from a previous run
    db = SessionLocal()
    try:
        stuck = db.query(Download).filter(Download.status.in_(ACTIVE_DOWNLOAD_STATUSES)).all()
        for row in stuck:
            row.status = DownloadStatus.QUEUED
            row.progress_percent = 0
        db.commit()
        requeue = db.query(Download).filter(Download.status == DownloadStatus.QUEUED).all()
        for row in requeue:
            downloader.enqueue_download(row.id)
    finally:
        db.close()

    db = SessionLocal()
    try:
        stuck_conversions = db.query(ConversionJob).filter(
            ConversionJob.status == ConversionStatus.CONVERTING
        ).all()
        for row in stuck_conversions:
            row.status = ConversionStatus.QUEUED
            row.progress_percent = 0
        db.commit()
        requeue_conversions = db.query(ConversionJob).filter(ConversionJob.status == ConversionStatus.QUEUED).all()
        for row in requeue_conversions:
            converter.enqueue(row.id)
    finally:
        db.close()


@app.get("/api/health")
def health():
    return {"ok": True}


# Built frontend assets (copied in at `app/static` during the Docker build —
# see Dockerfile). Absent in local dev, where the frontend runs separately
# via `npm run dev` and proxies /api to this backend (see vite.config.js).
FRONTEND_DIST = Path(__file__).resolve().parent / "static"

if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")

    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = FRONTEND_DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST / "index.html")
