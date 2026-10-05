"""Audio trimming on top of ffmpeg.

A session decodes a library track into a working 16-bit PCM WAV and keeps a
stack of versions — every edit (keep selection, remove selection, add
silence, auto-trim) renders the current version into a new file, so
undo/redo is just moving a pointer. Nothing touches the library file until
``export`` is called.
"""
import array
import shutil
import subprocess
import sys
import threading
import time
import uuid
import wave
from dataclasses import dataclass, field
from pathlib import Path

from .config import DEFAULT_CONVERT_DIR, AUDIO_CONVERT_FORMATS
from .library import metadata

FFMPEG = "ffmpeg"

EDITOR_DIR = DEFAULT_CONVERT_DIR / "editor"
MAX_UNDO_DEPTH = 10
SESSION_IDLE_SECONDS = 6 * 3600
MAX_INSERT_SILENCE = 600.0
AUTO_TRIM_THRESHOLD_DB = -50
EPS = 0.001


class EditorError(Exception):
    """A problem with the request itself (bad range, unsupported format, ...)."""


# --------------------------------------------------------------------------
# ffmpeg helpers
# --------------------------------------------------------------------------

def _run_ffmpeg(args: list[str], timeout: int = 900) -> None:
    cmd = [FFMPEG, "-hide_banner", "-nostdin", "-y", *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise EditorError("ffmpeg was not found on PATH")
    except subprocess.TimeoutExpired:
        raise EditorError("ffmpeg timed out")
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-4:]
        raise EditorError("ffmpeg failed: " + " | ".join(tail))


def _layout(channels: int) -> str:
    return "mono" if channels == 1 else "stereo"


def wav_info(path: Path) -> dict:
    with wave.open(str(path), "rb") as w:
        sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
    return {"sample_rate": sr, "channels": ch, "frames": n, "duration": n / sr if sr else 0.0}


# --------------------------------------------------------------------------
# sessions
# --------------------------------------------------------------------------

@dataclass
class Version:
    id: int
    path: Path
    label: str


@dataclass
class Session:
    id: str
    source_path: Path
    dir: Path
    versions: list[Version] = field(default_factory=list)
    index: int = 0
    saved_version_id: int | None = None
    next_id: int = 0
    last_used: float = field(default_factory=time.time)
    lock: threading.RLock = field(default_factory=threading.RLock)

    @property
    def current(self) -> Version:
        return self.versions[self.index]

    def new_path(self) -> tuple[int, Path]:
        vid = self.next_id
        self.next_id += 1
        return vid, self.dir / f"v{vid}.wav"

    def push(self, vid: int, path: Path, label: str) -> None:
        # a new edit discards any redo history
        for v in self.versions[self.index + 1:]:
            v.path.unlink(missing_ok=True)
        del self.versions[self.index + 1:]
        self.versions.append(Version(vid, path, label))
        while len(self.versions) > MAX_UNDO_DEPTH + 1:
            self.versions.pop(0).path.unlink(missing_ok=True)
        self.index = len(self.versions) - 1

    def info(self) -> dict:
        wi = wav_info(self.current.path)
        return {
            "id": self.id,
            "version": self.current.id,
            "duration": wi["duration"],
            "sample_rate": wi["sample_rate"],
            "channels": wi["channels"],
            "can_undo": self.index > 0,
            "can_redo": self.index < len(self.versions) - 1,
            "history": [v.label for v in self.versions[1:self.index + 1]],
            "dirty": self.current.id != self.saved_version_id,
            "source_filename": self.source_path.name,
            "source_ext": self.source_path.suffix.lstrip(".").lower(),
        }


_sessions: dict[str, Session] = {}
_sessions_lock = threading.Lock()


def cleanup_all() -> None:
    """Called at startup: working files from a previous run are orphaned."""
    shutil.rmtree(EDITOR_DIR, ignore_errors=True)
    EDITOR_DIR.mkdir(parents=True, exist_ok=True)


def _reap_idle() -> None:
    cutoff = time.time() - SESSION_IDLE_SECONDS
    with _sessions_lock:
        stale = [sid for sid, s in _sessions.items() if s.last_used < cutoff]
    for sid in stale:
        close_session(sid)


def get_session(session_id: str) -> Session:
    with _sessions_lock:
        sess = _sessions.get(session_id)
    if sess is None:
        raise KeyError(session_id)
    sess.last_used = time.time()
    return sess


def create_session(source_path: Path) -> Session:
    _reap_idle()
    sid = uuid.uuid4().hex[:16]
    d = EDITOR_DIR / sid
    d.mkdir(parents=True, exist_ok=True)
    sess = Session(id=sid, source_path=source_path, dir=d)
    vid, v0 = sess.new_path()
    try:
        # always 16-bit PCM, mono or stereo (anything wider is downmixed)
        _run_ffmpeg(["-i", str(source_path), "-vn", "-af", "aformat=channel_layouts=mono|stereo",
                     "-c:a", "pcm_s16le", str(v0)])
        wav_info(v0)
    except Exception:
        shutil.rmtree(d, ignore_errors=True)
        raise
    sess.versions.append(Version(vid, v0, "Original"))
    sess.saved_version_id = vid
    with _sessions_lock:
        _sessions[sid] = sess
    return sess


