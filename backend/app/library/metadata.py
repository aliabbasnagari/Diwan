"""Unified tag + album-art read/write across mp3, flac, m4a/mp4, ogg/opus, wav.

Mutagen's "easy" interface normalizes common tag names across formats but
doesn't handle embedded pictures uniformly, so art is handled per-format.
"""
from io import BytesIO
from pathlib import Path
from typing import Optional

from mutagen import File as MutagenFile
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC, ID3NoHeaderError
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggvorbis import OggVorbis
from mutagen.oggopus import OggOpus
from PIL import Image

from ..config import ALBUM_ART_MAX_SIZE

EASY_FIELDS = ["title", "artist", "album", "albumartist", "genre", "date", "tracknumber", "discnumber"]


def read_tags(path: Path) -> dict:
    tags = {f: None for f in EASY_FIELDS}
    duration = None
    bitrate = None

    try:
        audio = MutagenFile(str(path), easy=True)
        if audio is not None:
            for field in EASY_FIELDS:
                val = audio.get(field)
                if val:
                    tags[field] = val[0]
            if audio.info is not None:
                duration = getattr(audio.info, "length", None)
                bitrate = getattr(audio.info, "bitrate", None)
    except Exception:
        pass

    return {
        **tags,
        "duration": duration,
        "bitrate": bitrate,
        "has_art": read_art(path) is not None,
    }


def write_tags(path: Path, patch: dict) -> None:
    audio = MutagenFile(str(path), easy=True)
    if audio is None:
        raise ValueError(f"Unsupported or unreadable audio file: {path.name}")
    for field in EASY_FIELDS:
        value = patch.get(field)
        if value is None:
            continue
        if value == "":
            if field in audio:
                del audio[field]
        else:
            audio[field] = value
    audio.save()


def sniff_image_mime(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def read_art(path: Path) -> Optional[bytes]:
    ext = path.suffix.lower()
    try:
        if ext == ".mp3":
            id3 = ID3(str(path))
            for tag in id3.values():
                if tag.FrameID == "APIC":
                    return tag.data
        elif ext == ".flac":
            flac = FLAC(str(path))
            if flac.pictures:
                return flac.pictures[0].data
        elif ext in (".m4a", ".mp4"):
            mp4 = MP4(str(path))
            covers = mp4.get("covr")
            if covers:
                return bytes(covers[0])
        elif ext == ".ogg":
            ogg = OggVorbis(str(path))
            pics = ogg.get("metadata_block_picture")
            if pics:
                pic = Picture(BytesIO(__import__("base64").b64decode(pics[0])).read())
                return pic.data
        elif ext == ".opus":
            ogg = OggOpus(str(path))
            pics = ogg.get("metadata_block_picture")
            if pics:
                import base64
                pic = Picture(base64.b64decode(pics[0]))
                return pic.data
    except Exception:
        return None
    return None


def _resize_to_jpeg(image_bytes: bytes) -> bytes:
    img = Image.open(BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((ALBUM_ART_MAX_SIZE, ALBUM_ART_MAX_SIZE))
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def write_image_file(path: Path, image_bytes: bytes) -> None:
    """Resize/convert to JPEG and write as a standalone file — used for
    album folder covers (cover.jpg) and artist pictures, as opposed to
    write_art() which embeds into a specific track's file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_resize_to_jpeg(image_bytes))


def write_art(path: Path, image_bytes: bytes) -> None:
    """Resize/convert to JPEG and embed as the sole cover image."""
    jpeg_bytes = _resize_to_jpeg(image_bytes)

    ext = path.suffix.lower()
    if ext == ".mp3":
        try:
            id3 = ID3(str(path))
        except ID3NoHeaderError:
            id3 = ID3()
        id3.delall("APIC")
        id3.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=jpeg_bytes))
        id3.save(str(path))
    elif ext == ".flac":
        flac = FLAC(str(path))
        flac.clear_pictures()
        pic = Picture()
        pic.data = jpeg_bytes
        pic.type = 3
        pic.mime = "image/jpeg"
        flac.add_picture(pic)
        flac.save()
    elif ext in (".m4a", ".mp4"):
        mp4 = MP4(str(path))
        mp4["covr"] = [MP4Cover(jpeg_bytes, imageformat=MP4Cover.FORMAT_JPEG)]
        mp4.save()
    elif ext in (".ogg", ".opus"):
        import base64
        pic = Picture()
        pic.data = jpeg_bytes
        pic.type = 3
        pic.mime = "image/jpeg"
        encoded = base64.b64encode(pic.write()).decode("ascii")
        audio = OggOpus(str(path)) if ext == ".opus" else OggVorbis(str(path))
        audio["metadata_block_picture"] = [encoded]
        audio.save()
    else:
        raise ValueError(f"Album art embedding not supported for {ext} files")
