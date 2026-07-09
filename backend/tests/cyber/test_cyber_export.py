from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

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


def test_frontmatter_yaml_escaping_on_colons_and_special_chars(vault):
    """Verify frontmatter YAML is properly escaped when values contain colons, quotes, or other special chars.

    This test seeds an item with a title containing a colon and tags with colons,
    then asserts that the emitted frontmatter block parses as valid YAML and
    that the tags are correctly preserved.
    """
    from app.obsidian.export import slugify

    title = "Guide : bonnes pratiques réseau"
    tags = ["durcissement: réseau", "tls", "sécurité: pratiques"]

    with get_connection() as conn:
        _seed_item(conn, title=title, tags=tags)

    export_cyber_to_obsidian()

    export_root = vault / "Cours CPE" / "Culture Cyber"
    note_path = export_root / f"{slugify(title)}.md"
    assert note_path.exists()

    content = note_path.read_text(encoding="utf-8")

    # Extract frontmatter block (between --- markers)
    lines = content.split("\n")
    assert lines[0] == "---", "First line should be frontmatter opening marker"

    # Find the closing --- marker
    closing_idx = None
    for i in range(1, len(lines)):
        if lines[i] == "---":
            closing_idx = i
            break

    assert closing_idx is not None, "Should have a closing frontmatter marker"

    frontmatter_text = "\n".join(lines[1:closing_idx])

    # Parse the frontmatter as YAML; should not raise
    frontmatter = yaml.safe_load(frontmatter_text)

    # Verify the tags list was preserved correctly
    assert frontmatter["tags"] == tags, f"Expected tags {tags}, got {frontmatter['tags']}"
    # Verify source and other fields are present
    assert frontmatter["source"] == "ANSSI"
    assert frontmatter["connector"] == "anssi"
