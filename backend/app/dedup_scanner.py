import difflib
import re
import shutil
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from .database import SessionLocal
from .config import DUPLICATE_TRASH_DIRNAME
from .models import (
    TrackFingerprint, DuplicateScanJob, DuplicateScanStatus,
    DuplicateGroup, DuplicateGroupMember, DuplicateCategory, DuplicateGroupStatus,
    DuplicateIgnoredPair,
)
from . import settings_service
from .library import scanner as lib_scanner, metadata as tag_metadata, tracking, fingerprint as fp

ACTIVE_JOB_STATUSES = [
    DuplicateScanStatus.QUEUED, DuplicateScanStatus.HASHING,
    DuplicateScanStatus.FINGERPRINTING, DuplicateScanStatus.SCORING,
]

IDLE_POLL_SECONDS = 2
DURATION_BUCKET_SECONDS = 3

AUDIO_MATCH_THRESHOLD = 0.92
NEAR_MATCH_THRESHOLD = 0.75
DIFFERENT_RECORDING_TAG_THRESHOLD = 0.88
AUDIO_MATCH_DURATION_TOLERANCE = 2.0   # seconds, floor for the % based tolerance below

LOSSLESS_EXTS = {"flac", "wav", "alac", "ape"}

_lock = threading.Lock()
_worker_started = False
_cancel_flags: dict[int, bool] = {}


def start_worker():
    """Idempotently spin up the background scan worker thread."""
    global _worker_started
    with _lock:
        if _worker_started:
            return
        _worker_started = True
        threading.Thread(target=_loop, daemon=True).start()


def trigger_scan() -> dict:
    db = SessionLocal()
    try:
        active = db.query(DuplicateScanJob).filter(DuplicateScanJob.status.in_(ACTIVE_JOB_STATUSES)).first()
        if active:
            return active.to_dict()
        job = DuplicateScanJob(status=DuplicateScanStatus.QUEUED)
        db.add(job)
        db.commit()
        db.refresh(job)
        result = job.to_dict()
    finally:
        db.close()
    start_worker()
    return result


def cancel_active_scan() -> bool:
    db = SessionLocal()
    try:
        active = db.query(DuplicateScanJob).filter(DuplicateScanJob.status.in_(ACTIVE_JOB_STATUSES)).first()
        if not active:
            return False
        _cancel_flags[active.id] = True
        return True
    finally:
        db.close()


def latest_job_dict() -> dict | None:
    db = SessionLocal()
    try:
        job = db.query(DuplicateScanJob).order_by(DuplicateScanJob.created_at.desc()).first()
        return job.to_dict() if job else None
    finally:
        db.close()


def _loop():
    while True:
        job_id = _next_job_id()
        if job_id is None:
            time.sleep(IDLE_POLL_SECONDS)
            continue
        _run_job(job_id)


def _next_job_id() -> int | None:
    db = SessionLocal()
    try:
        job = (
            db.query(DuplicateScanJob)
            .filter(DuplicateScanJob.status.in_(ACTIVE_JOB_STATUSES))
            .order_by(DuplicateScanJob.created_at.asc())
            .first()
        )
        return job.id if job else None
    finally:
        db.close()


def _set_job(job_id: int, **fields):
    db = SessionLocal()
    try:
        job = db.get(DuplicateScanJob, job_id)
        if job is None:
            return
        for k, v in fields.items():
            setattr(job, k, v)
        db.commit()
    finally:
        db.close()


def _run_job(job_id: int):
    db = SessionLocal()
    try:
        job = db.get(DuplicateScanJob, job_id)
        if job is None:
            return
        job.status = DuplicateScanStatus.HASHING
        job.started_at = job.started_at or datetime.utcnow()
        job.error_message = None
        db.commit()
        library_dir = settings_service.library_dir(db)
    finally:
        db.close()

    try:
        paths = list(lib_scanner._scan_files(library_dir))
        _set_job(job_id, total=len(paths), processed=0, phase_detail=None)

        failures = 0
        failure_samples: list[str] = []
        for i, path in enumerate(paths):
            if _cancel_flags.get(job_id):
                _set_job(job_id, status=DuplicateScanStatus.CANCELLED, completed_at=datetime.utcnow())
                return
            rel = str(path.relative_to(library_dir))
            ok, error = _ensure_fingerprint(library_dir, path)
            if not ok:
                failures += 1
                print(f"[dedup_scanner] fingerprint failed for {rel}: {error}", file=sys.stderr, flush=True)
                if len(failure_samples) < 5:
                    failure_samples.append(f"{rel}: {error}")
            _set_job(
                job_id,
                processed=i + 1,
                phase_detail=rel,
                fingerprint_failures=failures,
                status=DuplicateScanStatus.FINGERPRINTING,
            )

        if _cancel_flags.get(job_id):
            _set_job(job_id, status=DuplicateScanStatus.CANCELLED, completed_at=datetime.utcnow())
            return

        _set_job(job_id, status=DuplicateScanStatus.SCORING, phase_detail=None)
        current_paths = {str(p.relative_to(library_dir)) for p in paths}
        groups_found = _build_groups(current_paths)

        warning = ("Could not fingerprint:\n" + "\n".join(failure_samples)) if failure_samples else None
        _set_job(
            job_id,
            status=DuplicateScanStatus.COMPLETED,
            groups_found=groups_found,
            error_message=warning,
            completed_at=datetime.utcnow(),
        )
    except Exception as exc:  # noqa: BLE001
        _set_job(job_id, status=DuplicateScanStatus.FAILED, error_message=str(exc)[:2000], completed_at=datetime.utcnow())
    finally:
        _cancel_flags.pop(job_id, None)


