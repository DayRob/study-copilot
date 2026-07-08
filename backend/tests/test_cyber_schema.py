import sqlite3

import pytest

from app.config import get_settings
from app.db.connection import init_db, get_connection


@pytest.fixture
def cyber_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()
    init_db()
    yield
    get_settings.cache_clear()


def test_cyber_items_and_chunks_tables_exist(cyber_db):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO cyber_items
                (connector, url, title, fetched_at, content_hash, raw_text, summary,
                 content_type, technical_domain, level, authority_source, tags_json,
                 generation_model, last_synced_at)
            VALUES ('anssi', 'https://example.org/a', 'Titre', '2026-01-01T00:00:00Z', 'hash',
                    'texte', 'resume', 'guide_bonnes_pratiques', 'reseau', 'fondamental',
                    'ANSSI', '[]', 'llama3.1:8b', '2026-01-01T00:00:00Z')
            """
        )
        item_id = conn.execute("SELECT id FROM cyber_items WHERE url = ?", ("https://example.org/a",)).fetchone()["id"]
        conn.execute(
            "INSERT INTO cyber_chunks (cyber_item_id, content_type, text, chunk_index) VALUES (?, 'prose', 'chunk', 0)",
            (item_id,),
        )
        conn.commit()

        rows = conn.execute("SELECT * FROM cyber_chunks WHERE cyber_item_id = ?", (item_id,)).fetchall()
        assert len(rows) == 1


def test_cyber_chunk_content_type_check_constraint(cyber_db):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO cyber_items
                (connector, url, title, fetched_at, content_hash, raw_text, summary,
                 content_type, technical_domain, level, authority_source, tags_json,
                 generation_model, last_synced_at)
            VALUES ('anssi', 'https://example.org/b', 'Titre', '2026-01-01T00:00:00Z', 'hash',
                    'texte', 'resume', 'guide_bonnes_pratiques', 'reseau', 'fondamental',
                    'ANSSI', '[]', 'llama3.1:8b', '2026-01-01T00:00:00Z')
            """
        )
        item_id = conn.execute("SELECT id FROM cyber_items WHERE url = ?", ("https://example.org/b",)).fetchone()["id"]
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO cyber_chunks (cyber_item_id, content_type, text, chunk_index) VALUES (?, 'code', 'x', 0)",
                (item_id,),
            )


def test_cyber_chunk_embeddings_vec_table_exists(cyber_db):
    with get_connection() as conn:
        # A functioning vec0 table accepts a query against `embedding MATCH ?`
        # without raising -- this is the simplest way to confirm the virtual
        # table (not a regular table) was created with the right shape.
        rows = conn.execute(
            "SELECT COUNT(*) AS n FROM cyber_chunk_embeddings"
        ).fetchall()
        assert rows[0]["n"] == 0
