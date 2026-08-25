from fastapi import APIRouter
from sqlalchemy import text

from app.db.session import get_engine

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/db")
def health_db() -> dict[str, str]:
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "reachable"}
    except Exception as exc:  # noqa: BLE001 — surface any driver error verbatim
        return {"status": "degraded", "database": "unreachable", "detail": str(exc)}
