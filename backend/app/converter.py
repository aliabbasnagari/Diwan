import json
import queue
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

from .config import DEFAULT_CONVERT_DIR, AUDIO_CONVERT_FORMATS, VIDEO_CONVERT_FORMATS, VIDEO_EXTENSIONS
from .database import SessionLocal
from .models import ConversionJob, ConversionStatus
from .library import metadata as tag_metadata, organizer

OUTPUT_DIR = DEFAULT_CONVERT_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

_job_queue: "queue.Queue[int]" = queue.Queue()
_workers_started = False
_lock = threading.Lock()
_active: dict[int, dict] = {}

WORKER_COUNT = 2


def start_workers():
    global _workers_started
    with _lock:
        if _workers_started:
            return
        _workers_started = True
        for _ in range(WORKER_COUNT):
            threading.Thread(target=_worker_loop, daemon=True).start()


def enqueue(job_id: int):
    start_workers()
    _job_queue.put(job_id)


def cancel(job_id: int):
    info = _active.get(job_id)
    if info is not None:
        info["cancelled"] = True
        proc = info.get("proc")
        if proc and proc.poll() is None:
            proc.terminate()


def probe_duration(path: Path) -> float | None:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(out.stdout or "{}")
        return float(data["format"]["duration"])
    except Exception:  # noqa: BLE001
        return None


def probe_has_video(path: Path) -> bool:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_type", "-of", "json", str(path)],
            capture_output=True, text=True, timeout=30,
        )
        data = json.loads(out.stdout or "{}")
        return bool(data.get("streams"))
    except Exception:  # noqa: BLE001
        return path.suffix.lower() in VIDEO_EXTENSIONS


def _worker_loop():
    while True:
        job_id = _job_queue.get()
        try:
            _process(job_id)
        except Exception as exc:  # noqa: BLE001
            _fail(job_id, str(exc))
        finally:
            _active.pop(job_id, None)
            _job_queue.task_done()


def _fail(job_id: int, message: str):
    db = SessionLocal()
    try:
        row = db.get(ConversionJob, job_id)
        if row:
            row.status = ConversionStatus.FAILED
            row.error_message = message[:2000]
            row.completed_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def _update_progress(job_id: int, pct: float, speed: str | None = None):
    db = SessionLocal()
    try:
        row = db.get(ConversionJob, job_id)
        if row:
            row.progress_percent = pct
            if speed:
                row.speed = speed
            db.commit()
    finally:
        db.close()


def _process(job_id: int):
    db = SessionLocal()
    try:
        row = db.get(ConversionJob, job_id)
        if row is None:
            return
        row.status = ConversionStatus.CONVERTING
        row.started_at = datetime.utcnow()
        db.commit()

        source_path = Path(row.source_path)
        source_filename = row.source_filename
        target_format = row.target_format.lower()
        target_bitrate = row.target_bitrate
        target_resolution = row.target_resolution
        save_to_library = row.save_to_library
    finally:
        db.close()

    if not source_path.exists():
        raise RuntimeError("Source file no longer exists")

    duration = probe_duration(source_path)
    if duration:
        db = SessionLocal()
        try:
            row = db.get(ConversionJob, job_id)
            if row:
                row.source_duration = duration
                db.commit()
        finally:
            db.close()

    is_audio_target = target_format in AUDIO_CONVERT_FORMATS
    spec = AUDIO_CONVERT_FORMATS.get(target_format) or VIDEO_CONVERT_FORMATS.get(target_format)
    if not spec:
        raise RuntimeError(f"Unsupported target format: {target_format}")

    stem = Path(source_filename).stem
    output_path = OUTPUT_DIR / f"{stem} [{job_id}].{spec['ext']}"

    cmd = ["ffmpeg", "-y", "-i", str(source_path)]
    if is_audio_target:
        cmd += ["-vn", "-acodec", spec["acodec"]]
        if not spec.get("lossless") and target_bitrate:
            cmd += ["-b:a", target_bitrate]
    else:
        cmd += ["-c:v", spec["vcodec"], "-c:a", spec["acodec"]]
        if target_resolution and target_resolution != "source":
            cmd += ["-vf", f"scale=-2:{target_resolution}"]
        if target_format == "webm":
            cmd += ["-b:v", "0", "-crf", "32"]
        else:
            cmd += ["-preset", "medium", "-crf", "22"]
    cmd += ["-progress", "pipe:1", "-nostats", str(output_path)]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1)
    _active[job_id] = {"proc": proc, "cancelled": False}

    last_update = 0.0
    speed = None
    for line in proc.stdout:
        line = line.strip()
        if _active.get(job_id, {}).get("cancelled"):
            proc.terminate()
            break
        if line.startswith("speed="):
            speed = line.split("=", 1)[1].strip()
        elif line.startswith("out_time_ms=") and duration:
            try:
                out_ms = int(line.split("=", 1)[1])
                pct = min(99.0, (out_ms / 1_000_000) / duration * 100)
                now = time.time()
                if now - last_update > 0.5:
                    _update_progress(job_id, pct, speed)
                    last_update = now
            except (ValueError, IndexError):
                pass

    proc.wait()

    if _active.get(job_id, {}).get("cancelled"):
        output_path.unlink(missing_ok=True)
        db = SessionLocal()
        try:
            row = db.get(ConversionJob, job_id)
            if row:
                row.status = ConversionStatus.CANCELLED
                row.completed_at = datetime.utcnow()
                db.commit()
        finally:
            db.close()
        return

    if proc.returncode != 0 or not output_path.exists():
        raise RuntimeError(f"ffmpeg exited with code {proc.returncode}")

    filesize = output_path.stat().st_size

    library_path = None
    if is_audio_target and save_to_library:
        library_path = _save_audio_to_library(output_path, source_path)

    db = SessionLocal()
    try:
        row = db.get(ConversionJob, job_id)
        if row:
            row.status = ConversionStatus.COMPLETED
            row.progress_percent = 100.0
            row.speed = None
            row.output_path = str(output_path)
            row.output_filesize = filesize
            row.library_path = library_path
            row.completed_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()


def _save_audio_to_library(output_path: Path, source_path: Path) -> str:
    from . import settings_service

    db = SessionLocal()
    try:
        lib_dir = settings_service.library_dir(db)
    finally:
        db.close()

    tags = {}
    try:
        tags = tag_metadata.read_tags(source_path)
    except Exception:  # noqa: BLE001
        pass

    artist = (tags.get("artist") if tags else None) or "Unknown Artist"
    albumartist = tags.get("albumartist") if tags else None
    album = (tags.get("album") if tags else None) or "Singles"
    title = (tags.get("title") if tags else None) or output_path.stem
    tracknumber = tags.get("tracknumber") if tags else None

    tag_patch = {"title": title, "artist": artist, "album": album}
    if albumartist:
        tag_patch["albumartist"] = albumartist
    try:
        tag_metadata.write_tags(output_path, tag_patch)
    except Exception:  # noqa: BLE001
        pass

    folder_artist = albumartist or artist
    new_path = organizer.move_into_library(output_path, lib_dir, folder_artist, album, title, tracknumber)
    return str(new_path.relative_to(lib_dir))