def _ensure_fingerprint(library_dir: Path, path: Path) -> tuple[bool, str | None]:
    """Returns (ok, error_message). ok=False means the acoustic fingerprint
    could not be computed for this file (e.g. fpcalc missing/unsupported
    format) — the file still gets hashed, so exact-duplicate detection
    keeps working regardless."""
    rel = str(path.relative_to(library_dir))
    try:
        stat = path.stat()
    except OSError:
        return True, None   # file vanished mid-scan — not a fingerprinting failure

    db = SessionLocal()
    try:
        row = db.query(TrackFingerprint).filter(TrackFingerprint.path == rel).first()
        if row and row.mtime_ns == stat.st_mtime_ns and row.size == stat.st_size:
            if row.chromaprint_fp or row.sha256 is not None:
                return True, None
            return False, "no cached fingerprint (a previous attempt failed — fix/re-encode the file to retry)"

        tags = tag_metadata.read_tags(path)

        ok = True
        error = None
        sha256 = None
        duration, raw_fp = None, []
        try:
            sha256 = fp.compute_sha256(path)
        except OSError as exc:
            ok = False
            error = f"could not read file to hash it: {exc}"

        if sha256 is not None:
            try:
                duration, raw_fp = fp.compute_chromaprint(path)
            except fp.FingerprintError as exc:
                ok = False
                error = str(exc)
            except Exception as exc:  # noqa: BLE001 — one bad file must not abort the whole scan
                ok = False
                error = f"unexpected error: {exc}"

        if row is None:
            row = TrackFingerprint(path=rel)
            db.add(row)
        row.mtime_ns = stat.st_mtime_ns
        row.size = stat.st_size
        row.sha256 = sha256
        row.duration = duration if duration is not None else tags.get("duration")
        row.sample_rate = tags.get("sample_rate")
        row.bitrate = tags.get("bitrate")
        row.chromaprint_fp = ",".join(str(x) for x in raw_fp) if raw_fp else None
        row.title = tags.get("title")
        row.artist = tags.get("artist")
        row.album = tags.get("album")
        row.scanned_at = datetime.utcnow()
        db.commit()
        return ok, error
    finally:
        db.close()


def _category_rank(cat: str) -> int:
    order = {
        DuplicateCategory.DIFFERENT_RECORDING.value: 0,
        DuplicateCategory.NEAR_MATCH.value: 1,
        DuplicateCategory.AUDIO_MATCH.value: 2,
        DuplicateCategory.EXACT.value: 3,
    }
    return order.get(cat, -1)


def _title_similarity(a: dict, b: dict) -> float:
    def norm(rec):
        return f"{(rec['title'] or '').strip().lower()} {(rec['artist'] or '').strip().lower()}"
    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


_TITLE_PAREN_RE = re.compile(r"\s*[\(\[].*$")      # drop "(Live)", "[Remix]", …
_TITLE_DASH_SUFFIX_RE = re.compile(r"\s+-\s+.*$")   # drop " - Remastered 2011", …


def _base_title_key(rec: dict) -> str:
    """Blocking key for the different-recording pass: strips the kind of
    suffix a live/remaster/remix/acoustic version's title usually carries,
    so e.g. "Song D" and "Song D (Live)" land in the same bucket even
    though their durations are nothing alike."""
    title = (rec["title"] or "").strip().lower()
    title = _TITLE_PAREN_RE.sub("", title)
    title = _TITLE_DASH_SUFFIX_RE.sub("", title)
    artist = (rec["artist"] or "").strip().lower()
    return f"{artist}::{title.strip()}"


