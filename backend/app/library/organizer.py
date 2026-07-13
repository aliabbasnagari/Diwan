import re
import shutil
from pathlib import Path

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize(name: str, fallback: str = "Unknown") -> str:
    name = (name or "").strip()
    name = _INVALID_CHARS.sub("", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name or fallback


def build_library_path(library_dir: Path, artist: str, album: str, title: str, track_number: str | None, ext: str) -> Path:
    """Artist/Album/[NN - ]Title.ext, with each segment sanitized and the
    whole thing guaranteed unique within the target directory."""
    artist = sanitize(artist, "Unknown Artist")
    album = sanitize(album, "Singles")
    title = sanitize(title, "Untitled")
    ext = ext.lstrip(".")

    prefix = ""
    if track_number:
        try:
            prefix = f"{int(str(track_number).split('/')[0]):02d} - "
        except (ValueError, TypeError):
            prefix = ""

    target_dir = library_dir / artist / album
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{prefix}{title}.{ext}"
    target = target_dir / filename
    counter = 2
    while target.exists():
        target = target_dir / f"{prefix}{title} ({counter}).{ext}"
        counter += 1
    return target


def move_into_library(src: Path, library_dir: Path, artist: str, album: str, title: str, track_number: str | None = None) -> Path:
    dest = build_library_path(library_dir, artist, album, title, track_number, src.suffix)
    shutil.move(str(src), str(dest))
    return dest


def reorganize_track(path: Path, library_dir: Path, artist: str, album: str, title: str, track_number: str | None = None) -> Path:
    """Move a track already inside the library to match its current tags,
    e.g. after an edit. No-op (and no rename-collision handling needed)
    if the file is already exactly where it should be."""
    artist_s = sanitize(artist, "Unknown Artist")
    album_s = sanitize(album, "Singles")
    title_s = sanitize(title, "Untitled")
    ext = path.suffix.lstrip(".")

    prefix = ""
    if track_number:
        try:
            prefix = f"{int(str(track_number).split('/')[0]):02d} - "
        except (ValueError, TypeError):
            prefix = ""

    target_dir = library_dir / artist_s / album_s
    target = target_dir / f"{prefix}{title_s}.{ext}"

    if target.resolve() == path.resolve():
        return path

    target_dir.mkdir(parents=True, exist_ok=True)
    counter = 2
    while target.exists():
        target = target_dir / f"{prefix}{title_s} ({counter}).{ext}"
        counter += 1

    shutil.move(str(path), str(target))

    # clean up now-empty parent directories left behind (but never the library root)
    old_parent = path.parent.resolve()
    lib_root = library_dir.resolve()
    while old_parent != lib_root and lib_root in old_parent.parents:
        try:
            old_parent.rmdir()  # only succeeds if empty
        except OSError:
            break
        old_parent = old_parent.parent

    return target


def relative_to_library(path: Path, library_dir: Path) -> str:
    return str(Path(path).resolve().relative_to(Path(library_dir).resolve()))