def close_session(session_id: str) -> None:
    with _sessions_lock:
        sess = _sessions.pop(session_id, None)
    if sess:
        shutil.rmtree(sess.dir, ignore_errors=True)


# --------------------------------------------------------------------------
# peaks
# --------------------------------------------------------------------------

def peaks(sess: Session, start: float, end: float, buckets: int) -> dict:
    """Min/max per bucket per channel, scaled to -1..1, for drawing a waveform."""
    with sess.lock:
        path = sess.current.path
    with wave.open(str(path), "rb") as w:
        sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
        s0 = max(0, min(n, int(start * sr)))
        s1 = max(s0, min(n, int(end * sr)))
        total = s1 - s0
        buckets = max(1, min(buckets, total or 1))
        w.setpos(s0)
        out: list[list[float]] = [[] for _ in range(ch)]
        done = 0
        for i in range(buckets):
            count = (total * (i + 1)) // buckets - done
            done += count
            if count <= 0:
                for c in range(ch):
                    out[c].extend((0.0, 0.0))
                continue
            samples = array.array("h")
            samples.frombytes(w.readframes(count))
            if sys.byteorder == "big":
                samples.byteswap()
            for c in range(ch):
                chan = samples[c::ch]
                out[c].extend((round(min(chan) / 32768, 4), round(max(chan) / 32768, 4)))
    return {"start": s0 / sr, "end": s1 / sr, "buckets": buckets, "channels": ch, "peaks": out}


# --------------------------------------------------------------------------
# edits
# --------------------------------------------------------------------------

def _selection(start, end, duration: float) -> tuple[float, float]:
    if start is None or end is None:
        raise EditorError("Select a region first")
    s, e = sorted((float(start), float(end)))
    s, e = max(0.0, s), min(duration, e)
    if e - s < EPS:
        raise EditorError("Select a region first")
    return s, e


def _encode_args(out: Path, sr: int) -> list[str]:
    return ["-c:a", "pcm_s16le", "-ar", str(sr), str(out)]


def _trim_expr(start: float | None, end: float | None) -> str:
    parts = []
    if start is not None:
        parts.append(f"start={start:.6f}")
    if end is not None:
        parts.append(f"end={end:.6f}")
    return "atrim=" + ":".join(parts) + ",asetpts=N/SR/TB"


def _splice(cur: Path, out: Path, sr: int, channels: int, duration: float,
            keep_before: float, keep_after: float, middle: Path | None = None) -> None:
    """Rebuild `cur` as  [0, keep_before) + middle + [keep_after, end).
    Removing a region: keep_before=start, keep_after=end, no middle.
    Inserting at a point: keep_before == keep_after, middle = the new audio."""
    fmt = f"aformat=sample_rates={sr}:channel_layouts={_layout(channels)}"
    use_before = keep_before > EPS
    use_after = keep_after < duration - EPS
    n_split = int(use_before) + int(use_after)
    if n_split == 0 and middle is None:
        raise EditorError("That would remove the entire track")

    chains, pieces, inputs = [], [], [cur]
    labels = [f"s{i}" for i in range(n_split)]
    if n_split:
        chains.append(f"[0:a]asplit={n_split}" + "".join(f"[{l}]" for l in labels))
    idx = 0
    if use_before:
        chains.append(f"[{labels[idx]}]{_trim_expr(None, keep_before)},{fmt}[a]")
        pieces.append("[a]")
        idx += 1
    if middle is not None:
        inputs.append(middle)
        chains.append(f"[1:a]asetpts=N/SR/TB,{fmt}[m]")
        pieces.append("[m]")
    if use_after:
        chains.append(f"[{labels[idx]}]{_trim_expr(keep_after, None)},{fmt}[c]")
        pieces.append("[c]")

    if len(pieces) == 1:
        graph = ";".join(chains) + f";{pieces[0]}anull[out]"
    else:
        graph = ";".join(chains) + f";{''.join(pieces)}concat=n={len(pieces)}:v=0:a=1[out]"
    args = []
    for p in inputs:
        args += ["-i", str(p)]
    _run_ffmpeg([*args, "-filter_complex", graph, "-map", "[out]", *_encode_args(out, sr)])


