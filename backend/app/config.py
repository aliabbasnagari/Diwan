import os
from pathlib import Path

# Base directory for the backend
BASE_DIR = Path(__file__).resolve().parent.parent

# --- bootstrap-only config (env vars, read once at startup) ---
# Runtime-editable preferences (library path, Navidrome connection, etc.)
# live in the AppSettings DB row instead — see app/settings_service.py.

DEFAULT_DOWNLOAD_DIR = Path(os.environ.get("DOWNLOAD_DIR", BASE_DIR / "downloads"))
DEFAULT_LIBRARY_DIR = Path(os.environ.get("LIBRARY_DIR", BASE_DIR / "library"))

DEFAULT_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
DEFAULT_LIBRARY_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = Path(os.environ.get("DB_PATH", BASE_DIR / "downloader.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"

DEFAULT_MAX_CONCURRENT_DOWNLOADS = int(os.environ.get("MAX_CONCURRENT_DOWNLOADS", 2))

CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
]

# Audio extensions the library scanner / tag editor will consider
AUDIO_EXTENSIONS = {".mp3", ".flac", ".m4a", ".mp4", ".ogg", ".opus", ".wav", ".wma", ".aac"}

# Max dimension (px) album art is resized to before embedding
ALBUM_ART_MAX_SIZE = 1200
