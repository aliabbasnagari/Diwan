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
    quality = Column(String, default="best")          # e.g. "best", "1080", "720", "audio only"
    audio_format = Column(String, nullable=True)       # e.g. mp3, m4a (audio-only jobs)
    subtitles = Column(Boolean, default=False)

    # --- status / progress ---
    status = Column(SAEnum(DownloadStatus), default=DownloadStatus.QUEUED, nullable=False, index=True)
    progress_percent = Column(Float, default=0.0)
    speed = Column(String, nullable=True)      # human readable, e.g. "3.2MiB/s"
    eta = Column(String, nullable=True)        # human readable, e.g. "00:12"
    error_message = Column(Text, nullable=True)

    # --- extracted metadata (populated once known) ---
    title = Column(String, nullable=True)
    uploader = Column(String, nullable=True)
    extractor = Column(String, nullable=True)   # e.g. youtube, vimeo, twitter
    duration = Column(Float, nullable=True)     # seconds
    thumbnail = Column(String, nullable=True)
    webpage_url = Column(String, nullable=True)
    view_count = Column(Integer, nullable=True)
    upload_date = Column(String, nullable=True)  # YYYYMMDD from yt-dlp
    ext = Column(String, nullable=True)
    filesize = Column(Integer, nullable=True)     # bytes, final file size
    filepath = Column(String, nullable=True)       # absolute path on disk

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
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
