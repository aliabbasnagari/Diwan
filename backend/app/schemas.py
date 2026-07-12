from typing import Optional
from pydantic import BaseModel, Field


class PreviewRequest(BaseModel):
    url: str


class DownloadCreateRequest(BaseModel):
    url: str
    media_type: str = Field(default="video", pattern="^(video|audio)$")
    quality: str = "best"          # "best", "2160", "1080", "720", "480", "360"
    audio_format: Optional[str] = "mp3"   # used only when media_type == audio
    subtitles: bool = False


class DownloadResponse(BaseModel):
    id: int

    class Config:
        from_attributes = True
