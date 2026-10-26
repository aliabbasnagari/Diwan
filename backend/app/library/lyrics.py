from pathlib import Path

# Lyrics are stored as a plain .lrc sidecar file next to the track (same
# basename, same folder) rather than embedded in the audio tags. This is
# the format Navidrome's LyricsPriority setting checks first by default
# (".ttml,.yaml,.yml,.elrc,.lrc,.srt,.txt,embedded") and, unlike embedded
# tags, it works identically across every container format — including
# MP4/M4A, where Navidrome doesn't read an embedded lyrics tag at all.
# The file may hold either plain text or LRC-timestamped ("[mm:ss.xx]
# line") synced lyrics; Navidrome tells them apart automatically.


def lrc_path(track_path: Path) -> Path:
    return track_path.with_suffix(".lrc")


def read_lyrics(track_path: Path) -> str | None:
    path = lrc_path(track_path)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


def write_lyrics(track_path: Path, text: str) -> None:
    path = lrc_path(track_path)
    text = (text or "").strip("\n")
    if not text.strip():
        if path.exists():
            path.unlink()
        return
    path.write_text(text + "\n", encoding="utf-8")


def move_companion(old_track_path: Path, new_track_path: Path) -> None:
    """Keep a track's .lrc sidecar (if any) matched to it when the organizer
    moves/renames the track itself, so lyrics don't go missing on an edit."""
    old_lrc = lrc_path(old_track_path)
    if not old_lrc.exists():
        return
    new_lrc = lrc_path(new_track_path)
    if new_lrc.resolve() == old_lrc.resolve():
        return
    try:
        new_lrc.parent.mkdir(parents=True, exist_ok=True)
        if new_lrc.exists():
            new_lrc.unlink()
        old_lrc.rename(new_lrc)
    except OSError:
        pass
