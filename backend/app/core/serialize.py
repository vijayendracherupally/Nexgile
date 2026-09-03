"""Model -> JSON helpers shared by every module router."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import Session


def to_dict(obj, *, exclude: set[str] | None = None, extra: dict | None = None) -> dict:
    if obj is None:
        return {}
    exclude = exclude or set()
    out: dict[str, Any] = {}
    for column in inspect(obj).mapper.column_attrs:
        key = column.key
        if key in exclude:
            continue
        value = getattr(obj, key)
        if isinstance(value, (datetime, date)):
            value = value.isoformat()
        out[key] = value
    if extra:
        out.update(extra)
    return out


def rows(items, **kwargs) -> list[dict]:
    return [to_dict(i, **kwargs) for i in items]


def paginate(db: Session, stmt: Select, *, page: int = 1, page_size: int = 50) -> dict:
    page = max(1, page)
    page_size = max(1, min(500, page_size))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items = list(db.scalars(stmt.limit(page_size).offset((page - 1) * page_size)))
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": (total + page_size - 1) // page_size,
    }


def page_response(db: Session, stmt: Select, *, page: int = 1, page_size: int = 50,
                  mapper=None) -> dict:
    result = paginate(db, stmt, page=page, page_size=page_size)
    mapper = mapper or (lambda o: to_dict(o))
    result["items"] = [mapper(o) for o in result["items"]]
    return result


def kg_to_t(kg: float | None) -> float:
    return round((kg or 0.0) / 1000.0, 4)
