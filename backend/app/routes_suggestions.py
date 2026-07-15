from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from .database import get_db
from .models import TagSuggestion
from . import downloader
from . import tag_suggestions
from . import settings_service
from .auth import require_admin

router = APIRouter(prefix="/api/suggestions", tags=["suggestions"])

@router.get("")
def suggestions(db: Session = Depends(get_db)):
    return {
        field: tag_suggestions.get_suggestions(db, field)
        for field in tag_suggestions.FIELD_MAP
    }

@router.get("/all")
def all_suggestions(db: Session = Depends(get_db)):
    """Return every tag suggestion with id, for the management UI."""
    rows = (
        db.query(TagSuggestion)
        .order_by(TagSuggestion.field, TagSuggestion.value)
        .all()
    )
    return [
        {"id": r.id, "field": r.field, "value": r.value, "use_count": r.use_count,
         "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None}
        for r in rows
    ]

@router.post("")
def create_suggestion(body: dict, db: Session = Depends(get_db)):
    field = body.get("field", "").strip()
    value = body.get("value", "").strip()
    if not field or not value:
        raise HTTPException(400, "field and value are required")
    if field not in tag_suggestions.FIELD_MAP:
        raise HTTPException(400, f"invalid field: {field}")
    existing = (
        db.query(TagSuggestion)
        .filter(TagSuggestion.field == field, TagSuggestion.value == value)
        .first()
    )
    if existing:
        raise HTTPException(409, "suggestion already exists")
    row = TagSuggestion(field=field, value=value, use_count=0)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row.to_dict()


@router.put("/{suggestion_id}")
def update_suggestion(suggestion_id: int, body: dict, db: Session = Depends(get_db)):
    row = db.query(TagSuggestion).filter(TagSuggestion.id == suggestion_id).first()
    if not row:
        raise HTTPException(404, "suggestion not found")
    if "value" in body:
        new_value = body["value"].strip()
        if not new_value:
            raise HTTPException(400, "value cannot be empty")
        # check uniqueness
        dup = (
            db.query(TagSuggestion)
            .filter(
                TagSuggestion.field == row.field,
                TagSuggestion.value == new_value,
                TagSuggestion.id != suggestion_id,
            )
            .first()
        )
        if dup:
            raise HTTPException(409, "a suggestion with that value already exists")
        row.value = new_value
    if "field" in body:
        new_field = body["field"].strip()
        if new_field not in tag_suggestions.FIELD_MAP:
            raise HTTPException(400, f"invalid field: {new_field}")
        row.field = new_field
    db.commit()
    db.refresh(row)
    return row.to_dict()

@router.delete("/{suggestion_id}")
def delete_suggestion(suggestion_id: int, db: Session = Depends(get_db)):
    row = db.query(TagSuggestion).filter(TagSuggestion.id == suggestion_id).first()
    if not row:
        raise HTTPException(404, "suggestion not found")
    db.delete(row)
    db.commit()
    return {"ok": True}

@router.post("/populate")
def populate_from_library(db: Session = Depends(get_db)):
    """Scan every audio file in the library dir and populate tag suggestions."""
    lib = settings_service.library_dir(db)
    if not lib.exists():
        raise HTTPException(400, f"Library directory does not exist: {lib}")
    result = tag_suggestions.populate_suggestions(db, lib)
    return result
