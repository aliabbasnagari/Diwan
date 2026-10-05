import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .database import get_db
from .schemas import EditorSessionCreate, EditorEditRequest, EditorSaveRequest
from . import audio_editor, navidrome, settings_service
from .audio_editor import EditorError
from .config import AUDIO_BITRATES, AUDIO_CONVERT_FORMATS
from .library import scanner

router = APIRouter(prefix="/api/editor", tags=["editor"])


def _session(session_id: str) -> audio_editor.Session:
    try:
        return audio_editor.get_session(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Editing session expired — reopen the track")


def _guard(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except EditorError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/options")
def editor_options():
    return {
        "formats": {k: {"lossless": v.get("lossless", False)} for k, v in AUDIO_CONVERT_FORMATS.items()},
        "bitrates": AUDIO_BITRATES,
    }


@router.post("/sessions")
def create_session(req: EditorSessionCreate, db: Session = Depends(get_db)):
    lib = settings_service.library_dir(db)
    db.rollback()
    try:
        path = scanner.resolve_track_path(lib, req.track_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid track id")
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Track not found")
    sess = _guard(audio_editor.create_session, path)
    return sess.info()


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    return _session(session_id).info()


@router.delete("/sessions/{session_id}")
def close_session(session_id: str):
    audio_editor.close_session(session_id)
    return {"closed": True}


@router.get("/sessions/{session_id}/audio")
def session_audio(session_id: str):
    sess = _session(session_id)
    return FileResponse(sess.current.path, media_type="audio/wav", headers={"Cache-Control": "no-store"})


@router.get("/sessions/{session_id}/peaks")
def session_peaks(
    session_id: str,
    start: float = Query(0.0, ge=0),
    end: float = Query(...),
    buckets: int = Query(1000, ge=1, le=8000),
):
    return _guard(audio_editor.peaks, _session(session_id), start, end, buckets)


@router.post("/sessions/{session_id}/edit")
def apply_edit(session_id: str, req: EditorEditRequest):
    sess = _session(session_id)
    _guard(audio_editor.apply_edit, sess, req.op, req.start, req.end, req.position, req.seconds)
    return sess.info()


@router.post("/sessions/{session_id}/undo")
def undo(session_id: str):
    sess = _session(session_id)
    audio_editor.undo(sess)
    return sess.info()


@router.post("/sessions/{session_id}/redo")
def redo(session_id: str):
    sess = _session(session_id)
    audio_editor.redo(sess)
    return sess.info()


@router.post("/sessions/{session_id}/save")
def save(session_id: str, req: EditorSaveRequest, db: Session = Depends(get_db)):
    sess = _session(session_id)
    lib = settings_service.library_dir(db)
    s = settings_service.get_settings(db)
    scan = (s.navidrome_url, s.navidrome_username or "", s.navidrome_password or "") if s.navidrome_auto_scan and s.navidrome_url else None
    db.rollback()

    dest = _guard(audio_editor.export, sess, req.mode, req.format, req.bitrate, req.title)

    if scan:
        try:
            asyncio.run(navidrome.start_scan(*scan))
        except Exception:  # noqa: BLE001  (best-effort, as in the spooler)
            pass
    return {"track": scanner.track_summary(lib, dest), "session": sess.info()}
