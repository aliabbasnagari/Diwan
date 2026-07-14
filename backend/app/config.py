import os
from pathlib import Path

# The Navidrome server Crate authenticates admin logins against. Provided
# via env (e.g. in docker-compose.yml or a .env file), not editable from
# the UI — the whole app is gated behind an admin login on this server.
NAVIDROME_URL = os.environ.get("NAVIDROME_URL", "").rstrip("/")

# Base directory for the backend
BASE_DIR = Path(__file__).resolve().parent.parent

# --- bootstrap-only config (env vars, read once at startup) ---
# Runtime-editable preferences (library path, Navidrome connection, etc.)
# live in the AppSettings DB row instead — see app/settings_service.py.

DEFAULT_DOWNLOAD_DIR = Path(os.environ.get("DOWNLOAD_DIR", BASE_DIR / "downloads"))
DEFAULT_LIBRARY_DIR = Path(os.environ.get("LIBRARY_DIR", BASE_DIR / "library"))
DEFAULT_ARTIST_IMAGE_DIR = Path(os.environ.get("ARTIST_IMAGE_DIR", DEFAULT_DOWNLOAD_DIR / "artist-images"))

DEFAULT_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_ARTIST_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.environ.get("DB_PATH", BASE_DIR / "downloader.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"

DEFAULT_MAX_CONCURRENT_DOWNLOADS = int(os.environ.get("MAX_CONCURRENT_DOWNLOADS", 2))

CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
]

DEFAULT_CONVERT_DIR = Path(os.environ.get("CONVERT_DIR", BASE_DIR / "conversions"))
DEFAULT_CONVERT_DIR.mkdir(parents=True, exist_ok=True)
(DEFAULT_CONVERT_DIR / "uploads").mkdir(parents=True, exist_ok=True)
(DEFAULT_CONVERT_DIR / "output").mkdir(parents=True, exist_ok=True)

# Audio extensions the library scanner / tag editor will consider
AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".mp4", ".ogg", ".opus", ".wav", ".wma", ".aac"}

# ffmpeg target formats offered by the Convert page
AUDIO_CONVERT_FORMATS = {
    "mp3": {"acodec": "libmp3lame", "ext": "mp3", "lossless": False, "default_bitrate": "192k"},
    "m4a": {"acodec": "aac", "ext": "m4a", "lossless": False, "default_bitrate": "192k"},
    "opus": {"acodec": "libopus", "ext": "opus", "lossless": False, "default_bitrate": "160k"},
    "ogg": {"acodec": "libvorbis", "ext": "ogg", "lossless": False, "default_bitrate": "192k"},
    "flac": {"acodec": "flac", "ext": "flac", "lossless": True},
    "wav": {"acodec": "pcm_s16le", "ext": "wav", "lossless": True},
}
AUDIO_BITRATES = ["128k", "192k", "256k", "320k"]

VIDEO_CONVERT_FORMATS = {
    "mp4": {"vcodec": "libx264", "acodec": "aac", "ext": "mp4"},
    "webm": {"vcodec": "libvpx-vp9", "acodec": "libopus", "ext": "webm"},
    "mkv": {"vcodec": "libx264", "acodec": "aac", "ext": "mkv"},
    "mov": {"vcodec": "libx264", "acodec": "aac", "ext": "mov"},
}
VIDEO_RESOLUTIONS = ["source", "2160", "1080", "720", "480", "360"]

# extensions treated as "has a video stream, offer video formats" by the
# Convert page's source-type detection (falls back to ffprobe either way)
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".flv", ".m4v"}

# Max dimension (px) album art is resized to before embedding
ALBUM_ART_MAX_SIZE = 1200

# Filenames Navidrome's default CoverArtPriority looks for in an album
# folder, in priority order (each tried with common image extensions)
FOLDER_ART_BASENAMES = ["cover", "folder", "front"]
IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".webp"]
