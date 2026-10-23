import re
import random
import threading
import time
from datetime import datetime, timedelta

from .database import SessionLocal
from .models import BulkSpoolerItem, BulkItemStatus, Download, DownloadStatus
from . import downloader, settings_service

# Downloads are deliberately trickled out one at a time with a random pause
# in between (configurable on the Settings page), rather than reusing
# downloader.py's concurrency — the whole point of the Bulk Spooler is to
# look like unhurried, spaced-out activity.
DEFAULT_DELAY_MIN_SECONDS = 180
DEFAULT_DELAY_MAX_SECONDS = 360
POLL_INTERVAL_SECONDS = 3
IDLE_POLL_SECONDS = 5

ACTIVE_DOWNLOAD_STATUSES = [
    DownloadStatus.DOWNLOADING, DownloadStatus.QUEUED,
    DownloadStatus.FETCHING_INFO, DownloadStatus.PROCESSING, DownloadStatus.TAGGING,
]
DUPLICATE_ITEM_STATUSES = [BulkItemStatus.PENDING, BulkItemStatus.DOWNLOADING, BulkItemStatus.COMPLETED]
TERMINAL_DOWNLOAD_STATUSES = {DownloadStatus.COMPLETED, DownloadStatus.FAILED, DownloadStatus.CANCELLED}

_lock = threading.Lock()
_worker_started = False
_state = {"current_item_id": None, "next_run_at": None}


def normalize_url(u: str) -> str:
    if not u:
        return ""
    s = u.strip().lower()
    s = re.sub(r"/+$", "", s)
    s = re.sub(r"^https?://(www\.)?", "", s)
    return s


def start_worker():
    """Idempotently spin up the background scheduler thread."""
    global _worker_started
    with _lock:
        if _worker_started:
            return
        _worker_started = True
        threading.Thread(target=_loop, daemon=True).start()


def get_status() -> dict:
    return dict(_state)


def _delay_bounds() -> tuple[float, float]:
    db = SessionLocal()
    try:
        s = settings_service.get_settings(db)
        lo = s.bulk_delay_min_seconds or DEFAULT_DELAY_MIN_SECONDS
        hi = s.bulk_delay_max_seconds or DEFAULT_DELAY_MAX_SECONDS
        if lo > hi:
            lo, hi = hi, lo
        return lo, hi
    finally:
        db.close()


def find_duplicate(db, norm_url: str, exclude_item_id: int | None = None) -> str | None:
    """Look for an existing (active or completed) Download, or another bulk
    item, whose URL normalizes the same way. Returns a short description of
    the match, or None."""
    for row in db.query(Download).filter(
        Download.status.in_(ACTIVE_DOWNLOAD_STATUSES + [DownloadStatus.COMPLETED])
    ).all():
        if norm_url == normalize_url(row.url) or (row.webpage_url and norm_url == normalize_url(row.webpage_url)):
            return f"download #{row.id}" + (f" ({row.title})" if row.title else "")

    q = db.query(BulkSpoolerItem).filter(BulkSpoolerItem.status.in_(DUPLICATE_ITEM_STATUSES))
    if exclude_item_id is not None:
        q = q.filter(BulkSpoolerItem.id != exclude_item_id)
    for row in q.all():
        if norm_url == normalize_url(row.url):
            return f"bulk item #{row.id}"

    return None


def cancel_item(item_id: int):
    db = SessionLocal()
    try:
        item = db.get(BulkSpoolerItem, item_id)
        if item is None:
            return
        if item.status == BulkItemStatus.PENDING:
            item.status = BulkItemStatus.CANCELLED
            item.completed_at = datetime.utcnow()
            db.commit()
        elif item.status == BulkItemStatus.DOWNLOADING:
            if item.download_id:
                downloader.cancel_download(item.download_id)
            item.status = BulkItemStatus.CANCELLED
            item.completed_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def _next_item_id() -> int | None:
    db = SessionLocal()
    try:
        # An item already DOWNLOADING (e.g. resumed after a restart) takes
        # priority over starting a new one, so bulk processing stays serial.
        item = (
            db.query(BulkSpoolerItem)
            .filter(BulkSpoolerItem.status == BulkItemStatus.DOWNLOADING)
            .order_by(BulkSpoolerItem.position)
            .first()
        )
        if item is None:
            item = (
                db.query(BulkSpoolerItem)
                .filter(BulkSpoolerItem.status == BulkItemStatus.PENDING)
                .order_by(BulkSpoolerItem.position)
                .first()
            )
        return item.id if item else None
    finally:
        db.close()


def _loop():
    while True:
        item_id = _next_item_id()
        if item_id is None:
            _state["current_item_id"] = None
            _state["next_run_at"] = None
            time.sleep(IDLE_POLL_SECONDS)
            continue

        did_download = _process_item(item_id)
        _state["current_item_id"] = None

        if did_download:
            lo, hi = _delay_bounds()
            delay = random.uniform(lo, hi)
            _state["next_run_at"] = (datetime.utcnow() + timedelta(seconds=delay)).isoformat() + "Z"
            time.sleep(delay)
        _state["next_run_at"] = None


def _process_item(item_id: int) -> bool:
    """Returns True if an actual download was attempted (so the caller should
    apply the random delay), False if the item was skipped as a duplicate."""
    db = SessionLocal()
    try:
        item = db.get(BulkSpoolerItem, item_id)
        if item is None:
            return False
        _state["current_item_id"] = item.id

        if item.download_id is None:
            norm = normalize_url(item.url)
            dup = find_duplicate(db, norm, exclude_item_id=item.id)
            if dup:
                item.status = BulkItemStatus.SKIPPED_DUPLICATE
                item.error_message = f"Skipped — duplicate of {dup}"
                item.started_at = item.started_at or datetime.utcnow()
                item.completed_at = datetime.utcnow()
                db.commit()
                return False

            download = Download(
                url=item.url,
                media_type=item.media_type,
                quality=item.quality,
                audio_format=item.audio_format,
                subtitles=item.subtitles,
                add_to_library=item.add_to_library,
                tag_artist=item.tag_artist,
                tag_album=item.tag_album,
                tag_title=item.tag_title,
                tag_album_artist=item.tag_album_artist,
                tag_genre=item.tag_genre,
                tag_year=item.tag_year,
                status=DownloadStatus.QUEUED,
            )
            db.add(download)
            item.status = BulkItemStatus.DOWNLOADING
            item.started_at = datetime.utcnow()
            db.commit()
            db.refresh(download)
            item.download_id = download.id
            db.commit()
            downloader.enqueue_download(download.id)

        download_id = item.download_id
    finally:
        db.close()

    while True:
        time.sleep(POLL_INTERVAL_SECONDS)
        db = SessionLocal()
        try:
            item = db.get(BulkSpoolerItem, item_id)
            if item is None or item.status == BulkItemStatus.CANCELLED:
                return True

            download = db.get(Download, download_id)
            if download is None:
                item.status = BulkItemStatus.FAILED
                item.error_message = "Linked download disappeared"
                item.completed_at = datetime.utcnow()
                db.commit()
                return True

            if download.status in TERMINAL_DOWNLOAD_STATUSES:
                if download.status == DownloadStatus.COMPLETED:
                    item.status = BulkItemStatus.COMPLETED
                elif download.status == DownloadStatus.CANCELLED:
                    item.status = BulkItemStatus.CANCELLED
                else:
                    item.status = BulkItemStatus.FAILED
                    item.error_message = download.error_message
                item.completed_at = datetime.utcnow()
                db.commit()
                return True
        finally:
            db.close()
