import asyncio
import queue
import threading
from datetime import datetime
from pathlib import Path
import os

import yt_dlp
from yt_dlp.networking.impersonate import ImpersonateTarget

from .database import SessionLocal
from .models import Download, DownloadStatus
from . import settings_service, navidrome
from .library import metadata as tag_metadata
from .library import organizer

# In-memory queue of download IDs waiting to be processed.
_job_queue: "queue.Queue[int]" = queue.Queue()
_workers_started = False
_lock = threading.Lock()

# active yt-dlp instances, keyed by download id, so we can cancel them
_active_downloads: dict[int, dict] = {}

_target = ImpersonateTarget(client='chrome', version='136', os=None, os_version=None)

def start_workers():
    """Idempotently spin up the background worker threads."""
    global _workers_started
    with _lock:
        if _workers_started:
            return
        _workers_started = True
        db = SessionLocal()
        try:
            n = settings_service.get_settings(db).max_concurrent_downloads or 2
        finally:
            db.close()
        for _ in range(n):
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
    global _target
    ydl_opts = {
        "http_client": "curl_cffi",
        "impersonate": _target,
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "noplaylist": True,
        "cookiefile": "cookies.txt" if os.path.exists("cookies.txt") else None,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "Chrome/120 Safari/537.36"
                ),
            "Accept-Language": "en-US,en;q=0.9",
        },
        "verbose": True,
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

        height = f.get("height")
        if height and vcodec != "none":
            size = f.get("filesize") or f.get("filesize_approx") or 0
            existing = heights_seen.get(height)
            if existing is None or size > existing["filesize"]:
                heights_seen[height] = {"height": height, "fps": f.get("fps"), "filesize": size}

    video_qualities = [{"value": "best", "label": "Best available", "filesize": None}]
    for height in sorted(heights_seen.keys(), reverse=True):
        meta = heights_seen[height]
        label = f"{height}p"
        if meta.get("fps") and meta["fps"] > 30:
            label += f" {int(meta['fps'])}fps"
        video_qualities.append({"value": str(height), "label": label, "filesize": meta["filesize"] or None})

    return {
        "title": info.get("title"),
        "uploader": info.get("uploader") or info.get("channel"),
        "artist": info.get("artist") or info.get("uploader") or info.get("channel"),
        "track": info.get("track") or info.get("title"),
        "album": info.get("album"),
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
    global _target
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
        add_to_library = row.add_to_library
        tag_artist = row.tag_artist
        tag_album = row.tag_album
        tag_title = row.tag_title
        tag_album_artist = row.tag_album_artist
        tag_genre = row.tag_genre
        tag_year = row.tag_year


        s = settings_service.get_settings(db)
        download_dir = Path(s.library_dir if (media_type == "audio" and add_to_library) else s.download_dir)
        library_dir = Path(s.library_dir)
        navidrome_url = s.navidrome_url
        navidrome_username = s.navidrome_username
        navidrome_password = s.navidrome_password
        navidrome_auto_scan = s.navidrome_auto_scan
        download_dir.mkdir(parents=True, exist_ok=True)
    finally:
        db.close()

    _active_downloads[download_id] = {"cancelled": False}

    # Download to a temp/staging area first; library placement (if any)
    # happens after tagging, once we know the final artist/album/title.
    staging_dir = download_dir
    outtmpl = str(staging_dir / "%(title).150B [%(id)s].%(ext)s")

    def progress_hook(d):
        if _active_downloads.get(download_id, {}).get("cancelled"):
            raise yt_dlp.utils.DownloadCancelled("Cancelled by user")

        if d.get("status") == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes") or 0
            percent = (downloaded / total * 100) if total else 0.0
            _update_progress(download_id, DownloadStatus.DOWNLOADING, percent, _fmt_speed(d.get("speed")), _fmt_eta(d.get("eta")))
        elif d.get("status") == "finished":
            _update_progress(download_id, DownloadStatus.PROCESSING, 99.0, None, None)

    format_selector = _build_format_selector(media_type, quality)

    ydl_opts = {
        "http_client": "curl_cffi",
        "impersonate": _target,
        "outtmpl": outtmpl,
        "format": format_selector,
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "writesubtitles": subtitles,
        "writeautomaticsub": subtitles,
        "subtitleslangs": ["en"] if subtitles else None,
        "merge_output_format": "mp4" if media_type == "video" else None,
        "writethumbnail": media_type == "audio",
        "cookiefile": "cookies.txt" if os.path.exists("cookies.txt") else None,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "Chrome/120 Safari/537.36"
                ),
            "Accept-Language": "en-US,en;q=0.9",
        },
        "verbose": True,
    }

    if media_type == "audio":
        ydl_opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": audio_format or "mp3",
            "preferredquality": "0",
        }]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = Path(ydl.prepare_filename(info))
            if media_type == "audio":
                filepath = filepath.with_suffix(f".{audio_format or 'mp3'}")
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
    library_path_str = None

    if media_type == "audio" and add_to_library:
        _update_progress(download_id, DownloadStatus.TAGGING, 99.0, None, None)
        final_artist = tag_artist or simplified.get("artist") or "Unknown Artist"
        final_album = tag_album or simplified.get("album") or "Singles"
        final_title = tag_title or simplified.get("track") or simplified.get("title") or filepath.stem
        final_album_artist = tag_album_artist or simplified.get("album_artist") or "Unknown Album Artist"
        final_genre = tag_genre or simplified.get("genre") or "Unknown Genre"
        final_year = tag_year or simplified.get("year") or "Unknown Year"

        try:
            thumb_bytes = _find_thumbnail_bytes(filepath)
            if thumb_bytes:
                tag_metadata.write_art(filepath, thumb_bytes)
            tag_metadata.write_tags(filepath, {
                "title": final_title,
                "artist": final_artist,
                "album": final_album,
                "albumartist": final_album_artist,
                "genre": final_genre,
                "date": final_year,
            })
        except Exception:
            pass  # tagging is best-effort; keep the file even if it fails

        filepath = organizer.move_into_library(filepath, library_dir, final_artist, final_album, final_title)
        library_path_str = organizer.relative_to_library(filepath, library_dir)
        _cleanup_leftover_thumbnails(filepath)

        if navidrome_auto_scan and navidrome_url:
            try:
                asyncio.run(navidrome.start_scan(navidrome_url, navidrome_username or "", navidrome_password or ""))
            except Exception:
                pass  # scan trigger is best-effort and shouldn't fail the download
    elif media_type == "audio":
        _cleanup_leftover_thumbnails(filepath)

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
            row.library_path = library_path_str
            row.completed_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def _find_thumbnail_bytes(media_path: Path) -> bytes | None:
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        candidate = media_path.with_suffix(ext)
        if candidate.exists():
            data = candidate.read_bytes()
            return data
    return None


def _cleanup_leftover_thumbnails(media_path: Path):
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        candidate = media_path.with_suffix(ext)
        if candidate.exists() and candidate != media_path:
            try:
                candidate.unlink()
            except OSError:
                pass


def _build_format_selector(media_type: str, quality: str) -> str:
    if media_type == "audio":
        return "bestaudio/best"
    if quality == "best" or not quality:
        return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
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
