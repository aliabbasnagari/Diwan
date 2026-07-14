from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware

from .config import CORS_ORIGINS
from .database import init_db, SessionLocal
from .models import Download, DownloadStatus, ConversionJob, ConversionStatus
from . import downloader, converter, settings_service
from .auth import require_admin
from .routes_auth import router as auth_router
from .routes_downloads import router as downloads_router
from .routes_library import router as library_router
from .routes_settings import router as settings_router
from .routes_navidrome import router as navidrome_router
from .routes_convert import router as convert_router

app = FastAPI(title="Crate — Navidrome Library Manager API")

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
app.include_router(convert_router, dependencies=[Depends(require_admin)])

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
