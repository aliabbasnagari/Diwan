"""Audacity-style audio editing on top of ffmpeg.

An editing *session* decodes a library track into a working 16-bit PCM WAV
and then keeps a stack of versions — every edit (trim, cut, an effect, ...)
renders the current version into a new file, so undo/redo is just moving a
pointer. Nothing touches the library file until ``export`` is called.

Effects are declared once in ``EFFECTS`` (parameter ranges included); the
frontend renders its forms from that list, and the same ranges are used to
clamp whatever the client sends before it is turned into an ffmpeg filter.
"""
import array
import re
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
MAX_UNDO_DEPTH = 20
SESSION_IDLE_SECONDS = 6 * 3600
PREVIEW_SECONDS = 12.0
EPS = 0.001


class EditorError(Exception):
    """A problem with the request itself (bad range, unsupported effect, ...)."""


# --------------------------------------------------------------------------
# ffmpeg helpers
# --------------------------------------------------------------------------

def _run_ffmpeg(args: list[str], timeout: int = 900) -> str:
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
    return proc.stderr or ""


def _layout(channels: int) -> str:
    return "mono" if channels == 1 else "stereo"


def wav_info(path: Path) -> dict:
    with wave.open(str(path), "rb") as w:
        sr, ch, n = w.getframerate(), w.getnchannels(), w.getnframes()
    return {"sample_rate": sr, "channels": ch, "frames": n, "duration": n / sr if sr else 0.0}


