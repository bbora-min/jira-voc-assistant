"""카테고리 조회 API (드롭다운용)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Category

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("")
def list_categories(db: Annotated[Session, Depends(get_db)]) -> dict:
    rows = db.execute(
        select(Category).where(Category.is_active.is_(True)).order_by(Category.sort_order)
    ).scalars().all()
    return {
        "items": [
            {"id": c.id, "code": c.code, "label_ko": c.label_ko, "label_en": c.label_en}
            for c in rows
        ]
    }
