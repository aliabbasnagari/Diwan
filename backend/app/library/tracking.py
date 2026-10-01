from pathlib import Path

from sqlalchemy.orm import Session

from ..models import Download, ConversionJob
from . import organizer


def _same(a: str | None, b: Path) -> bool:
    if not a:
        return False
    try:
        return Path(a).resolve() == b.resolve()
    except OSError:
        return False


def sync_moved_path(db: Session, old_path: Path, new_path: Path, library_dir: Path) -> None:
    """Point spooler/convert history rows at a library file's new location
    after it has been moved, so they keep showing it as available."""
    old_path, new_path = Path(old_path), Path(new_path)
    if old_path.resolve() == new_path.resolve():
        return

    new_rel = organizer.relative_to_library(new_path, library_dir)

    for row in db.query(Download).filter(Download.filepath.isnot(None)).all():
        if _same(row.filepath, old_path):
            row.filepath = str(new_path)
            row.library_path = new_rel

    for row in db.query(ConversionJob).filter(ConversionJob.output_path.isnot(None)).all():
        if _same(row.output_path, old_path):
            row.output_path = str(new_path)
            row.library_path = new_rel

    db.commit()
