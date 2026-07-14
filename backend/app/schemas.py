from typing import Optional
from pydantic import BaseModel, Field


class PreviewRequest(BaseModel):
    url: str


class DownloadCreateRequest(BaseModel):
    url: str
    media_type: str = Field(default="video", pattern="^(video|audio)$")
    quality: str = "best"
    audio_format: Optional[str] = "mp3"
    subtitles: bool = False

    # library integration (audio only)
    add_to_library: bool = False
    tag_artist: Optional[str] = None
    tag_album: Optional[str] = None
    tag_title: Optional[str] = None


class SettingsUpdateRequest(BaseModel):
    download_dir: Optional[str] = None
    library_dir: Optional[str] = None
    artist_image_dir: Optional[str] = None
    max_concurrent_downloads: Optional[int] = None
    navidrome_url: Optional[str] = None
    navidrome_username: Optional[str] = None
    navidrome_password: Optional[str] = None
    navidrome_auto_scan: Optional[bool] = None


class TrackTagsUpdate(BaseModel):
    title: Optional[str] = None
    artist: Optional[str] = None
    album: Optional[str] = None
    albumartist: Optional[str] = None
    genre: Optional[str] = None
    date: Optional[str] = None
    tracknumber: Optional[str] = None
    discnumber: Optional[str] = None
    reorganize: bool = True   # move/rename the file to match Artist/Album/Title if tags changed


class OrganizeRequest(BaseModel):
    track_ids: Optional[list[str]] = None   # None = organize entire library
