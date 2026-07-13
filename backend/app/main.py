from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from .config import CORS_ORIGINS
from .database import get_db, init_db, SessionLocal
from .models import Download, DownloadStatus, MediaType
from .schemas import PreviewRequest, DownloadCreateRequest
from . import downloader, settings_service
from .routes_library import router as library_router
from .routes_settings import router as settings_router
from .routes_navidrome import router as navidrome_router

app = FastAPI(title="Navidrome Library Manager API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(library_router)
app.include_router(settings_router)
app.include_router(navidrome_router)

ACTIVE_STATUSES = [
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

    # Resume anything left mid-flight from a previous run
    db = SessionLocal()
    try:
        stuck = db.query(Download).filter(Download.status.in_(ACTIVE_STATUSES)).all()
        for row in stuck:
            row.status = DownloadStatus.QUEUED
            row.progress_percent = 0
        db.commit()
        requeue = db.query(Download).filter(Download.status == DownloadStatus.QUEUED).all()
        for row in requeue:
            downloader.enqueue_download(row.id)
    finally:
        db.close()


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/preview")
def preview(req: PreviewRequest):
    try:
        info = downloader.extract_info(req.url)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not fetch info: {exc}")
    return info


@app.post("/api/downloads")
def create_download(req: DownloadCreateRequest, db: Session = Depends(get_db)):
    row = Download(
        url=req.url,
        media_type=MediaType.AUDIO if req.media_type == "audio" else MediaType.VIDEO,
        quality=req.quality,
        audio_format=req.audio_format,
        subtitles=req.subtitles,
        add_to_library=req.add_to_library and req.media_type == "audio",
        tag_artist=req.tag_artist,
        tag_album=req.tag_album,
        tag_title=req.tag_title,
        status=DownloadStatus.QUEUED,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    downloader.enqueue_download(row.id)
    return row.to_dict()


@app.get("/api/downloads")
def list_downloads(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0),
    db: Session = Depends(get_db),
):
    q = db.query(Download)
    if status:
        q = q.filter(Download.status == status)
    q = q.order_by(Download.created_at.desc()).offset(offset).limit(limit)
    return [row.to_dict() for row in q.all()]


@app.get("/api/downloads/{download_id}")
def get_download(download_id: int, db: Session = Depends(get_db)):
    row = db.get(Download, download_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row.to_dict()


@app.post("/api/downloads/{download_id}/cancel")
def cancel_download(download_id: int, db: Session = Depends(get_db)):
    row = db.get(Download, download_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    downloader.cancel_download(download_id)
    row.status = DownloadStatus.CANCELLED
    db.commit()
    return row.to_dict()


@app.post("/api/downloads/{download_id}/retry")
def retry_download(download_id: int, db: Session = Depends(get_db)):
    row = db.get(Download, download_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    row.status = DownloadStatus.QUEUED
    row.progress_percent = 0
    row.error_message = None
    db.commit()
    downloader.enqueue_download(row.id)
    return row.to_dict()


@app.delete("/api/downloads/{download_id}")
def delete_download(download_id: int, delete_file: bool = True, db: Session = Depends(get_db)):
    row = db.get(Download, download_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    if delete_file and row.filepath:
        try:
            Path(row.filepath).unlink(missing_ok=True)
        except OSError:
            pass
    db.delete(row)
    db.commit()
    return {"deleted": True}


@app.get("/api/downloads/{download_id}/file")
def get_file(download_id: int, db: Session = Depends(get_db)):
    row = db.get(Download, download_id)
    if row is None or not row.filepath:
        raise HTTPException(status_code=404, detail="File not found")
    path = Path(row.filepath)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(path, filename=path.name)


@app.get("/api/stats")
def stats(db: Session = Depends(get_db)):
    total = db.query(func.count(Download.id)).scalar()
    completed = db.query(func.count(Download.id)).filter(Download.status == DownloadStatus.COMPLETED).scalar()
    failed = db.query(func.count(Download.id)).filter(Download.status == DownloadStatus.FAILED).scalar()
    active = db.query(func.count(Download.id)).filter(Download.status.in_(ACTIVE_STATUSES)).scalar()
    total_bytes = db.query(func.coalesce(func.sum(Download.filesize), 0)).filter(
        Download.status == DownloadStatus.COMPLETED
    ).scalar()
    return {
        "total": total,
        "completed": completed,
        "failed": failed,
        "active": active,
        "total_bytes": int(total_bytes or 0),
    }
