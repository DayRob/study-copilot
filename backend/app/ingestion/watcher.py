"""Watches COURSE_ROOTS for changes and triggers an incremental re-ingestion
automatically -- this is what removes the need to click 'Sync now' after
editing a note (e.g. in the "Mes Notes" Obsidian folder) or adding a course
file. Debounced so a burst of saves (or an editor's autosave) doesn't
trigger a re-sync per keystroke."""

import threading

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app.config import get_settings

_observer: Observer | None = None
_debounce_timer: threading.Timer | None = None
_timer_lock = threading.Lock()


class _DebouncedHandler(FileSystemEventHandler):
    def __init__(self, debounce_seconds: float) -> None:
        self._debounce_seconds = debounce_seconds

    def on_any_event(self, event) -> None:
        if event.is_directory:
            return
        _schedule_sync(self._debounce_seconds)


def _schedule_sync(debounce_seconds: float) -> None:
    global _debounce_timer
    with _timer_lock:
        if _debounce_timer is not None:
            _debounce_timer.cancel()
        _debounce_timer = threading.Timer(debounce_seconds, _trigger_sync)
        _debounce_timer.daemon = True
        _debounce_timer.start()


def _trigger_sync() -> None:
    from app.api.ingest import trigger_if_idle

    trigger_if_idle()


def start_watcher() -> None:
    global _observer
    settings = get_settings()
    roots = [r for r in settings.course_roots if r.exists()]
    if not roots:
        return

    _observer = Observer()
    handler = _DebouncedHandler(settings.watch_debounce_seconds)
    for root in roots:
        _observer.schedule(handler, str(root), recursive=True)
    _observer.start()


def stop_watcher() -> None:
    if _observer is not None:
        _observer.stop()
        _observer.join(timeout=5)
