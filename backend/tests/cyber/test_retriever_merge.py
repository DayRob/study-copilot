import numpy as np
import pytest

import app.rag.retriever as retriever_module
from app.config import get_settings
from app.db.connection import init_db, get_connection
from app.rag.retriever import retrieve


@pytest.fixture
def rag_db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    get_settings.cache_clear()
    init_db()

    dim = get_settings().embedding_dim

    def fake_embed_query(text: str):
        return np.ones(dim, dtype=np.float32)

    # Chunk embeddings are seeded directly below (see _seed_course_chunk /
    # _seed_cyber_chunk) rather than via embed_documents(), since the test
    # only needs a fixed vector for both course and cyber chunks so the KNN
    # match is deterministic -- only the query-side embed_query() is patched.
    monkeypatch.setattr(retriever_module, "embed_query", fake_embed_query)
    yield
    get_settings.cache_clear()


def _seed_course_chunk(conn, text="Un chunk de cours."):
    import sqlite_vec

    conn.execute("INSERT INTO subjects (year, semester, name, root_path) VALUES ('4A', NULL, 'Réseaux', '/tmp')")
    subject_id = conn.execute("SELECT id FROM subjects WHERE name = 'Réseaux'").fetchone()["id"]
    conn.execute(
        """
        INSERT INTO source_files (subject_id, relative_path, absolute_path, file_type, content_hash, last_ingested_at)
        VALUES (?, 'cours.pdf', '/tmp/cours.pdf', 'pdf', 'h', '2026-01-01T00:00:00Z')
        """,
        (subject_id,),
    )
    source_file_id = conn.execute("SELECT id FROM source_files WHERE relative_path = 'cours.pdf'").fetchone()["id"]
    cur = conn.execute(
        "INSERT INTO chunks (source_file_id, content_type, text, chunk_index) VALUES (?, 'prose', ?, 0)",
        (source_file_id, text),
    )
    chunk_id = cur.lastrowid
    conn.execute(
        "INSERT INTO chunk_embeddings (chunk_id, embedding) VALUES (?, ?)",
        (chunk_id, sqlite_vec.serialize_float32([1.0] * get_settings().embedding_dim)),
    )
    conn.commit()
    return subject_id


def _seed_cyber_chunk(conn, text="Un chunk de veille cyber."):
    import sqlite_vec

    conn.execute(
        """
        INSERT INTO cyber_items
            (connector, url, title, fetched_at, content_hash, raw_text, summary,
             content_type, technical_domain, level, authority_source, tags_json,
             generation_model, last_synced_at)
        VALUES ('anssi', 'https://example.org/x', 'Titre cyber', '2026-01-01T00:00:00Z', 'h',
                'texte', 'resume', 'guide_bonnes_pratiques', 'reseau', 'fondamental',
                'ANSSI', '[]', 'llama3.1:8b', '2026-01-01T00:00:00Z')
        """
    )
    item_id = conn.execute("SELECT id FROM cyber_items WHERE url = 'https://example.org/x'").fetchone()["id"]
    cur = conn.execute(
        "INSERT INTO cyber_chunks (cyber_item_id, content_type, text, chunk_index) VALUES (?, 'prose', ?, 0)",
        (item_id, text),
    )
    chunk_id = cur.lastrowid
    conn.execute(
        "INSERT INTO cyber_chunk_embeddings (chunk_id, embedding) VALUES (?, ?)",
        (chunk_id, sqlite_vec.serialize_float32([1.0] * get_settings().embedding_dim)),
    )
    conn.commit()


def test_retrieve_merges_course_and_cyber_chunks(rag_db):
    with get_connection() as conn:
        _seed_course_chunk(conn)
        _seed_cyber_chunk(conn)

    results = retrieve("question", top_k=10)

    origins = {(r.subject_name, r.relative_path) for r in results}
    assert ("Réseaux", "cours.pdf") in origins
    assert ("ANSSI", "Titre cyber") in origins
    cyber_result = next(r for r in results if r.subject_name == "ANSSI")
    assert cyber_result.absolute_path == "https://example.org/x"
    assert cyber_result.subject_id is None


def test_retrieve_excludes_cyber_when_subject_id_scoped(rag_db):
    with get_connection() as conn:
        subject_id = _seed_course_chunk(conn)
        _seed_cyber_chunk(conn)

    results = retrieve("question", top_k=10, subject_id=subject_id)

    assert all(r.subject_id == subject_id for r in results)
    assert all(r.subject_name != "ANSSI" for r in results)
