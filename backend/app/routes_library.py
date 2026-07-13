from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import Response
from sqlalchemy.orm import Session

from .database import get_db
from .schemas import TrackTagsUpdate, OrganizeRequest
from . import settings_service
from .library import scanner, metadata, organizer

router = APIRouter(prefix="/api/library", tags=["library"])


def _lib_dir(db: Session) -> Path:
    return settings_service.library_dir(db)


def _resolve(db: Session, track_id: str) -> Path:
    try:
        path = scanner.resolve_track_path(_lib_dir(db), track_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid track id")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Track not found")
    return path


@router.get("/tree")
def get_tree(db: Session = Depends(get_db)):
    return scanner.scan_tree(_lib_dir(db))


@router.get("/tracks")
def list_tracks(q: Optional[str] = Query(default=None), db: Session = Depends(get_db)):
    lib = _lib_dir(db)
    if q:
        return scanner.search(lib, q)
    return scanner.scan_flat(lib)


@router.get("/stats")
def library_stats(db: Session = Depends(get_db)):
    tree = scanner.scan_tree(_lib_dir(db))
    tracks = [t for artist in tree["artists"] for album in artist["albums"] for t in album["tracks"]]
    total_size = sum(t.get("filesize") or 0 for t in tracks)
    total_duration = sum(t.get("duration") or 0 for t in tracks)
    return {
        "artist_count": tree["artist_count"],
        "album_count": sum(a["album_count"] for a in tree["artists"]),
        "track_count": tree["track_count"],
        "total_size": total_size,
        "total_duration": total_duration,
    }


@router.get("/tracks/{track_id}")
def get_track(track_id: str, db: Session = Depends(get_db)):
    path = _resolve(db, track_id)
    return scanner.track_summary(_lib_dir(db), path)


@router.put("/tracks/{track_id}")
def update_track(track_id: str, req: TrackTagsUpdate, db: Session = Depends(get_db)):
    lib = _lib_dir(db)
    path = _resolve(db, track_id)

    patch = req.model_dump(exclude={"reorganize"}, exclude_unset=True)
    try:
        metadata.write_tags(path, patch)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not write tags: {exc}")

    new_path = path
    if req.reorganize:
        tags = metadata.read_tags(path)
        try:
            new_path = organizer.reorganize_track(
                path, lib,
                artist=tags.get("artist") or "Unknown Artist",
                album=tags.get("album") or "Singles",
                title=tags.get("title") or path.stem,
                track_number=tags.get("tracknumber"),
            )
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=f"Tags saved, but could not move file: {exc}")

    return scanner.track_summary(lib, new_path)


@router.delete("/tracks/{track_id}")
def delete_track(track_id: str, db: Session = Depends(get_db)):
    path = _resolve(db, track_id)
    try:
        path.unlink()
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Could not delete file: {exc}")
    return {"deleted": True}


@router.get("/tracks/{track_id}/artwork")
def get_artwork(track_id: str, db: Session = Depends(get_db)):
    path = _resolve(db, track_id)
    data = metadata.read_art(path)
    if not data:
        raise HTTPException(status_code=404, detail="No artwork embedded")
    return Response(content=data, media_type=metadata.sniff_image_mime(data))


@router.post("/tracks/{track_id}/artwork")
async def set_artwork(track_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    path = _resolve(db, track_id)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload")
    try:
        metadata.write_art(path, data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not embed artwork: {exc}")
    return scanner.track_summary(_lib_dir(db), path)


@router.post("/tracks/{track_id}/organize")
def organize_one(track_id: str, db: Session = Depends(get_db)):
    lib = _lib_dir(db)
    path = _resolve(db, track_id)
    tags = metadata.read_tags(path)
    new_path = organizer.reorganize_track(
        path, lib,
        artist=tags.get("artist") or "Unknown Artist",
        album=tags.get("album") or "Singles",
        title=tags.get("title") or path.stem,
        track_number=tags.get("tracknumber"),
    )
    return scanner.track_summary(lib, new_path)


@router.post("/organize")
def organize_bulk(req: OrganizeRequest, db: Session = Depends(get_db)):
    lib = _lib_dir(db)
    if req.track_ids:
        paths = [scanner.resolve_track_path(lib, tid) for tid in req.track_ids]
    else:
        paths = list(scanner._scan_files(lib))

    moved, unchanged, errors = 0, 0, []
    for path in paths:
        if not path.exists():
            continue
        try:
            tags = metadata.read_tags(path)
            new_path = organizer.reorganize_track(
                path, lib,
                artist=tags.get("artist") or "Unknown Artist",
                album=tags.get("album") or "Singles",
                title=tags.get("title") or path.stem,
                track_number=tags.get("tracknumber"),
            )
            if new_path != path:
                moved += 1
            else:
                unchanged += 1
        except Exception as exc:  # noqa: BLE001
            errors.append({"path": str(path), "error": str(exc)})

    return {"moved": moved, "unchanged": unchanged, "errors": errors}
