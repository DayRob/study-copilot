import threading

from fastapi import APIRouter, BackgroundTasks

from app.ingestion.pipeline import run_ingestion

router = APIRouter(prefix="/ingest", tags=["ingest"])

_lock = threading.Lock()
_state = {
    "status": "idle",  # idle | running | completed | failed
    "current": 0,
    "total": 0,
    "current_file": None,
    "stats": None,
    "error": None,
}


def _try_claim() -> bool:
    """Atomically check-and-set the 'running' slot under one lock acquisition.
    Checking status and setting it as two separate locked sections (as this
    used to do) leaves a window where the file watcher's debounce timer and
    a manual 'Sync now' click can both observe 'idle' and both proceed to run
    an ingestion concurrently -- this collapses that into a single atomic
    claim so only one caller ever wins."""
    with _lock:
        if _state["status"] == "running":
            return False
        _state.update(status="running", current=0, total=0, current_file=None, stats=None, error=None)
        return True


def _run() -> None:
    # Caller must have already claimed the slot via _try_claim().
    def progress_cb(current: int, total: int, filename: str) -> None:
        with _lock:
            _state.update(current=current, total=total, current_file=filename)

    try:
        stats = run_ingestion(progress_cb=progress_cb)
        with _lock:
            _state.update(status="completed", stats=stats.__dict__)
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI via /status
        with _lock:
            _state.update(status="failed", error=str(exc))


def trigger_if_idle() -> bool:
    """Shared entry point for both the manual 'Sync now' button and the
    background file watcher, so an auto-triggered sync shows up in
    GET /status exactly like a manual one. Returns False without doing
    anything if a sync is already running."""
    if not _try_claim():
        return False
    _run()
    return True


@router.post("/run")
def start_ingestion(background_tasks: BackgroundTasks):
    if not _try_claim():
        return {"status": "already_running"}
    background_tasks.add_task(_run)
    return {"status": "started"}


@router.get("/status")
def get_status():
    with _lock:
        return dict(_state)
