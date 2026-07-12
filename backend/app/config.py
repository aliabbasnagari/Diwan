import os
from pathlib import Path

# Base directory for the backend
BASE_DIR = Path(__file__).resolve().parent.parent

# Where downloaded media files are stored
DOWNLOAD_DIR = Path(os.environ.get("DOWNLOAD_DIR", BASE_DIR / "downloads"))
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# SQLite database file
DB_PATH = Path(os.environ.get("DB_PATH", BASE_DIR / "downloader.db"))
DATABASE_URL = f"sqlite:///{DB_PATH}"

# Max number of concurrent downloads processed at once
MAX_CONCURRENT_DOWNLOADS = int(os.environ.get("MAX_CONCURRENT_DOWNLOADS", 2))

# Allowed CORS origins (React dev server default + common vite port)
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
]
