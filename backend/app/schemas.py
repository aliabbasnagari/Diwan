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
    tag_album_artist: Optional[str] = None
    tag_genre: Optional[str] = None
    tag_year: Optional[int] = None


class SettingsUpdateRequest(BaseModel):
    download_dir: Optional[str] = None
    library_dir: Optional[str] = None
    artist_image_dir: Optional[str] = None
    max_concurrent_downloads: Optional[int] = None
    cookies_enabled: Optional[bool] = None
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
    comment: Optional[str] = None
    reorganize: bool = True   # move/rename the file to match Artist/Album/Title if tags changed


class EditorSessionCreate(BaseModel):
    track_id: str


class EditorEffectRequest(BaseModel):
    effect: str
    params: dict = Field(default_factory=dict)
    start: Optional[float] = None   # selection in seconds; none = whole track
    end: Optional[float] = None


class EditorEditRequest(BaseModel):
    op: str   # trim | delete | cut | copy | paste | insert_silence
    start: Optional[float] = None
    end: Optional[float] = None
    position: Optional[float] = None
    seconds: Optional[float] = None


class EditorSaveRequest(BaseModel):
    mode: str = Field(default="new", pattern="^(replace|new)$")
    format: Optional[str] = None
    bitrate: Optional[str] = None
    title: Optional[str] = None


class OrganizeRequest(BaseModel):
    track_ids: Optional[list[str]] = None   # None = organize entire library
