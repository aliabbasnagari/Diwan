import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from .database import get_db
from .models import ConversionJob, ConversionStatus, Download
from . import settings_service, converter
from .config import (
    DEFAULT_CONVERT_DIR, AUDIO_CONVERT_FORMATS, VIDEO_CONVERT_FORMATS,
    AUDIO_BITRATES, VIDEO_RESOLUTIONS,
)
from .library import scanner

router = APIRouter(prefix="/api/convert", tags=["convert"])

UPLOAD_DIR = DEFAULT_CONVERT_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ACTIVE_STATUSES = [ConversionStatus.QUEUED, ConversionStatus.CONVERTING]


@router.get("/formats")
def get_formats():
    return {
        "audio": {k: {"lossless": v.get("lossless", False)} for k, v in AUDIO_CONVERT_FORMATS.items()},
        "audio_bitrates": AUDIO_BITRATES,
        "video": list(VIDEO_CONVERT_FORMATS.keys()),
        "video_resolutions": VIDEO_RESOLUTIONS,
    }


def _resolve_source(db: Session, source_kind: str, source_ref: Optional[str], file: Optional[UploadFile], file_bytes: Optional[bytes]) -> tuple[Path, str]:
    if source_kind == "upload":
        if not file or not file_bytes:
            raise HTTPException(status_code=400, detail="No file uploaded")
        dest = UPLOAD_DIR / f"{uuid.uuid4().hex}_{file.filename}"
        dest.write_bytes(file_bytes)
        return dest, file.filename

    if source_kind == "library":
        if not source_ref:
            raise HTTPException(status_code=400, detail="source_ref (track id) is required")
        lib_dir = settings_service.library_dir(db)
        try:
            path = scanner.resolve_track_path(lib_dir, source_ref)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid track id")
        if not path.exists():
            raise HTTPException(status_code=404, detail="Library track not found")
        return path, path.name

    if source_kind == "download":
        if not source_ref:
            raise HTTPException(status_code=400, detail="source_ref (download id) is required")
        row = db.get(Download, int(source_ref))
        if not row or not row.filepath:
            raise HTTPException(status_code=404, detail="Download not found")
        path = Path(row.filepath)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Downloaded file missing on disk")
        return path, path.name

    raise HTTPException(status_code=400, detail="source_kind must be upload, library, or download")


@router.post("/jobs")
async def create_job(
    source_kind: str = Form(...),
    source_ref: Optional[str] = Form(None),
    target_format: str = Form(...),
    target_bitrate: Optional[str] = Form(None),
    target_resolution: Optional[str] = Form(None),
    save_to_library: bool = Form(False),
    file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    fmt = target_format.lower()
    is_audio = fmt in AUDIO_CONVERT_FORMATS
    is_video = fmt in VIDEO_CONVERT_FORMATS
    if not is_audio and not is_video:
        raise HTTPException(status_code=400, detail=f"Unsupported target format: {target_format}")

    file_bytes = await file.read() if file else None
    source_path, source_filename = _resolve_source(db, source_kind, source_ref, file, file_bytes)

    if is_audio and not target_bitrate and not AUDIO_CONVERT_FORMATS[fmt].get("lossless"):
        target_bitrate = AUDIO_CONVERT_FORMATS[fmt]["default_bitrate"]
    if is_video and not target_resolution:
        target_resolution = "source"

    row = ConversionJob(
        source_kind=source_kind,
        source_ref=source_ref,
        source_path=str(source_path),
        source_filename=source_filename,
        target_format=fmt,
        target_bitrate=target_bitrate if is_audio else None,
        target_resolution=target_resolution if is_video else None,
        save_to_library=bool(save_to_library) and is_audio,
        status=ConversionStatus.QUEUED,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    converter.enqueue(row.id)
    return row.to_dict()


@router.get("/jobs")
def list_jobs(db: Session = Depends(get_db)):
    rows = db.query(ConversionJob).order_by(ConversionJob.created_at.desc()).limit(200).all()
    return [r.to_dict() for r in rows]


@router.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db)):
    row = db.get(ConversionJob, job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return row.to_dict()


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int, db: Session = Depends(get_db)):
    row = db.get(ConversionJob, job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    converter.cancel(job_id)
    row.status = ConversionStatus.CANCELLED
    db.commit()
    return row.to_dict()


@router.delete("/jobs/{job_id}")
def delete_job(job_id: int, db: Session = Depends(get_db)):
    row = db.get(ConversionJob, job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    if row.output_path:
        Path(row.output_path).unlink(missing_ok=True)
    if row.source_kind == "upload" and row.source_path:
        Path(row.source_path).unlink(missing_ok=True)
    db.delete(row)
    db.commit()
    return {"deleted": True}


@router.get("/jobs/{job_id}/file")
def get_job_file(job_id: int, db: Session = Depends(get_db)):
    row = db.get(ConversionJob, job_id)
    if not row or not row.output_path:
        raise HTTPException(status_code=404, detail="File not found")
    path = Path(row.output_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(path, filename=path.name)


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    total = db.query(func.count(ConversionJob.id)).scalar()
    completed = db.query(func.count(ConversionJob.id)).filter(ConversionJob.status == ConversionStatus.COMPLETED).scalar()
    failed = db.query(func.count(ConversionJob.id)).filter(ConversionJob.status == ConversionStatus.FAILED).scalar()
    active = db.query(func.count(ConversionJob.id)).filter(ConversionJob.status.in_(ACTIVE_STATUSES)).scalar()
    return {"total": total, "completed": completed, "failed": failed, "active": active}
