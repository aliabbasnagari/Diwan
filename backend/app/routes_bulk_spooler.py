from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from .database import get_db
from .models import BulkSpoolerItem, BulkItemStatus, Download, MediaType
from .schemas import BulkBatchCreateRequest, BulkReorderRequest
from . import bulk_spooler, tag_suggestions

router = APIRouter(prefix="/api/bulk-spooler", tags=["bulk-spooler"])


@router.post("/items")
def create_items(req: BulkBatchCreateRequest, db: Session = Depends(get_db)):
    # de-dupe within the pasted batch itself, preserving first-seen order
    seen_norm = set()
    urls = []
    for raw in req.urls:
        u = (raw or "").strip()
        if not u:
            continue
        norm = bulk_spooler.normalize_url(u)
        if norm in seen_norm:
            continue
        seen_norm.add(norm)
        urls.append(u)

    if not urls:
        raise HTTPException(status_code=400, detail="No URLs provided")

    max_pos = db.query(func.coalesce(func.max(BulkSpoolerItem.position), -1)).scalar()
    created, skipped = 0, 0

    for i, u in enumerate(urls):
        dup = bulk_spooler.find_duplicate(db, bulk_spooler.normalize_url(u))
        row = BulkSpoolerItem(
            position=max_pos + 1 + i,
            url=u,
            media_type=MediaType.AUDIO if req.media_type == "audio" else MediaType.VIDEO,
            quality=req.quality,
            audio_format=req.audio_format,
            subtitles=req.subtitles,
            add_to_library=req.add_to_library and req.media_type == "audio",
            tag_artist=req.tag_artist,
            tag_album=req.tag_album,
            tag_album_artist=req.tag_album_artist,
            tag_genre=req.tag_genre,
            tag_year=req.tag_year,
            status=BulkItemStatus.SKIPPED_DUPLICATE if dup else BulkItemStatus.PENDING,
            error_message=f"Skipped — duplicate of {dup}" if dup else None,
            started_at=datetime.utcnow() if dup else None,
            completed_at=datetime.utcnow() if dup else None,
        )
        db.add(row)
        if dup:
            skipped += 1
        else:
            created += 1

    tag_suggestions.record_tags(
        db,
        artist=req.tag_artist,
        album_artist=req.tag_album_artist,
        album=req.tag_album,
        genre=req.tag_genre,
        year=req.tag_year,
    )
    db.commit()
    bulk_spooler.start_worker()
    return {"created": created, "skipped_duplicates": skipped}


@router.get("/items")
def list_items(db: Session = Depends(get_db)):
    items = db.query(BulkSpoolerItem).order_by(BulkSpoolerItem.position).all()
    download_ids = [i.download_id for i in items if i.download_id]
    downloads_by_id = {}
    if download_ids:
        for dl in db.query(Download).filter(Download.id.in_(download_ids)).all():
            downloads_by_id[dl.id] = dl

    results = []
    for item in items:
        d = item.to_dict()
        dl = downloads_by_id.get(item.download_id)
        if dl:
            d["download"] = {
                "title": dl.title,
                "thumbnail": dl.thumbnail,
                "uploader": dl.uploader,
                "duration": dl.duration,
                "progress_percent": round(dl.progress_percent or 0, 1),
                "speed": dl.speed,
                "eta": dl.eta,
                "status": dl.status.value if dl.status else None,
                "library_path": dl.library_path,
            }
        results.append(d)
    return results


@router.get("/status")
def status():
    return bulk_spooler.get_status()


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    def count(status_val):
        return db.query(func.count(BulkSpoolerItem.id)).filter(BulkSpoolerItem.status == status_val).scalar()

    return {
        "total": db.query(func.count(BulkSpoolerItem.id)).scalar(),
        "pending": count(BulkItemStatus.PENDING),
        "downloading": count(BulkItemStatus.DOWNLOADING),
        "completed": count(BulkItemStatus.COMPLETED),
        "failed": count(BulkItemStatus.FAILED),
        "skipped_duplicates": count(BulkItemStatus.SKIPPED_DUPLICATE),
        "cancelled": count(BulkItemStatus.CANCELLED),
    }


@router.patch("/reorder")
def reorder(req: BulkReorderRequest, db: Session = Depends(get_db)):
    pending_ids = {
        row.id for row in db.query(BulkSpoolerItem.id).filter(BulkSpoolerItem.status == BulkItemStatus.PENDING).all()
    }
    position = 0
    for item_id in req.order:
        if item_id not in pending_ids:
            continue
        row = db.get(BulkSpoolerItem, item_id)
        row.position = position
        position += 1
    db.commit()
    return {"ok": True}


@router.post("/items/{item_id}/cancel")
def cancel(item_id: int, db: Session = Depends(get_db)):
    row = db.get(BulkSpoolerItem, item_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    bulk_spooler.cancel_item(item_id)
    db.refresh(row)
    return row.to_dict()


@router.post("/items/{item_id}/retry")
def retry(item_id: int, db: Session = Depends(get_db)):
    row = db.get(BulkSpoolerItem, item_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    max_pos = db.query(func.coalesce(func.max(BulkSpoolerItem.position), -1)).scalar()
    row.status = BulkItemStatus.PENDING
    row.error_message = None
    row.download_id = None
    row.started_at = None
    row.completed_at = None
    row.position = max_pos + 1
    db.commit()
    bulk_spooler.start_worker()
    return row.to_dict()


@router.delete("/items/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db)):
    row = db.get(BulkSpoolerItem, item_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    if row.status == BulkItemStatus.DOWNLOADING:
        bulk_spooler.cancel_item(item_id)
        db.refresh(row)
    db.delete(row)
    db.commit()
    return {"deleted": True}
