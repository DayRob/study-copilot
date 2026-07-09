import asyncio
import threading

from fastapi import APIRouter, BackgroundTasks

from app.cyber.pipeline import sync_all

router = APIRouter(prefix="/cyber", tags=["cyber"])

_lock = threading.Lock()
_state = {
    "status": "idle",  # idle | running | completed | failed
    "current": 0,
    "total": 0,
    "current_item": None,
    "stats": None,
    "error": None,
}


def _try_claim() -> bool:
    """Same atomic check-and-set pattern as api/ingest.py::_try_claim, so a
    double-click on 'Sync' can't start two overlapping syncs."""
    with _lock:
        if _state["status"] == "running":
            return False
        _state.update(status="running", current=0, total=0, current_item=None, stats=None, error=None)
        return True


def _run() -> None:
    def progress_cb(current: int, total: int, title: str) -> None:
        with _lock:
            _state.update(current=current, total=total, current_item=title)

    try:
        stats = asyncio.run(sync_all(progress_cb=progress_cb))
        with _lock:
            _state.update(status="completed", stats=stats.__dict__)
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI via /status
        with _lock:
            _state.update(status="failed", error=str(exc))


@router.post("/sync")
def start_sync(background_tasks: BackgroundTasks):
    if not _try_claim():
        return {"status": "already_running"}
    background_tasks.add_task(_run)
    return {"status": "started"}


@router.get("/status")
def get_status():
    with _lock:
        return dict(_state)


@router.get("/items")
def list_items():
    from app.db.connection import get_connection

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, connector, url, title, published_at, fetched_at, summary,
                   content_type, technical_domain, level, authority_source, referentiel, tags_json
            FROM cyber_items
            ORDER BY fetched_at DESC
            """
        ).fetchall()
        return [dict(row) for row in rows]