def apply_edit(sess: Session, op: str, start=None, end=None, position=None, seconds=None) -> None:
    """op: trim (keep selection) | delete (remove selection) |
    insert_silence (at position) | trim_silence (auto, both ends)."""
    with sess.lock:
        cur = sess.current.path
        wi = wav_info(cur)
        sr, ch, dur = wi["sample_rate"], wi["channels"], wi["duration"]
        vid, out = sess.new_path()

        if op == "trim":
            s, e = _selection(start, end, dur)
            if s <= EPS and e >= dur - EPS:
                raise EditorError("The selection already covers the whole track")
            _run_ffmpeg(["-i", str(cur), "-af", _trim_expr(s, e), *_encode_args(out, sr)])
            label = "Keep selection"

        elif op == "delete":
            s, e = _selection(start, end, dur)
            _splice(cur, out, sr, ch, dur, s, e)
            label = "Remove selection"

        elif op == "insert_silence":
            length = max(0.01, min(MAX_INSERT_SILENCE, float(seconds or 1.0)))
            at = max(0.0, min(dur, float(position or 0.0)))
            sil = sess.dir / "silence.wav"
            try:
                _run_ffmpeg(["-f", "lavfi", "-i", f"anullsrc=r={sr}:cl={_layout(ch)}",
                             "-t", f"{length:.4f}", *_encode_args(sil, sr)])
                _splice(cur, out, sr, ch, dur, at, at, middle=sil)
            finally:
                sil.unlink(missing_ok=True)
            label = f"Add {length:g}s silence"

        elif op == "trim_silence":
            th = f"{AUTO_TRIM_THRESHOLD_DB}dB"
            one_end = f"silenceremove=start_periods=1:start_duration=0.02:start_threshold={th}"
            _run_ffmpeg(["-i", str(cur), "-af", f"{one_end},areverse,{one_end},areverse", *_encode_args(out, sr)])
            try:
                result = wav_info(out)["duration"]
            except Exception:  # noqa: BLE001  (empty output)
                result = 0.0
            if result < 0.05:
                out.unlink(missing_ok=True)
                raise EditorError("Nothing left after trimming — the track looks silent")
            if abs(result - dur) < EPS:
                out.unlink(missing_ok=True)
                raise EditorError("No silence found at the start or end")
            label = "Trim silence"

        else:
            raise EditorError(f"Unknown edit: {op}")

        sess.push(vid, out, label)


def undo(sess: Session) -> None:
    with sess.lock:
        if sess.index > 0:
            sess.index -= 1


def redo(sess: Session) -> None:
    with sess.lock:
        if sess.index < len(sess.versions) - 1:
            sess.index += 1


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------

_EXT_TO_FORMAT = {spec["ext"]: name for name, spec in AUDIO_CONVERT_FORMATS.items()}


def export(sess: Session, mode: str, fmt: str | None, bitrate: str | None, title: str | None) -> Path:
    """Encode the current version and write it into the library.

    mode "replace": overwrite the original file (same format, tags + cover kept).
    mode "new":     write a sibling file "<name> (edited).<ext>" in any format.
    """
    src = sess.source_path
    if not src.exists():
        raise EditorError("The original track no longer exists")

    if mode == "replace":
        fmt = _EXT_TO_FORMAT.get(src.suffix.lstrip(".").lower())
        if fmt is None:
            raise EditorError(f"Overwriting {src.suffix} files isn't supported — use \"Save as new copy\"")
    elif mode == "new":
        fmt = fmt or _EXT_TO_FORMAT.get(src.suffix.lstrip(".").lower()) or "mp3"
        if fmt not in AUDIO_CONVERT_FORMATS:
            raise EditorError(f"Unsupported format: {fmt}")
    else:
        raise EditorError("mode must be 'replace' or 'new'")

    spec = AUDIO_CONVERT_FORMATS[fmt]
    original_tags = metadata.read_tags(src)

    with sess.lock:
        cur = sess.current
        tmp = sess.dir / f"export.{spec['ext']}"
        args = ["-i", str(cur.path), "-vn", "-map_metadata", "-1", "-c:a", spec["acodec"]]
        if not spec.get("lossless"):
            if not bitrate:
                orig = original_tags.get("bitrate")
                bitrate = f"{min(max(int(orig / 1000), 96), 320)}k" if (mode == "replace" and orig) else spec["default_bitrate"]
            args += ["-b:a", bitrate]
        if fmt == "opus":
            args += ["-ar", "48000"]
        _run_ffmpeg([*args, str(tmp)])

        patch = {k: original_tags.get(k) for k in metadata.EASY_FIELDS}
        if mode == "new":
            patch["title"] = (title or "").strip() or f"{original_tags.get('title') or src.stem} (edited)"
        try:
            metadata.write_tags(tmp, patch)
        except Exception:  # noqa: BLE001  (e.g. wav has no tag support)
            pass
        art = metadata.read_art(src)
        if art:
            try:
                metadata.write_art(tmp, art)
            except Exception:  # noqa: BLE001
                pass

        if mode == "replace":
            dest = src
            tmp.replace(dest)
            sess.saved_version_id = cur.id
        else:
            dest = src.with_name(f"{src.stem} (edited).{spec['ext']}")
            n = 2
            while dest.exists():
                dest = src.with_name(f"{src.stem} (edited {n}).{spec['ext']}")
                n += 1
            shutil.move(str(tmp), str(dest))
        return dest
