import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.connection import init_db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()
    init_db()

    # Import main only after DB_PATH is patched, and only inside the test, so
    # module-level state (the in-memory _state dict in api/cyber.py) starts
    # fresh per test.
    import importlib

    import app.api.cyber as cyber_api

    importlib.reload(cyber_api)

    from app.main import app

    # base_url must present an allowed Host (main.py's TrustedHostMiddleware
    # only permits localhost/127.0.0.1/::1); TestClient's default
    # "http://testserver" host is otherwise rejected with 400 Bad Request.
    with TestClient(app, base_url="http://localhost") as test_client:
        yield test_client, cyber_api
    get_settings.cache_clear()


def test_status_starts_idle(client):
    test_client, _ = client
    response = test_client.get("/cyber/status")
    assert response.status_code == 200
    assert response.json()["status"] == "idle"


def test_sync_endpoint_starts_and_status_reflects_it(client, monkeypatch):
    test_client, cyber_api = client

    async def fake_sync_all(progress_cb=None):
        from app.cyber.pipeline import SyncStats

        return SyncStats(items_found=0, items_added=0, items_updated=0, items_skipped=0, errors=0)

    monkeypatch.setattr(cyber_api, "sync_all", fake_sync_all)

    response = test_client.post("/cyber/sync")
    assert response.status_code == 200
    assert response.json()["status"] == "started"

    status = test_client.get("/cyber/status").json()
    assert status["status"] in ("running", "completed")