def _classify_pair(a: dict, b: dict) -> str | None:
    duration_a, duration_b = a["duration"] or 0.0, b["duration"] or 0.0
    duration_diff = abs(duration_a - duration_b)
    sim = fp.fingerprint_similarity(a["fp"], b["fp"]) if a["fp"] and b["fp"] else 0.0
    tolerance = max(AUDIO_MATCH_DURATION_TOLERANCE, 0.03 * max(duration_a, duration_b, 1.0))

    if sim >= AUDIO_MATCH_THRESHOLD and duration_diff <= tolerance:
        return DuplicateCategory.AUDIO_MATCH.value
    if sim >= NEAR_MATCH_THRESHOLD:
        return DuplicateCategory.NEAR_MATCH.value
    if _title_similarity(a, b) >= DIFFERENT_RECORDING_TAG_THRESHOLD:
        return DuplicateCategory.DIFFERENT_RECORDING.value
    return None


def _suggest_keeper(members: list[dict]) -> str:
    def score(rec):
        ext = Path(rec["path"]).suffix.lstrip(".").lower()
        return (1 if ext in LOSSLESS_EXTS else 0, rec["bitrate"] or 0, rec["sample_rate"] or 0, rec["filesize"] or 0)
    return max(members, key=score)["path"]


def _build_groups(current_paths: set[str]) -> int:
    db = SessionLocal()
    try:
        # stale fingerprint rows for files no longer in the library
        for stale in db.query(TrackFingerprint).filter(~TrackFingerprint.path.in_(current_paths)).all():
            db.delete(stale)

        # fully regenerate PENDING groups each run; RESOLVED/IGNORED history stays
        pending_group_ids = [
            gid for (gid,) in db.query(DuplicateGroup.id).filter(DuplicateGroup.status == DuplicateGroupStatus.PENDING).all()
        ]
        if pending_group_ids:
            db.query(DuplicateGroupMember).filter(DuplicateGroupMember.group_id.in_(pending_group_ids)).delete(synchronize_session=False)
            db.query(DuplicateGroup).filter(DuplicateGroup.id.in_(pending_group_ids)).delete(synchronize_session=False)
        db.commit()

        ignored_pairs = {row.pair_key for row in db.query(DuplicateIgnoredPair).all()}
        rows = db.query(TrackFingerprint).filter(TrackFingerprint.path.in_(current_paths)).all()

        records = []
        for r in rows:
            fp_ints = [int(x) for x in r.chromaprint_fp.split(",")] if r.chromaprint_fp else []
            records.append({
                "path": r.path, "sha256": r.sha256, "duration": r.duration or 0.0, "fp": fp_ints,
                "title": r.title, "artist": r.artist, "album": r.album,
                "bitrate": r.bitrate, "sample_rate": r.sample_rate, "filesize": r.size,
            })

        n = len(records)
        parent = list(range(n))

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        def pair_key(i, j):
            a, b = sorted((records[i]["path"], records[j]["path"]))
            return f"{a}||{b}"

        edge_category: dict[frozenset, str] = {}
        seen_pairs = set()

        def consider_pair(i: int, j: int):
            if j <= i or (i, j) in seen_pairs:
                return
            seen_pairs.add((i, j))

            a, b = records[i], records[j]
            if a["sha256"] and a["sha256"] == b["sha256"]:
                return   # already an EXACT edge, handled separately

            if pair_key(i, j) in ignored_pairs:
                return

            category = _classify_pair(a, b)
            if category is None:
                return

            fkey = frozenset((i, j))
            existing = edge_category.get(fkey)
            if existing is None or _category_rank(category) > _category_rank(existing):
                edge_category[fkey] = category
            union(i, j)

        # --- stage 2: exact hash groups ---
        by_hash: dict[str, list[int]] = {}
        for idx, rec in enumerate(records):
            if rec["sha256"]:
                by_hash.setdefault(rec["sha256"], []).append(idx)
        for idxs in by_hash.values():
            if len(idxs) < 2:
                continue
            for a in range(len(idxs)):
                for b in range(a + 1, len(idxs)):
                    i, j = idxs[a], idxs[b]
                    if pair_key(i, j) in ignored_pairs:
                        continue
                    union(i, j)
                    edge_category[frozenset((i, j))] = DuplicateCategory.EXACT.value

        # --- stage 3+4a: duration-bucketed fingerprint comparison (audio
        # match / near match both require close duration, so this blocking
        # is safe for them) ---
        duration_buckets: dict[int, list[int]] = {}
        for idx, rec in enumerate(records):
            duration_buckets.setdefault(int(rec["duration"] // DURATION_BUCKET_SECONDS), []).append(idx)

        for bucket_key, idxs in duration_buckets.items():
            pool = set(idxs) | set(duration_buckets.get(bucket_key - 1, [])) | set(duration_buckets.get(bucket_key + 1, []))
            for i in idxs:
                for j in pool:
                    consider_pair(i, j)

        # --- stage 4b: title-blocked pass for "different recording" (live /
        # remaster / remix / cover) — these routinely have a very different
        # duration from the original, so they'd never meet the duration
        # buckets above. Block by a normalized "base title" instead. ---
        title_buckets: dict[str, list[int]] = {}
        for idx, rec in enumerate(records):
            key = _base_title_key(rec)
            if key == "::":
                continue   # no usable title/artist tags — would bucket every untagged file together
            title_buckets.setdefault(key, []).append(idx)

        for idxs in title_buckets.values():
            if len(idxs) < 2:
                continue
            for a in range(len(idxs)):
                for b in range(a + 1, len(idxs)):
                    consider_pair(idxs[a], idxs[b])

        # --- stage 5: connected components -> persisted groups ---
        components: dict[int, list[int]] = {}
        for idx in range(n):
            components.setdefault(find(idx), []).append(idx)

        groups_persisted = 0
        for members_idx in components.values():
            if len(members_idx) < 2:
                continue
            member_set = set(members_idx)
            best_category = None
            for fkey, cat in edge_category.items():
                if fkey <= member_set and (best_category is None or _category_rank(cat) > _category_rank(best_category)):
                    best_category = cat
            if best_category is None:
                continue

            group = DuplicateGroup(category=DuplicateCategory(best_category), status=DuplicateGroupStatus.PENDING)
            db.add(group)
            db.flush()

            member_records = [records[i] for i in members_idx]
            keeper_path = _suggest_keeper(member_records)
            for rec in member_records:
                db.add(DuplicateGroupMember(
                    group_id=group.id,
                    path=rec["path"], title=rec["title"], artist=rec["artist"], album=rec["album"],
                    duration=rec["duration"], bitrate=rec["bitrate"], sample_rate=rec["sample_rate"],
                    filesize=rec["filesize"], is_suggested_keeper=(rec["path"] == keeper_path),
                ))
            groups_persisted += 1

        db.commit()
        return groups_persisted
    finally:
        db.close()


def cleanup_empty_dirs(start_dir: Path, library_dir: Path):
    current = start_dir.resolve()
    root = library_dir.resolve()
    while current != root and root in current.parents:
        try:
            current.rmdir()   # only succeeds if empty
        except OSError:
            break
        current = current.parent


def resolve_group(db, group: DuplicateGroup, keep_paths: list[str], library_dir: Path) -> dict:
    members = db.query(DuplicateGroupMember).filter(DuplicateGroupMember.group_id == group.id).all()
    member_paths = {m.path for m in members}
    keep_set = set(keep_paths) & member_paths
    if not keep_set:
        raise ValueError("keep_paths must include at least one member of this group")
    if keep_set == member_paths:
        raise ValueError("at least one file must be removed — use 'not a duplicate' to keep everything")

    trash_dir = library_dir / DUPLICATE_TRASH_DIRNAME
    quarantined = []
    for m in members:
        if m.path in keep_set:
            continue
        src = (library_dir / m.path).resolve()
        if not src.exists():
            continue

        dest = trash_dir / m.path
        dest.parent.mkdir(parents=True, exist_ok=True)
        counter = 2
        base_dest = dest
        while dest.exists():
            dest = base_dest.with_name(f"{base_dest.stem} ({counter}){base_dest.suffix}")
            counter += 1

        shutil.move(str(src), str(dest))
        tracking.sync_moved_path(db, src, dest, library_dir)
        db.query(TrackFingerprint).filter(TrackFingerprint.path == m.path).delete()
        cleanup_empty_dirs(src.parent, library_dir)
        quarantined.append(m.path)

    group.status = DuplicateGroupStatus.RESOLVED
    group.resolved_at = datetime.utcnow()
    db.commit()
    return {"kept": sorted(keep_set), "quarantined": quarantined}


def ignore_group(db, group: DuplicateGroup) -> None:
    members = db.query(DuplicateGroupMember).filter(DuplicateGroupMember.group_id == group.id).all()
    paths = [m.path for m in members]
    for a in range(len(paths)):
        for b in range(a + 1, len(paths)):
            key = "||".join(sorted((paths[a], paths[b])))
            if not db.query(DuplicateIgnoredPair).filter(DuplicateIgnoredPair.pair_key == key).first():
                db.add(DuplicateIgnoredPair(pair_key=key))
    group.status = DuplicateGroupStatus.IGNORED
    db.commit()
