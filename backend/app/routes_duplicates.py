import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .database import get_db
from .config import DUPLICATE_TRASH_DIRNAME
from .models import DuplicateGroup, DuplicateGroupMember, DuplicateGroupStatus
from .schemas import DuplicateResolveRequest, DuplicateTrashPathRequest
from . import dedup_scanner, settings_service
from .library import scanner, tracking

router = APIRouter(prefix="/api/duplicates", tags=["duplicates"])


def _lib_dir(db: Session) -> Path:
    path = settings_service.library_dir(db)
    db.rollback()
    return path


@router.post("/scan")
def start_scan():
    return dedup_scanner.trigger_scan()


@router.get("/scan/status")
def scan_status():
    return dedup_scanner.latest_job_dict() or {}


@router.post("/scan/cancel")
def cancel_scan():
    cancelled = dedup_scanner.cancel_active_scan()
    if not cancelled:
        raise HTTPException(status_code=400, detail="No scan is currently running")
    return {"cancelled": True}


@router.get("/groups")
def list_groups(
    category: Optional[str] = Query(default=None),
    status: str = Query(default="pending"),
    db: Session = Depends(get_db),
):
    q = db.query(DuplicateGroup).filter(DuplicateGroup.status == status)
    if category:
        q = q.filter(DuplicateGroup.category == category)
    groups = q.order_by(DuplicateGroup.created_at.desc()).all()

    group_ids = [g.id for g in groups]
    members_by_group: dict[int, list[DuplicateGroupMember]] = {}
    if group_ids:
        for m in db.query(DuplicateGroupMember).filter(DuplicateGroupMember.group_id.in_(group_ids)).all():
            members_by_group.setdefault(m.group_id, []).append(m)

    results = []
    for g in groups:
        d = g.to_dict()
        members = []
        for m in members_by_group.get(g.id, []):
            md = m.to_dict()
            md["track_id"] = scanner.encode_id(m.path)
            members.append(md)
        d["members"] = members
        results.append(d)
    return results


@router.post("/groups/{group_id}/resolve")
def resolve_group(group_id: int, req: DuplicateResolveRequest, db: Session = Depends(get_db)):
    group = db.get(DuplicateGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Not found")
    if group.status != DuplicateGroupStatus.PENDING:
        raise HTTPException(status_code=400, detail="This group was already resolved or ignored")
    try:
        result = dedup_scanner.resolve_group(db, group, req.keep_paths, _lib_dir(db))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not quarantine file(s): {exc}")
    return result


@router.post("/groups/{group_id}/ignore")
def ignore_group(group_id: int, db: Session = Depends(get_db)):
    group = db.get(DuplicateGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="Not found")
    if group.status != DuplicateGroupStatus.PENDING:
        raise HTTPException(status_code=400, detail="This group was already resolved or ignored")
    dedup_scanner.ignore_group(db, group)
    return {"ignored": True}


# --- quarantine ("duplicates trash") management ---

@router.get("/trash")
def list_trash(db: Session = Depends(get_db)):
    trash_dir = _lib_dir(db) / DUPLICATE_TRASH_DIRNAME
    if not trash_dir.is_dir():
        return []
    items = []
    for path in sorted(trash_dir.rglob("*")):
        if path.is_file():
            rel = str(path.relative_to(trash_dir))
            stat = path.stat()
            items.append({"path": rel, "filename": path.name, "filesize": stat.st_size, "modified_at": stat.st_mtime})
    return items


@router.post("/trash/restore")
def restore_trash(req: DuplicateTrashPathRequest, db: Session = Depends(get_db)):
    lib = _lib_dir(db)
    trash_dir = lib / DUPLICATE_TRASH_DIRNAME
    src = (trash_dir / req.path).resolve()
    if trash_dir.resolve() not in src.parents or not src.is_file():
        raise HTTPException(status_code=404, detail="File not found in trash")

    dest = lib / req.path
    dest.parent.mkdir(parents=True, exist_ok=True)
    counter = 2
    base_dest = dest
    while dest.exists():
        dest = base_dest.with_name(f"{base_dest.stem} ({counter}){base_dest.suffix}")
        counter += 1

    shutil.move(str(src), str(dest))
    tracking.sync_moved_path(db, src, dest, lib)
    dedup_scanner.cleanup_empty_dirs(src.parent, trash_dir)
    return {"restored": True}


@router.delete("/trash")
def delete_trash_item(path: str = Query(...), db: Session = Depends(get_db)):
    trash_dir = _lib_dir(db) / DUPLICATE_TRASH_DIRNAME
    target = (trash_dir / path).resolve()
    if trash_dir.resolve() not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found in trash")
    target.unlink()
    dedup_scanner.cleanup_empty_dirs(target.parent, trash_dir)
    return {"deleted": True}


@router.post("/trash/empty")
def empty_trash(db: Session = Depends(get_db)):
    trash_dir = _lib_dir(db) / DUPLICATE_TRASH_DIRNAME
    if not trash_dir.is_dir():
        return {"deleted": 0}
    count = 0
    for path in list(trash_dir.rglob("*")):
        if path.is_file():
            path.unlink()
            count += 1
    for path in sorted(trash_dir.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass
    return {"deleted": count}
