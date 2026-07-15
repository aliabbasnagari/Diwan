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