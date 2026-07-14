import enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, Enum as SAEnum, Boolean
)

from .database import Base


class DownloadStatus(str, enum.Enum):
    QUEUED = "queued"
    FETCHING_INFO = "fetching_info"
    DOWNLOADING = "downloading"
    PROCESSING = "processing"
    TAGGING = "tagging"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MediaType(str, enum.Enum):
    VIDEO = "video"
    AUDIO = "audio"


class Download(Base):
    """Stores every download job: request params, live progress, and the
    resulting file/media metadata. Doubles as the persistent history log."""

    __tablename__ = "downloads"

    id = Column(Integer, primary_key=True, index=True)

    # --- request info ---
    url = Column(String, nullable=False, index=True)
    media_type = Column(SAEnum(MediaType), default=MediaType.VIDEO, nullable=False)
    quality = Column(String, default="best")          # e.g. "best", "1080", "720"
    audio_format = Column(String, nullable=True)       # e.g. mp3, m4a (audio-only jobs)
    subtitles = Column(Boolean, default=False)

    # --- library integration (audio jobs only) ---
    add_to_library = Column(Boolean, default=False)
    tag_artist = Column(String, nullable=True)     # user-supplied / overridden before download
    tag_album = Column(String, nullable=True)
    tag_title = Column(String, nullable=True)

    # --- status / progress ---
    status = Column(SAEnum(DownloadStatus), default=DownloadStatus.QUEUED, nullable=False, index=True)
    progress_percent = Column(Float, default=0.0)
    speed = Column(String, nullable=True)
    eta = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)

    # --- extracted metadata (populated once known) ---
    title = Column(String, nullable=True)
    uploader = Column(String, nullable=True)
    extractor = Column(String, nullable=True)
    duration = Column(Float, nullable=True)
    thumbnail = Column(String, nullable=True)
    webpage_url = Column(String, nullable=True)
    view_count = Column(Integer, nullable=True)
    upload_date = Column(String, nullable=True)
    ext = Column(String, nullable=True)
    filesize = Column(Integer, nullable=True)
    filepath = Column(String, nullable=True)          # final location on disk (library or downloads dir)
    library_path = Column(String, nullable=True)       # relative path within LIBRARY_DIR, if added to library

    # --- timestamps ---
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "url": self.url,
            "media_type": self.media_type.value if self.media_type else None,
            "quality": self.quality,
            "audio_format": self.audio_format,
            "subtitles": self.subtitles,
            "add_to_library": self.add_to_library,
            "tag_artist": self.tag_artist,
            "tag_album": self.tag_album,
            "tag_title": self.tag_title,
            "status": self.status.value if self.status else None,
            "progress_percent": round(self.progress_percent or 0, 1),
            "speed": self.speed,
            "eta": self.eta,
            "error_message": self.error_message,
            "title": self.title,
            "uploader": self.uploader,
            "extractor": self.extractor,
            "duration": self.duration,
            "thumbnail": self.thumbnail,
            "webpage_url": self.webpage_url,
            "view_count": self.view_count,
            "upload_date": self.upload_date,
            "ext": self.ext,
            "filesize": self.filesize,
            "filepath": self.filepath,
            "library_path": self.library_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class ConversionStatus(str, enum.Enum):
    QUEUED = "queued"
    CONVERTING = "converting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ConversionJob(Base):
    """One ffmpeg conversion: an uploaded file, or an existing library
    track / spooler download, re-encoded into a different format."""

    __tablename__ = "conversion_jobs"

    id = Column(Integer, primary_key=True, index=True)

    # --- source ---
    source_kind = Column(String, nullable=False)      # "upload" | "library" | "download"
    source_ref = Column(String, nullable=True)          # track id / download id, if not an upload
    source_path = Column(String, nullable=False)          # resolved absolute path being read
    source_filename = Column(String, nullable=False)
    source_duration = Column(Float, nullable=True)

    # --- target ---
    target_format = Column(String, nullable=False)    # e.g. mp3, flac, mp4, webm
    target_bitrate = Column(String, nullable=True)      # audio only, e.g. "192k"
    target_resolution = Column(String, nullable=True)     # video only, e.g. "1080" or "source"
    save_to_library = Column(Boolean, default=False)        # audio output: tag + move into the library

    # --- status / progress ---
    status = Column(SAEnum(ConversionStatus), default=ConversionStatus.QUEUED, nullable=False, index=True)
    progress_percent = Column(Float, default=0.0)
    speed = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)

    # --- result ---
    output_path = Column(String, nullable=True)
    output_filesize = Column(Integer, nullable=True)
    library_path = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "source_kind": self.source_kind,
            "source_ref": self.source_ref,
            "source_filename": self.source_filename,
            "source_duration": self.source_duration,
            "target_format": self.target_format,
            "target_bitrate": self.target_bitrate,
            "target_resolution": self.target_resolution,
            "save_to_library": self.save_to_library,
            "status": self.status.value if self.status else None,
            "progress_percent": round(self.progress_percent or 0, 1),
            "speed": self.speed,
            "error_message": self.error_message,
            "output_filesize": self.output_filesize,
            "library_path": self.library_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class AppSettings(Base):
    """Single-row table of user-editable runtime settings."""

    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, default=1)

    download_dir = Column(String, nullable=False)
    library_dir = Column(String, nullable=False)
    artist_image_dir = Column(String, nullable=True)
    max_concurrent_downloads = Column(Integer, default=2)

    navidrome_url = Column(String, nullable=True)
    navidrome_username = Column(String, nullable=True)
    navidrome_password = Column(String, nullable=True)
    navidrome_auto_scan = Column(Boolean, default=False)

    session_secret = Column(String, nullable=True)  # signs admin login session tokens; never exposed via to_dict

    def to_dict(self, include_secrets: bool = False):
        from .config import NAVIDROME_URL
        d = {
            "download_dir": self.download_dir,
            "library_dir": self.library_dir,
            "artist_image_dir": self.artist_image_dir,
            "max_concurrent_downloads": self.max_concurrent_downloads,
            "navidrome_url": self.navidrome_url,
            "navidrome_url_locked": bool(NAVIDROME_URL),
            "navidrome_username": self.navidrome_username,
            "navidrome_auto_scan": self.navidrome_auto_scan,
            "navidrome_password_set": bool(self.navidrome_password),
        }
        if include_secrets:
            d["navidrome_password"] = self.navidrome_password
        return d