def _peak_db(path: Path, start: float, duration: float) -> float | None:
    """Loudest sample (dBFS) in a range, via ffmpeg's volumedetect."""
    stderr = _run_ffmpeg(["-ss", f"{start:.6f}", "-t", f"{duration:.6f}", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"])
    m = re.search(r"max_volume:\s*(-?[\d.]+|-inf)\s*dB", stderr)
    if not m or m.group(1) == "-inf":
        return None
    return float(m.group(1))


# --------------------------------------------------------------------------
# effect catalogue
# --------------------------------------------------------------------------

def num(key, label, default, lo, hi, step=None, unit=""):
    return {"key": key, "label": label, "type": "number", "default": default, "min": lo, "max": hi,
            "step": step if step is not None else (hi - lo) / 100, "unit": unit}


def _lin(db: float) -> float:
    return 10 ** (db / 20)


def _atempo_chain(factor: float) -> str:
    """atempo only accepts 0.5–2.0 per instance, so chain for wider ranges."""
    parts = []
    while factor > 2.0:
        parts.append(2.0)
        factor /= 2.0
    while factor < 0.5:
        parts.append(0.5)
        factor /= 0.5
    parts.append(factor)
    return ",".join(f"atempo={p:.5f}" for p in parts)


@dataclass
class Ctx:
    sr: int
    channels: int
    seg_dur: float          # length of the audio the filter will see (seconds)
    path: Path              # current version, for effects that analyse first
    start: float            # selection start within `path`
    end: float


def _normalize(p, ctx: Ctx) -> str:
    peak = _peak_db(ctx.path, ctx.start, ctx.end - ctx.start)
    if peak is None:
        return "anull"
    return f"volume={p['target'] - peak:.3f}dB"


def _fade_in(p, ctx: Ctx) -> str:
    d = min(p["seconds"], ctx.seg_dur)
    return f"afade=t=in:st=0:d={d:.4f}:curve={p['curve']}"


def _fade_out(p, ctx: Ctx) -> str:
    d = min(p["seconds"], ctx.seg_dur)
    return f"afade=t=out:st={max(ctx.seg_dur - d, 0):.4f}:d={d:.4f}:curve={p['curve']}"


def _invert(p, ctx: Ctx) -> str:
    return "aeval=" + "|".join(f"-val({i})" for i in range(ctx.channels)) + ":c=same"


def _reverb(p, ctx: Ctx) -> str:
    scale = 0.4 + 1.2 * p["room"]
    delays = "|".join(f"{d * scale:.1f}" for d in (37, 71, 113, 151))
    decays = "|".join(f"{g * p['wet']:.3f}" for g in (0.6, 0.5, 0.4, 0.3))
    return f"aecho=in_gain=0.85:out_gain=0.85:delays={delays}:decays={decays}"


def _balance(p, ctx: Ctx) -> str:
    b = p["balance"]
    return f"pan=stereo|c0={min(1.0, 1 - b):.3f}*c0|c1={min(1.0, 1 + b):.3f}*c1"


def _silence_remove(p, ctx: Ctx) -> str:
    th = f"{p['threshold']:.1f}dB"
    return (f"silenceremove=start_periods=1:start_duration=0.05:start_threshold={th}"
            f":stop_periods=-1:stop_duration={p['min_silence']:.2f}:stop_threshold={th}")


CURVES = ["tri", "qsin", "hsin", "log", "exp"]

# group, label and params are for the UI; `build` produces the ffmpeg filter
# chain for the selected audio. Flags: whole_only (changes the channel layout,
# so selections can't apply), stereo_only, needs_selection, preview_tail
# (preview the end of a long selection instead of the start).
EFFECTS: dict[str, dict] = {
    # --- volume / dynamics ---
    "amplify": {"group": "Volume", "label": "Amplify", "params": [num("gain", "Gain", 6, -40, 40, 0.5, "dB")],
                "build": lambda p, c: f"volume={p['gain']:.3f}dB"},
    "normalize": {"group": "Volume", "label": "Normalize (peak)", "params": [num("target", "Peak level", -1, -30, 0, 0.5, "dB")],
                  "build": _normalize},
    "loudnorm": {"group": "Volume", "label": "Loudness normalize", "params": [num("lufs", "Target loudness", -14, -30, -5, 0.5, "LUFS")],
                 "build": lambda p, c: f"loudnorm=I={p['lufs']:.1f}:TP=-1.5:LRA=11"},
    "fade_in": {"group": "Volume", "label": "Fade in", "params": [num("seconds", "Length", 3, 0.05, 60, 0.05, "s"),
                {"key": "curve", "label": "Curve", "type": "select", "default": "tri", "options": CURVES}],
                "build": _fade_in},
    "fade_out": {"group": "Volume", "label": "Fade out", "preview_tail": True,
                 "params": [num("seconds", "Length", 3, 0.05, 60, 0.05, "s"),
                            {"key": "curve", "label": "Curve", "type": "select", "default": "tri", "options": CURVES}],
                 "build": _fade_out},
    "compressor": {"group": "Volume", "label": "Compressor", "params": [
        num("threshold", "Threshold", -18, -60, 0, 1, "dB"), num("ratio", "Ratio", 4, 1, 20, 0.5, ":1"),
        num("attack", "Attack", 20, 0.1, 500, 1, "ms"), num("release", "Release", 250, 10, 3000, 10, "ms"),
        num("makeup", "Make-up gain", 0, 0, 24, 0.5, "dB")],
        "build": lambda p, c: (f"acompressor=threshold={_lin(p['threshold']):.5f}:ratio={p['ratio']:.2f}"
                               f":attack={p['attack']:.1f}:release={p['release']:.1f}:makeup={_lin(p['makeup']):.3f}")},
    "limiter": {"group": "Volume", "label": "Limiter", "params": [num("ceiling", "Ceiling", -1, -24, 0, 0.5, "dB")],
                "build": lambda p, c: f"alimiter=limit={max(_lin(p['ceiling']), 0.0625):.4f}:level=0"},
    "noise_gate": {"group": "Volume", "label": "Noise gate", "params": [
        num("threshold", "Threshold", -45, -80, -10, 1, "dB"), num("ratio", "Ratio", 6, 1, 20, 0.5, ":1")],
        "build": lambda p, c: f"agate=threshold={_lin(p['threshold']):.5f}:ratio={p['ratio']:.2f}"},
    "invert": {"group": "Volume", "label": "Invert polarity", "params": [], "build": _invert},
    "silence": {"group": "Volume", "label": "Silence selection", "needs_selection": True, "params": [],
                "build": lambda p, c: "volume=0"},

    # --- EQ / filters ---
    "bass": {"group": "EQ & filters", "label": "Bass boost / cut", "params": [
        num("gain", "Gain", 6, -20, 20, 0.5, "dB"), num("freq", "Frequency", 100, 20, 500, 5, "Hz")],
        "build": lambda p, c: f"bass=g={p['gain']:.2f}:f={p['freq']:.0f}"},
    "treble": {"group": "EQ & filters", "label": "Treble boost / cut", "params": [
        num("gain", "Gain", 6, -20, 20, 0.5, "dB"), num("freq", "Frequency", 3000, 1000, 16000, 100, "Hz")],
        "build": lambda p, c: f"treble=g={p['gain']:.2f}:f={p['freq']:.0f}"},
    "equalizer": {"group": "EQ & filters", "label": "Parametric EQ band", "params": [
        num("freq", "Frequency", 1000, 20, 20000, 10, "Hz"), num("q", "Q (width)", 1, 0.1, 10, 0.1),
        num("gain", "Gain", 4, -20, 20, 0.5, "dB")],
        "build": lambda p, c: f"equalizer=f={p['freq']:.0f}:t=q:w={p['q']:.2f}:g={p['gain']:.2f}"},
    "highpass": {"group": "EQ & filters", "label": "High-pass filter", "params": [num("freq", "Cutoff", 80, 20, 5000, 5, "Hz")],
                 "build": lambda p, c: f"highpass=f={p['freq']:.0f}"},
    "lowpass": {"group": "EQ & filters", "label": "Low-pass filter", "params": [num("freq", "Cutoff", 8000, 200, 20000, 50, "Hz")],
                "build": lambda p, c: f"lowpass=f={p['freq']:.0f}"},
    "noise_reduction": {"group": "EQ & filters", "label": "Noise reduction", "params": [
        num("reduction", "Reduction", 12, 1, 60, 1, "dB"), num("floor", "Noise floor", -50, -80, -20, 1, "dB")],
        "build": lambda p, c: f"afftdn=nr={p['reduction']:.1f}:nf={p['floor']:.1f}"},
    "remove_silence": {"group": "EQ & filters", "label": "Remove silences", "params": [
        num("threshold", "Threshold", -50, -80, -10, 1, "dB"), num("min_silence", "Min. silence", 0.5, 0.1, 5, 0.1, "s")],
        "build": _silence_remove},

    # --- time & pitch ---
    "speed": {"group": "Time & pitch", "label": "Change speed (tape-style)", "params": [num("factor", "Speed", 1.25, 0.25, 4, 0.05, "×")],
              "build": lambda p, c: f"asetrate={int(round(c.sr * p['factor']))},aresample={c.sr}"},
    "tempo": {"group": "Time & pitch", "label": "Change tempo (keep pitch)", "params": [num("factor", "Tempo", 1.25, 0.25, 4, 0.05, "×")],
              "build": lambda p, c: _atempo_chain(p["factor"])},
    "pitch": {"group": "Time & pitch", "label": "Change pitch (keep tempo)", "params": [num("semitones", "Shift", 2, -12, 12, 0.5, "st")],
              "build": lambda p, c: (lambda r: f"asetrate={int(round(c.sr * r))},aresample={c.sr},{_atempo_chain(1 / r)}")(2 ** (p["semitones"] / 12))},
    "reverse": {"group": "Time & pitch", "label": "Reverse", "params": [], "build": lambda p, c: "areverse"},

    # --- modulation / space ---
    "echo": {"group": "Effects", "label": "Echo", "params": [
        num("delay", "Delay", 400, 20, 2000, 10, "ms"), num("decay", "Decay", 0.45, 0.05, 0.95, 0.05)],
        "build": lambda p, c: f"aecho=0.8:0.9:{p['delay']:.0f}:{p['decay']:.2f}"},
    "reverb": {"group": "Effects", "label": "Reverb (simple)", "params": [
        num("room", "Room size", 0.5, 0, 1, 0.05), num("wet", "Wet level", 0.6, 0.1, 1, 0.05)],
        "build": _reverb},
    "chorus": {"group": "Effects", "label": "Chorus", "params": [],
               "build": lambda p, c: "chorus=0.5:0.9:50|60:0.4|0.32:0.25|0.4:2|1.3"},
    "flanger": {"group": "Effects", "label": "Flanger", "params": [
        num("speed", "Speed", 0.5, 0.1, 5, 0.1, "Hz"), num("depth", "Depth", 2, 0, 10, 0.5, "ms")],
        "build": lambda p, c: f"flanger=speed={p['speed']:.2f}:depth={p['depth']:.1f}"},
    "phaser": {"group": "Effects", "label": "Phaser", "params": [num("speed", "Speed", 0.5, 0.1, 5, 0.1, "Hz")],
               "build": lambda p, c: f"aphaser=speed={p['speed']:.2f}"},
    "tremolo": {"group": "Effects", "label": "Tremolo", "params": [
        num("freq", "Rate", 5, 0.5, 20, 0.5, "Hz"), num("depth", "Depth", 0.5, 0.05, 1, 0.05)],
        "build": lambda p, c: f"tremolo=f={p['freq']:.2f}:d={p['depth']:.2f}"},
    "vibrato": {"group": "Effects", "label": "Vibrato", "params": [
        num("freq", "Rate", 5, 0.5, 20, 0.5, "Hz"), num("depth", "Depth", 0.5, 0.05, 1, 0.05)],
        "build": lambda p, c: f"vibrato=f={p['freq']:.2f}:d={p['depth']:.2f}"},

    # --- stereo ---
    "balance": {"group": "Stereo", "label": "Balance (L / R)", "stereo_only": True,
                "params": [num("balance", "Balance", 0, -1, 1, 0.05)], "build": _balance},
    "swap_channels": {"group": "Stereo", "label": "Swap left / right", "stereo_only": True, "params": [],
                      "build": lambda p, c: "pan=stereo|c0=c1|c1=c0"},
    "vocal_reduce": {"group": "Stereo", "label": "Vocal reduction", "stereo_only": True, "params": [],
                     "build": lambda p, c: "pan=stereo|c0=0.5*c0-0.5*c1|c1=0.5*c1-0.5*c0"},
    "to_mono": {"group": "Stereo", "label": "Convert to mono", "stereo_only": True, "whole_only": True, "params": [],
                "build": lambda p, c: "pan=mono|c0=0.5*c0+0.5*c1"},
}


def effect_catalogue() -> list[dict]:
    return [{
        "name": name,
        "group": spec["group"],
        "label": spec["label"],
        "params": spec["params"],
        "whole_only": bool(spec.get("whole_only")),
        "stereo_only": bool(spec.get("stereo_only")),
        "needs_selection": bool(spec.get("needs_selection")),
    } for name, spec in EFFECTS.items()]


def _resolve_params(spec: dict, raw: dict | None) -> dict:
    raw = raw or {}
    out = {}
    for p in spec["params"]:
        if p["type"] == "select":
            v = raw.get(p["key"], p["default"])
            out[p["key"]] = v if v in p["options"] else p["default"]
        else:
            try:
                v = float(raw.get(p["key"], p["default"]))
            except (TypeError, ValueError):
                v = p["default"]
            out[p["key"]] = max(p["min"], min(p["max"], v))
    return out


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
    clipboard: Path | None = None
    clipboard_seconds: float = 0.0
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
            "clipboard_seconds": self.clipboard_seconds if self.clipboard else 0.0,
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

def _range(start, end, duration: float, required: bool) -> tuple[float | None, float | None]:
    """Normalise a selection. Returns (None, None) for "whole track"."""
    if start is None or end is None or abs(end - start) < EPS:
        if required:
            raise EditorError("Select a region of the waveform first")
        return None, None
    s, e = sorted((float(start), float(end)))
    s, e = max(0.0, s), min(duration, e)
    if e - s < EPS:
        if required:
            raise EditorError("Select a region of the waveform first")
        return None, None
    if not required and s <= EPS and e >= duration - EPS:
        return None, None
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


def _concat_render(inputs: list[Path], graph: str, out_label: str, out: Path, sr: int) -> None:
    args = []
    for p in inputs:
        args += ["-i", str(p)]
    _run_ffmpeg([*args, "-filter_complex", graph, "-map", f"[{out_label}]", *_encode_args(out, sr)])


def _splice(cur: Path, out: Path, info: dict, keep_before: float | None, keep_after: float | None,
            middle: Path | None = None) -> None:
    """Rebuild `cur` as  [0, keep_before) + middle + [keep_after, end)  — used by
    delete (no middle), paste/insert (middle, keep_before == keep_after)."""
    sr, ch = info["sr"], info["channels"]
    fmt = f"aformat=sample_rates={sr}:channel_layouts={_layout(ch)}"
    pieces, chains = [], []
    use_before = keep_before is not None and keep_before > EPS
    use_after = keep_after is not None and keep_after < info["duration"] - EPS
    n_split = int(use_before) + int(use_after)
    if n_split == 0 and middle is None:
        raise EditorError("That would remove the entire track")

    labels = [f"s{i}" for i in range(n_split)]
    if n_split:
        chains.append(f"[0:a]asplit={n_split}" + "".join(f"[{l}]" for l in labels))
    idx = 0
    if use_before:
        chains.append(f"[{labels[idx]}]{_trim_expr(None, keep_before)},{fmt}[a]")
        pieces.append("[a]")
        idx += 1
    inputs = [cur]
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
    _concat_render(inputs, graph, "out", out, sr)


def _apply_filter(cur: Path, out: Path, info: dict, start: float | None, end: float | None, flt: str) -> None:
    sr, ch = info["sr"], info["channels"]
    if start is None:
        _run_ffmpeg(["-i", str(cur), "-af", flt, *_encode_args(out, sr)])
        return
    fmt = f"aformat=sample_rates={sr}:channel_layouts={_layout(ch)}"
    use_before, use_after = start > EPS, end < info["duration"] - EPS
    n = 1 + int(use_before) + int(use_after)
    labels = [f"s{i}" for i in range(n)]
    chains = [f"[0:a]asplit={n}" + "".join(f"[{l}]" for l in labels)]
    pieces, idx = [], 0
    if use_before:
        chains.append(f"[{labels[idx]}]{_trim_expr(None, start)},{fmt}[a]")
        pieces.append("[a]")
        idx += 1
    chains.append(f"[{labels[idx]}]{_trim_expr(start, end)},{flt},{fmt}[b]")
    pieces.append("[b]")
    idx += 1
    if use_after:
        chains.append(f"[{labels[idx]}]{_trim_expr(end, None)},{fmt}[c]")
        pieces.append("[c]")
    graph = ";".join(chains) + f";{''.join(pieces)}concat=n={len(pieces)}:v=0:a=1[out]"
    _concat_render([cur], graph, "out", out, sr)


def _info(sess: Session) -> dict:
    wi = wav_info(sess.current.path)
    return {"sr": wi["sample_rate"], "channels": wi["channels"], "duration": wi["duration"]}


def apply_effect(sess: Session, name: str, params: dict | None, start, end) -> None:
    spec = EFFECTS.get(name)
    if spec is None:
        raise EditorError(f"Unknown effect: {name}")
    with sess.lock:
        info = _info(sess)
        if spec.get("stereo_only") and info["channels"] != 2:
            raise EditorError(f"{spec['label']} needs a stereo track")
        s, e = _range(start, end, info["duration"], bool(spec.get("needs_selection")))
        if spec.get("whole_only"):
            s = e = None
        ctx = _ctx(sess, info, s, e)
        flt = spec["build"](_resolve_params(spec, params), ctx)
        vid, out = sess.new_path()
        _apply_filter(sess.current.path, out, info, s, e, flt)
        sess.push(vid, out, spec["label"])


def _ctx(sess: Session, info: dict, s, e) -> Ctx:
    s0, e0 = (0.0, info["duration"]) if s is None else (s, e)
    return Ctx(sr=info["sr"], channels=info["channels"], seg_dur=e0 - s0, path=sess.current.path, start=s0, end=e0)


def preview_effect(sess: Session, name: str, params: dict | None, start, end) -> Path:
    """Render a short sample of the effect (not stored as a version)."""
    spec = EFFECTS.get(name)
    if spec is None:
        raise EditorError(f"Unknown effect: {name}")
    with sess.lock:
        info = _info(sess)
        if spec.get("stereo_only") and info["channels"] != 2:
            raise EditorError(f"{spec['label']} needs a stereo track")
        s, e = _range(start, end, info["duration"], bool(spec.get("needs_selection")))
        if spec.get("whole_only"):
            s = e = None
        full = _ctx(sess, info, s, e)
        flt = spec["build"](_resolve_params(spec, params), full)
        # preview a short slice; fades are computed against the slice, so for
        # fade-outs take the tail of the selection instead of its head
        length = min(full.seg_dur, PREVIEW_SECONDS)
        offset = full.end - length if spec.get("preview_tail") else full.start
        if length < full.seg_dur:
            flt = spec["build"](_resolve_params(spec, params), Ctx(
                sr=full.sr, channels=full.channels, seg_dur=length, path=full.path, start=full.start, end=full.end))
        out = sess.dir / "preview.wav"
        _run_ffmpeg(["-ss", f"{offset:.6f}", "-t", f"{length:.6f}", "-i", str(sess.current.path), "-af", flt,
                     *_encode_args(out, info["sr"])])
        return out


def _copy_to_clipboard(sess: Session, cur: Path, info: dict, s: float, e: float) -> None:
    clip = sess.dir / "clipboard.wav"
    _run_ffmpeg(["-ss", f"{s:.6f}", "-t", f"{e - s:.6f}", "-i", str(cur), *_encode_args(clip, info["sr"])])
    sess.clipboard, sess.clipboard_seconds = clip, e - s


def apply_edit(sess: Session, op: str, start=None, end=None, position=None, seconds=None) -> None:
    with sess.lock:
        info = _info(sess)
        cur, dur = sess.current.path, info["duration"]

        if op == "copy":
            s, e = _range(start, end, dur, True)
            _copy_to_clipboard(sess, cur, info, s, e)
            return

        vid, out = sess.new_path()

        if op == "trim":
            s, e = _range(start, end, dur, True)
            _run_ffmpeg(["-i", str(cur), "-af", _trim_expr(s, e), *_encode_args(out, info["sr"])])
            sess.push(vid, out, "Trim to selection")

        elif op in ("delete", "cut"):
            s, e = _range(start, end, dur, True)
            if op == "cut":
                _copy_to_clipboard(sess, cur, info, s, e)
            _splice(cur, out, info, s, e)
            sess.push(vid, out, "Cut" if op == "cut" else "Delete selection")

        elif op == "paste":
            if not sess.clipboard or not sess.clipboard.exists():
                raise EditorError("The clipboard is empty")
            at = max(0.0, min(dur, float(position or 0.0)))
            _splice(cur, out, info, at, at, middle=sess.clipboard)
            sess.push(vid, out, "Paste")

        elif op == "insert_silence":
            length = max(0.01, min(600.0, float(seconds or 1.0)))
            at = max(0.0, min(dur, float(position or 0.0)))
            sil = sess.dir / "silence.wav"
            _run_ffmpeg(["-f", "lavfi", "-i", f"anullsrc=r={info['sr']}:cl={_layout(info['channels'])}",
                         "-t", f"{length:.4f}", *_encode_args(sil, info["sr"])])
            _splice(cur, out, info, at, at, middle=sil)
            sil.unlink(missing_ok=True)
            sess.push(vid, out, "Insert silence")

        else:
            raise EditorError(f"Unknown edit: {op}")


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

_EXT_TO_FORMAT = {f"{spec['ext']}": name for name, spec in AUDIO_CONVERT_FORMATS.items()}


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
        else:
            dest = src.with_name(f"{src.stem} (edited).{spec['ext']}")
            n = 2
            while dest.exists():
                dest = src.with_name(f"{src.stem} (edited {n}).{spec['ext']}")
                n += 1
            shutil.move(str(tmp), str(dest))

        if mode == "replace":
            sess.saved_version_id = cur.id
        return dest
