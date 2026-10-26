from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import Response, FileResponse
from sqlalchemy.orm import Session

from .config import AUDIO_EXTENSIONS
from .database import get_db
from .schemas import TrackTagsUpdate, OrganizeRequest, RenameRequest, LyricsUpdateRequest
from . import settings_service
from .library import scanner, metadata, organizer, tracking, lyrics

router = APIRouter(prefix="/api/library", tags=["library"])

AUDIO_MEDIA_TYPES = {
    "mp3": "audio/mpeg", "flac": "audio/flac", "m4a": "audio/mp4", "mp4": "audio/mp4",
    "ogg": "audio/ogg", "opus": "audio/opus", "wav": "audio/wav", "wma": "audio/x-ms-wma",
    "aac": "audio/aac",
}


def _lib_dir(db: Session) -> Path:
    path = settings_service.library_dir(db)
    db.rollback()  # release the pooled connection before slow disk scans
    return path


def _artist_dir(db: Session) -> Path:
    path = settings_service.artist_image_dir(db)
    db.rollback()
    return path


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


@router.get("/tracks/{track_id}/audio")
def stream_track_audio(track_id: str, db: Session = Depends(get_db)):
    path = _resolve(db, track_id)
    media_type = AUDIO_MEDIA_TYPES.get(path.suffix.lstrip(".").lower(), "application/octet-stream")
    return FileResponse(path, media_type=media_type)


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
        tracking.sync_moved_path(db, path, new_path, lib)

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


# --- track-level lyrics: a .lrc sidecar file next to the track (same
# basename, same folder) — the format Navidrome's LyricsPriority setting
# checks first by default, and the only one that works for every
# container format Diwan handles. Holds plain text or LRC-timestamped
# ("[mm:ss.xx] line") synced lyrics; Navidrome tells them apart itself. ---

@router.get("/tracks/{track_id}/lyrics")
def get_lyrics(track_id: str, db: Session = Depends(get_db)):
    path = _resolve(db, track_id)
    return {"text": lyrics.read_lyrics(path)}


@router.put("/tracks/{track_id}/lyrics")
def set_lyrics(track_id: str, req: LyricsUpdateRequest, db: Session = Depends(get_db)):
    path = _resolve(db, track_id)
    try:
        lyrics.write_lyrics(path, req.text)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Could not save lyrics: {exc}")
    return {"text": lyrics.read_lyrics(path)}


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


@router.post("/artists/{artist_id}/rename")
def rename_artist(artist_id: str, req: RenameRequest, db: Session = Depends(get_db)):
    """Rename an artist across every track grouped under it (same
    albumartist-or-artist grouping scanner.scan_tree uses), moving each
    file to match and carrying over the artist picture, if any."""
    lib = _lib_dir(db)
    old_name = _resolve_artist_name(artist_id)
    new_name = req.new_name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="New name cannot be empty")

    renamed, errors = 0, []
    if new_name != old_name:
        for path in scanner._scan_files(lib):
            try:
                tags = metadata.read_tags(path)
                grouping_artist = tags.get("albumartist") or tags.get("artist")
                if grouping_artist != old_name:
                    continue
                if tags.get("albumartist"):
                    patch = {"albumartist": new_name}
                    # the (possibly multi-value, comma-separated) artist tag
                    # may separately credit this same artist — update just
                    # that entry if so, leaving any co-artists untouched
                    artist_parts = [p.strip() for p in (tags.get("artist") or "").split(",") if p.strip()]
                    if old_name in artist_parts:
                        patch["artist"] = ", ".join(new_name if p == old_name else p for p in artist_parts)
                else:
                    patch = {"artist": new_name}
                metadata.write_tags(path, patch)
                new_tags = metadata.read_tags(path)
                new_path = organizer.reorganize_track(
                    path, lib,
                    artist=organizer.folder_artist(new_tags),
                    album=new_tags.get("album") or "Singles",
                    title=new_tags.get("title") or path.stem,
                    track_number=new_tags.get("tracknumber"),
                )
                tracking.sync_moved_path(db, path, new_path, lib)
                renamed += 1
            except Exception as exc:  # noqa: BLE001
                errors.append({"path": str(path), "error": str(exc)})

        artist_dir = _artist_dir(db)
        old_picture = scanner.artist_picture_path(artist_dir, old_name)
        if old_picture:
            new_picture = artist_dir / (organizer.sanitize(new_name, "Unknown Artist") + old_picture.suffix)
            try:
                if new_picture.resolve() != old_picture.resolve():
                    old_picture.rename(new_picture)
            except OSError as exc:
                errors.append({"path": str(old_picture), "error": str(exc)})

    return {"renamed": renamed, "errors": errors}


@router.post("/albums/{album_id}/rename")
def rename_album(album_id: str, req: RenameRequest, db: Session = Depends(get_db)):
    """Rename an album across every track in its folder, moving each file
    to match and carrying over any folder art (cover.jpg etc.)."""
    lib = _lib_dir(db)
    album_dir = _resolve_album(db, album_id)
    new_name = req.new_name.strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="New name cannot be empty")

    track_paths = [
        p for p in sorted(album_dir.iterdir())
        if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
    ]

    renamed, errors, new_dir = 0, [], None
    for path in track_paths:
        try:
            metadata.write_tags(path, {"album": new_name})
            tags = metadata.read_tags(path)
            new_path = organizer.reorganize_track(
                path, lib,
                artist=organizer.folder_artist(tags),
                album=new_name,
                title=tags.get("title") or path.stem,
                track_number=tags.get("tracknumber"),
            )
            tracking.sync_moved_path(db, path, new_path, lib)
            if new_dir is None:
                new_dir = new_path.parent
            renamed += 1
        except Exception as exc:  # noqa: BLE001
            errors.append({"path": str(path), "error": str(exc)})

    if new_dir is not None and new_dir.resolve() != album_dir.resolve():
        folder_image = scanner.find_folder_image(album_dir)
        if folder_image and folder_image.exists():
            try:
                new_dir.mkdir(parents=True, exist_ok=True)
                target = new_dir / folder_image.name
                if not target.exists():
                    folder_image.rename(target)
            except OSError as exc:
                errors.append({"path": str(folder_image), "error": str(exc)})

    return {"renamed": renamed, "errors": errors}


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
    tracking.sync_moved_path(db, path, new_path, lib)
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
                tracking.sync_moved_path(db, path, new_path, lib)
                moved += 1
            else:
                unchanged += 1
        except Exception as exc:  # noqa: BLE001
            errors.append({"path": str(path), "error": str(exc)})

    return {"moved": moved, "unchanged": unchanged, "errors": errors}
