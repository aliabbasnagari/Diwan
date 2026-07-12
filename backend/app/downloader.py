import queue
import threading
import time
from datetime import datetime
from pathlib import Path

import yt_dlp

from .config import DOWNLOAD_DIR, MAX_CONCURRENT_DOWNLOADS
from .database import SessionLocal
from .models import Download, DownloadStatus

# In-memory queue of download IDs waiting to be processed.
_job_queue: "queue.Queue[int]" = queue.Queue()
_workers_started = False
_lock = threading.Lock()

# active yt-dlp instances, keyed by download id, so we can cancel them
_active_downloads: dict[int, dict] = {}


def start_workers():
    """Idempotently spin up the background worker threads."""
    global _workers_started
    with _lock:
        if _workers_started:
            return
        _workers_started = True
        for _ in range(MAX_CONCURRENT_DOWNLOADS):
            t = threading.Thread(target=_worker_loop, daemon=True)
            t.start()


def enqueue_download(download_id: int):
    start_workers()
    _job_queue.put(download_id)


def cancel_download(download_id: int):
    info = _active_downloads.get(download_id)
    if info is not None:
        info["cancelled"] = True


def extract_info(url: str) -> dict:
    """Fetch metadata for a URL without downloading anything."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    return _simplify_info(info)


def _simplify_info(info: dict) -> dict:
    formats = []
    heights_seen: dict[int, dict] = {}
    has_audio_only = False

    for f in info.get("formats", []) or []:
        vcodec = f.get("vcodec")
        acodec = f.get("acodec")
        if vcodec == "none" and acodec == "none":
            continue
        if vcodec == "none" and acodec != "none":
            has_audio_only = True

        formats.append({
            "format_id": f.get("format_id"),
            "ext": f.get("ext"),
            "resolution": f.get("resolution") or (f"{f.get('height')}p" if f.get("height") else None),
            "filesize": f.get("filesize") or f.get("filesize_approx"),
            "vcodec": vcodec,
            "acodec": acodec,
            "fps": f.get("fps"),
        })

        # Track the best (largest filesize) format seen at each real height
        # so the quality dropdown reflects resolutions this video actually has.
        height = f.get("height")
        if height and vcodec != "none":
            size = f.get("filesize") or f.get("filesize_approx") or 0
            existing = heights_seen.get(height)
            if existing is None or size > existing["filesize"]:
                heights_seen[height] = {
                    "height": height,
                    "fps": f.get("fps"),
                    "filesize": size,
                }

    video_qualities = [
        {
            "value": "best",
            "label": "Best available",
            "filesize": None,
        }
    ]
    for height in sorted(heights_seen.keys(), reverse=True):
        meta = heights_seen[height]
        label = f"{height}p"
        if meta.get("fps") and meta["fps"] > 30:
            label += f" {int(meta['fps'])}fps"
        video_qualities.append({
            "value": str(height),
            "label": label,
            "filesize": meta["filesize"] or None,
        })

    return {
        "title": info.get("title"),
        "uploader": info.get("uploader") or info.get("channel"),
        "extractor": info.get("extractor_key") or info.get("extractor"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "webpage_url": info.get("webpage_url") or info.get("original_url"),
        "view_count": info.get("view_count"),
        "upload_date": info.get("upload_date"),
        "formats": formats,
        "video_qualities": video_qualities,
        "has_audio": has_audio_only or any(f["acodec"] not in (None, "none") for f in formats),
    }


def _worker_loop():
    while True:
        download_id = _job_queue.get()
        try:
            _process_download(download_id)
        except Exception as exc:  # noqa: BLE001
            _mark_failed(download_id, str(exc))
        finally:
            _active_downloads.pop(download_id, None)
            _job_queue.task_done()


def _mark_failed(download_id: int, message: str):
    db = SessionLocal()
    try:
        row = db.get(Download, download_id)
        if row:
            row.status = DownloadStatus.FAILED
            row.error_message = message[:2000]
            row.completed_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def _process_download(download_id: int):
    db = SessionLocal()
    try:
        row = db.get(Download, download_id)
        if row is None:
            return
        row.status = DownloadStatus.FETCHING_INFO
        row.started_at = datetime.utcnow()
        db.commit()

        url = row.url
        media_type = row.media_type.value if hasattr(row.media_type, "value") else row.media_type
        quality = row.quality
        audio_format = row.audio_format
        subtitles = row.subtitles
    finally:
        db.close()

    _active_downloads[download_id] = {"cancelled": False}

    outtmpl = str(DOWNLOAD_DIR / "%(title).150B [%(id)s].%(ext)s")

    def progress_hook(d):
        if _active_downloads.get(download_id, {}).get("cancelled"):
            raise yt_dlp.utils.DownloadCancelled("Cancelled by user")

        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes") or 0
            percent = (downloaded / total * 100) if total else 0.0
            _update_progress(
                download_id,
                status=DownloadStatus.DOWNLOADING,
                progress_percent=percent,
                speed=_fmt_speed(d.get("speed")),
                eta=_fmt_eta(d.get("eta")),
            )
        elif d.get("status") == "finished":
            _update_progress(
                download_id,
                status=DownloadStatus.PROCESSING,
                progress_percent=99.0,
                speed=None,
                eta=None,
            )

    format_selector = _build_format_selector(media_type, quality)

    ydl_opts = {
        "outtmpl": outtmpl,
        "format": format_selector,
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "writesubtitles": subtitles,
        "writeautomaticsub": subtitles,
        "subtitleslangs": ["en"] if subtitles else None,
        "merge_output_format": "mp4" if media_type == "video" else None
    }

    if media_type == "audio":
        # "0" = best quality for lossy codecs (e.g. highest VBR for mp3/opus);
        # ignored by yt-dlp for inherently lossless targets like wav/flac,
        # which are always encoded lossless from the best source audio track.
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": audio_format or "mp3",
            "preferredquality": "0",
        }]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)
            if media_type == "audio":
                filepath = str(Path(filepath).with_suffix(f".{audio_format or 'mp3'}"))
    except yt_dlp.utils.DownloadCancelled:
        db = SessionLocal()
        try:
            row = db.get(Download, download_id)
            if row:
                row.status = DownloadStatus.CANCELLED
                row.completed_at = datetime.utcnow()
                db.commit()
        finally:
            db.close()
        return

    simplified = _simplify_info(info)
    file_path_obj = Path(filepath)
    filesize = file_path_obj.stat().st_size if file_path_obj.exists() else None

    db = SessionLocal()
    try:
        row = db.get(Download, download_id)
        if row:
            row.status = DownloadStatus.COMPLETED
            row.progress_percent = 100.0
            row.speed = None
            row.eta = None
            row.title = simplified["title"]
            row.uploader = simplified["uploader"]
            row.extractor = simplified["extractor"]
            row.duration = simplified["duration"]
            row.thumbnail = simplified["thumbnail"]
            row.webpage_url = simplified["webpage_url"]
            row.view_count = simplified["view_count"]
            row.upload_date = simplified["upload_date"]
            row.ext = file_path_obj.suffix.lstrip(".")
            row.filesize = filesize
            row.filepath = str(file_path_obj)
            row.completed_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def _build_format_selector(media_type: str, quality: str) -> str:
    if media_type == "audio":
        return "bestaudio/best"
    if quality == "best" or not quality:
        return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    # quality is a height like "1080", "720"
    return (
        f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]"
        f"/best[height<={quality}][ext=mp4]/best[height<={quality}]/best"
    )


def _update_progress(download_id: int, status, progress_percent, speed, eta):
    db = SessionLocal()
    try:
        row = db.get(Download, download_id)
        if row:
            row.status = status
            row.progress_percent = progress_percent
            row.speed = speed
            row.eta = eta
            db.commit()
    finally:
        db.close()


def _fmt_speed(speed_bytes):
    if not speed_bytes:
        return None
    for unit in ["B/s", "KiB/s", "MiB/s", "GiB/s"]:
        if speed_bytes < 1024:
            return f"{speed_bytes:.1f}{unit}"
        speed_bytes /= 1024
    return f"{speed_bytes:.1f}TiB/s"


def _fmt_eta(eta_seconds):
    if eta_seconds is None:
        return None
    eta_seconds = int(eta_seconds)
    m, s = divmod(eta_seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"
