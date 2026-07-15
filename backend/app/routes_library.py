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


def _artist_dir(db: Session) -> Path:
    return settings_service.artist_image_dir(db)


def _resolve(db: Session, track_id: str) -> Path:
    try:
        path = scanner.resolve_track_path(_lib_dir(db), track_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid track id")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Track not found")
    return path


def _resolve_album(db: Session, album_id: str) -> Path:
    try:
        path = scanner.resolve_album_dir(_lib_dir(db), album_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid album id")
    if not path.exists() or not path.is_dir():
        raise HTTPException(status_code=404, detail="Album not found")
    return path


def _resolve_artist_name(artist_id: str) -> str:
    try:
        return scanner.decode_id(artist_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid artist id")


@router.get("/tree")
def get_tree(db: Session = Depends(get_db)):
    return scanner.scan_tree(_lib_dir(db), _artist_dir(db))


@router.get("/tracks")
def list_tracks(q: Optional[str] = Query(default=None), db: Session = Depends(get_db)):
    lib = _lib_dir(db)
    if q:
        return scanner.search(lib, q)
    return scanner.scan_flat(lib)


@router.get("/stats")
def library_stats(db: Session = Depends(get_db)):
    tree = scanner.scan_tree(_lib_dir(db), _artist_dir(db))
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
                artist=organizer.folder_artist(tags),
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


# --- track-level artwork: embedded in that one file only ---

@router.get("/tracks/{track_id}/artwork")
def get_track_artwork(track_id: str, db: Session = Depends(get_db)):
    path = _resolve(db, track_id)
    data = metadata.read_art(path)
    if not data:
        raise HTTPException(status_code=404, detail="No artwork embedded")
    return Response(content=data, media_type=metadata.sniff_image_mime(data))


@router.post("/tracks/{track_id}/artwork")
async def set_track_artwork(track_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    path = _resolve(db, track_id)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload")
    try:
        metadata.write_art(path, data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not embed artwork: {exc}")
    return scanner.track_summary(_lib_dir(db), path)


# --- album-level artwork: a cover.jpg file in the album folder (what
# Navidrome actually prefers, per its default CoverArtPriority), plus
# embedded into every track in that folder for portability ---

@router.get("/albums/{album_id}/artwork")
def get_album_artwork(album_id: str, db: Session = Depends(get_db)):
    album_dir = _resolve_album(db, album_id)
    folder_image = scanner.find_folder_image(album_dir)
    if folder_image:
        data = folder_image.read_bytes()
        return Response(content=data, media_type=metadata.sniff_image_mime(data))
    # fall back to the first track's embedded art
    for track_path in sorted(album_dir.iterdir()):
        if track_path.is_file() and track_path.suffix.lower() in {".mp3", ".flac", ".m4a", ".mp4", ".ogg", ".opus"}:
            data = metadata.read_art(track_path)
            if data:
                return Response(content=data, media_type=metadata.sniff_image_mime(data))
    raise HTTPException(status_code=404, detail="No artwork found for this album")


@router.post("/albums/{album_id}/artwork")
async def set_album_artwork(album_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    album_dir = _resolve_album(db, album_id)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload")

    try:
        metadata.write_image_file(album_dir / "cover.jpg", data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not write cover.jpg: {exc}")

    # also embed into every track in the folder, for players that only
    # read embedded art (Navidrome itself prefers cover.jpg by default)
    embedded, failed = 0, 0
    for track_path in sorted(album_dir.iterdir()):
        if track_path.is_file() and track_path.suffix.lower() in {".mp3", ".flac", ".m4a", ".mp4", ".ogg", ".opus"}:
            try:
                metadata.write_art(track_path, data)
                embedded += 1
            except Exception:  # noqa: BLE001
                failed += 1

    return {"cover_written": True, "tracks_embedded": embedded, "tracks_failed": failed}


# --- artist pictures: written to a dedicated folder outside the music
# library (Navidrome can be pointed at it via ArtistImageFolder) ---

@router.get("/artists/{artist_id}/picture")
def get_artist_picture(artist_id: str, db: Session = Depends(get_db)):
    name = _resolve_artist_name(artist_id)
    path = scanner.artist_picture_path(_artist_dir(db), name)
    if not path:
        raise HTTPException(status_code=404, detail="No picture set for this artist")
    data = path.read_bytes()
    return Response(content=data, media_type=metadata.sniff_image_mime(data))


@router.post("/artists/{artist_id}/picture")
async def set_artist_picture(artist_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    name = _resolve_artist_name(artist_id)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload")

    artist_dir = _artist_dir(db)
    filename = organizer.sanitize(name, "Unknown Artist") + ".jpg"
    try:
        metadata.write_image_file(artist_dir / filename, data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Could not save artist picture: {exc}")

    return {"artist": name, "picture_saved": True, "artist_image_dir": str(artist_dir)}


@router.post("/tracks/{track_id}/organize")
def organize_one(track_id: str, db: Session = Depends(get_db)):
    lib = _lib_dir(db)
    path = _resolve(db, track_id)
    tags = metadata.read_tags(path)
    new_path = organizer.reorganize_track(
        path, lib,
        artist=organizer.folder_artist(tags),
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
                artist=organizer.folder_artist(tags),
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
