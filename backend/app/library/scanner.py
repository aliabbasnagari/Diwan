import base64
from pathlib import Path

from ..config import AUDIO_EXTENSIONS
from . import metadata


def encode_track_id(relative_path: str) -> str:
    return base64.urlsafe_b64encode(relative_path.encode("utf-8")).decode("ascii").rstrip("=")


def decode_track_id(track_id: str) -> str:
    padded = track_id + "=" * (-len(track_id) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")


def resolve_track_path(library_dir: Path, track_id: str) -> Path:
    rel = decode_track_id(track_id)
    path = (library_dir / rel).resolve()
    library_dir = library_dir.resolve()
    if library_dir not in path.parents and path != library_dir:
        raise ValueError("Path escapes library directory")
    return path


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
        "id": encode_track_id(rel),
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


def scan_tree(library_dir: Path) -> dict:
    """{ artists: [ { name, albums: [ { name, tracks: [...] } ] } ] }"""
    tracks = scan_flat(library_dir)

    artists: dict[str, dict[str, list[dict]]] = {}
    for t in tracks:
        artists.setdefault(t["artist"], {}).setdefault(t["album"], []).append(t)

    result = []
    for artist_name in sorted(artists.keys(), key=str.lower):
        albums = artists[artist_name]
        album_list = []
        for album_name in sorted(albums.keys(), key=str.lower):
            album_tracks = sorted(
                albums[album_name],
                key=lambda t: (_track_sort_key(t["tracknumber"]), t["title"] or ""),
            )
            album_list.append({
                "name": album_name,
                "track_count": len(album_tracks),
                "tracks": album_tracks,
            })
        result.append({
            "name": artist_name,
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
