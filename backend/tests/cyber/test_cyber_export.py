from pathlib import Path
from unittest.mock import patch

import pytest

from app.config import get_settings
from app.db.connection import init_db, get_connection
from app.obsidian.cyber_export import export_cyber_to_obsidian


@pytest.fixture
def vault(tmp_path, monkeypatch):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(vault_root))
    get_settings.cache_clear()
    init_db()
    yield vault_root
    get_settings.cache_clear()


def _seed_item(conn, title="Guide de test", referentiel=None, tags=None):
    import json

    conn.execute(
        """
        INSERT INTO cyber_items
            (connector, url, title, published_at, fetched_at, content_hash, raw_text, summary,
             content_type, technical_domain, level, authority_source, referentiel, tags_json,
             generation_model, last_synced_at)
        VALUES ('anssi', ?, ?, '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z', 'h', 'texte complet',
                'Résumé reformulé de test.', 'guide_bonnes_pratiques', 'reseau', 'fondamental',
                'ANSSI', ?, ?, 'llama3.1:8b', '2026-01-02T00:00:00Z')
        """,
        (f"https://example.org/{title}", title, referentiel, json.dumps(tags or [])),
    )
    conn.commit()


def test_export_writes_one_note_per_item(vault):
    with get_connection() as conn:
        _seed_item(conn, title="Guide de test")

    result = export_cyber_to_obsidian()

    assert result == {"items_exported": 1}
    export_root = vault / "Cours CPE" / "Culture Cyber"
    note_path = export_root / "Guide de test.md"
    assert note_path.exists()
    content = note_path.read_text(encoding="utf-8")
    assert "source: ANSSI" in content
    assert "https://example.org/Guide de test" in content
    assert "Résumé reformulé de test." in content


def test_export_writes_index(vault):
    with get_connection() as conn:
        _seed_item(conn, title="Guide A")
        _seed_item(conn, title="Guide B")

    export_cyber_to_obsidian()

    index_path = vault / "Cours CPE" / "Culture Cyber" / "_Index.md"
    assert index_path.exists()
    content = index_path.read_text(encoding="utf-8")
    assert "Guide A" in content
    assert "Guide B" in content


def test_export_returns_none_when_vault_not_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()
    init_db()

    # Mock get_settings to return a settings object with no vault configured
    mock_settings = get_settings()
    mock_settings.obsidian_vault_path = None
    with patch("app.obsidian.cyber_export.get_settings", return_value=mock_settings):
        assert export_cyber_to_obsidian() is None
