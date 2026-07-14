import base64
from pathlib import Path

from ..config import AUDIO_EXTENSIONS, FOLDER_ART_BASENAMES, IMAGE_EXTENSIONS
from . import metadata
from .organizer import sanitize


def encode_id(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii").rstrip("=")


def decode_id(value: str) -> str:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")


# kept for backwards compatibility with earlier track-id helpers
encode_track_id = encode_id
decode_track_id = decode_id


def resolve_track_path(library_dir: Path, track_id: str) -> Path:
    rel = decode_id(track_id)
    path = (library_dir / rel).resolve()
    library_dir = library_dir.resolve()
    if library_dir not in path.parents and path != library_dir:
        raise ValueError("Path escapes library directory")
    return path


def resolve_album_dir(library_dir: Path, album_id: str) -> Path:
    rel = decode_id(album_id)
    path = (library_dir / rel).resolve()
    library_dir = library_dir.resolve()
    if library_dir not in path.parents and path != library_dir:
        raise ValueError("Path escapes library directory")
    return path


def find_folder_image(dir_path: Path) -> Path | None:
    """Mirrors Navidrome's default CoverArtPriority folder-image lookup
    (cover.*, folder.*, front.*), case-insensitively."""
    if not dir_path.is_dir():
        return None
    lower_map = {p.name.lower(): p for p in dir_path.iterdir() if p.is_file()}
    for base in FOLDER_ART_BASENAMES:
        for ext in IMAGE_EXTENSIONS:
            hit = lower_map.get(f"{base}{ext}")
            if hit:
                return hit
    return None


def _scan_files(library_dir: Path):
    if not library_dir.exists():
        return
    for path in sorted(library_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in AUDIO_EXTENSIONS:
            yield path


def track_summary(library_dir: Path, path: Path) -> dict:
    rel = str(path.resolve().relative_to(library_dir.resolve()))
    tags = metadata.read_tags(path)
    stat = path.stat()
    return {
        "id": encode_id(rel),
        "path": rel,
        "filename": path.name,
        "ext": path.suffix.lstrip(".").lower(),
        "title": tags["title"] or path.stem,
        "artist": tags["artist"] or "Unknown Artist",
        "album": tags["album"] or "Unknown Album",
        "albumartist": tags["albumartist"],
        "genre": tags["genre"],
        "date": tags["date"],
        "tracknumber": tags["tracknumber"],
        "discnumber": tags["discnumber"],
        "duration": tags["duration"],
        "bitrate": tags["bitrate"],
        "has_art": tags["has_art"],
        "filesize": stat.st_size,
        "modified_at": stat.st_mtime,
    }


def scan_flat(library_dir: Path) -> list[dict]:
    return [track_summary(library_dir, p) for p in _scan_files(library_dir)]


def artist_picture_path(artist_image_dir: Path, artist_name: str) -> Path | None:
    if not artist_image_dir.is_dir():
        return None
    target_stub = sanitize(artist_name, "Unknown Artist").lower()
    for ext in IMAGE_EXTENSIONS:
        candidate = artist_image_dir / f"{sanitize(artist_name, 'Unknown Artist')}{ext}"
        if candidate.exists():
            return candidate
    # case-insensitive fallback in case the file was placed by hand
    for p in artist_image_dir.iterdir():
        if p.is_file() and p.stem.lower() == target_stub and p.suffix.lower() in IMAGE_EXTENSIONS:
            return p
    return None


def scan_tree(library_dir: Path, artist_image_dir: Path | None = None) -> dict:
    """{ artists: [ { id, name, has_picture, albums: [ { id, name, dir, has_folder_art, tracks: [...] } ] } ] }

    Grouped by albumartist (falling back to the track's own artist when
    albumartist isn't set) — the canonical "who this album belongs to"
    field, so a track crediting multiple/featured artists doesn't get
    split off into its own pseudo-artist. This is also what artist
    picture files are named after.
    """
    tracks = scan_flat(library_dir)

    artists: dict[str, dict[str, list[dict]]] = {}
    for t in tracks:
        grouping_artist = t["albumartist"] or t["artist"]
        artists.setdefault(grouping_artist, {}).setdefault(t["album"], []).append(t)

    result = []
    for artist_name in sorted(artists.keys(), key=str.lower):
        albums = artists[artist_name]
        album_list = []
        for album_name in sorted(albums.keys(), key=str.lower):
            album_tracks = sorted(
                albums[album_name],
                key=lambda t: (_track_sort_key(t["tracknumber"]), t["title"] or ""),
            )
            album_dir_rel = str(Path(album_tracks[0]["path"]).parent)
            album_dir_abs = library_dir / album_dir_rel
            album_list.append({
                "id": encode_id(album_dir_rel),
                "name": album_name,
                "dir": album_dir_rel,
                "track_count": len(album_tracks),
                "has_folder_art": find_folder_image(album_dir_abs) is not None,
                "tracks": album_tracks,
            })
        has_picture = False
        if artist_image_dir is not None:
            has_picture = artist_picture_path(artist_image_dir, artist_name) is not None
        result.append({
            "id": encode_id(artist_name),
            "name": artist_name,
            "has_picture": has_picture,
            "album_count": len(album_list),
            "track_count": sum(a["track_count"] for a in album_list),
            "albums": album_list,
        })
    return {
        "artists": result,
        "artist_count": len(result),
        "track_count": len(tracks),
    }


def _track_sort_key(tracknumber) -> int:
    if not tracknumber:
        return 9999
    try:
        return int(str(tracknumber).split("/")[0])
    except (ValueError, TypeError):
        return 9999


def search(library_dir: Path, query: str) -> list[dict]:
    q = query.lower().strip()
    if not q:
        return []
    results = []
    for t in scan_flat(library_dir):
        haystack = " ".join(str(t.get(f, "") or "") for f in ("title", "artist", "album", "albumartist"))
        if q in haystack.lower():
            results.append(t)
    return results
