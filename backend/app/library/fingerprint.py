"""Audio identity primitives for the Duplicates feature: a byte-exact hash
and a Chromaprint acoustic fingerprint, plus a local (no AcoustID server)
similarity score between two fingerprints. Shells out to the `fpcalc`
CLI (part of Chromaprint) the same way the rest of the codebase shells
out to ffmpeg/ffprobe — no extra Python package required."""

import hashlib
import json
import subprocess
from pathlib import Path

FPCALC = "fpcalc"
HASH_CHUNK_SIZE = 1 << 20
FINGERPRINT_MAX_LENGTH = 180   # seconds of audio fpcalc analyzes; plenty for one track


class FingerprintError(Exception):
    pass


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(HASH_CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_chromaprint(path: Path) -> tuple[float, list[int]]:
    """Returns (duration_seconds, raw_fingerprint_ints) via `fpcalc -raw`."""
    cmd = [FPCALC, "-raw", "-json", "-length", str(FINGERPRINT_MAX_LENGTH), str(path)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except FileNotFoundError:
        raise FingerprintError("fpcalc was not found on PATH")
    except subprocess.TimeoutExpired:
        raise FingerprintError("fpcalc timed out")
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-4:]
        raise FingerprintError("fpcalc failed: " + " | ".join(tail))
    try:
        data = json.loads(proc.stdout)
        duration = float(data["duration"])
        fp = [int(x) for x in str(data["fingerprint"]).split(",") if x.strip() != ""]
    except Exception as exc:  # noqa: BLE001
        raise FingerprintError(f"could not parse fpcalc output: {exc}")
    return duration, fp


def fingerprint_similarity(fp_a: list[int], fp_b: list[int], max_offset: int = 20) -> float:
    """Best-offset bit-match ratio between two raw Chromaprint fingerprints.
    ~1.0 means the same recording; low values mean unrelated audio. Trying
    a small range of offsets tolerates leading silence / trim differences
    between the two files without needing to time-align them first."""
    if not fp_a or not fp_b:
        return 0.0

    best = 0.0
    for offset in range(-max_offset, max_offset + 1):
        if offset >= 0:
            a, b = fp_a[offset:], fp_b
        else:
            a, b = fp_a, fp_b[-offset:]
        n = min(len(a), len(b))
        if n < 10:   # too short an overlap to mean anything
            continue
        mismatched_bits = sum((a[i] ^ b[i]).bit_count() for i in range(n))
        similarity = 1.0 - (mismatched_bits / (n * 32))
        if similarity > best:
            best = similarity
    return max(0.0, best)
