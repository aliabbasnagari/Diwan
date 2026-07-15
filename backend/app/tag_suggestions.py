from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from .models import TagSuggestion

FIELD_MAP = {
    "artist": "tag_artist",
    "album_artist": "tag_album_artist",
    "album": "tag_album",
    "genre": "tag_genre",
    "year": "tag_year",
}


def record_tags(db: Session, **field_values: Optional[str]):
    """field_values keys should match FIELD_MAP keys, e.g. record_tags(db, artist='X', album='Y')"""
    for field, value in field_values.items():
        if not value:
            continue
        value = str(value).strip()
        if not value:
            continue
        existing = (
            db.query(TagSuggestion)
            .filter(TagSuggestion.field == field, TagSuggestion.value == value)
            .first()
        )
        if existing:
            existing.use_count += 1
            existing.last_used_at = datetime.utcnow()
        else:
            db.add(TagSuggestion(field=field, value=value, use_count=1))
    db.commit()


def get_suggestions(db: Session, field: str, limit: int = 30):
    rows = (
        db.query(TagSuggestion)
        .filter(TagSuggestion.field == field)
        .order_by(TagSuggestion.use_count.desc(), TagSuggestion.last_used_at.desc())
        .limit(limit)
        .all()
    )
    return [r.value for r in rows]


def populate_suggestions(db: Session, library_dir) -> dict:
    """Scan every audio file in the library and insert missing tag suggestions.
    Existing suggestions are left unchanged; their use_count is NOT modified.
    """
    from pathlib import Path
    from .library import scanner, metadata

    lib = Path(library_dir)
    added, scanned = 0, 0

    TAG_TO_FIELD = {
        "artist": "artist",
        "albumartist": "album_artist",
        "album": "album",
        "genre": "genre",
        "date": "year",
    }

    # Pre-load existing suggestions into a lookup to avoid duplicates.
    existing_rows = db.query(TagSuggestion).all()
    seen = {(row.field, row.value): row for row in existing_rows}

    for path in scanner._scan_files(lib):
        scanned += 1
        try:
            tags = metadata.read_tags(path)
        except Exception:
            continue

        for tag_key, field in TAG_TO_FIELD.items():
            raw = tags.get(tag_key)
            if not raw:
                continue

            # artist and albumartist may contain comma-separated values.
            if tag_key in ("artist", "albumartist"):
                values = [v.strip() for v in str(raw).split(",") if v.strip()]
            else:
                value = str(raw).strip()
                values = [value] if value else []

            for value in values:
                key = (field, value)

                if key in seen:
                    continue

                new_row = TagSuggestion(
                    field=field,
                    value=value,
                    use_count=1,
                )

                db.add(new_row)
                seen[key] = new_row
                added += 1

    db.commit()

    return {
        "scanned": scanned,
        "added": added,
    }