import sqlite3
from contextlib import contextmanager
from pathlib import Path

import sqlite_vec

from app.config import get_settings
from app.db.migrate import run_migrations

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def init_db() -> None:
    settings = get_settings()
    conn = _connect(settings.resolved_db_path)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS chunk_embeddings USING vec0(
                chunk_id INTEGER PRIMARY KEY,
                embedding FLOAT[{settings.embedding_dim}]
            )
            """
        )
        # vec0 virtual tables aren't covered by the schema's FK cascades, so
        # clean them up explicitly whenever a chunk row disappears.
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_chunks_delete_embeddings
            AFTER DELETE ON chunks
            BEGIN
                DELETE FROM chunk_embeddings WHERE chunk_id = OLD.id;
            END
            """
        )
        conn.commit()
        run_migrations(conn)
        conn.execute(
            f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS cyber_chunk_embeddings USING vec0(
                chunk_id INTEGER PRIMARY KEY,
                embedding FLOAT[{settings.embedding_dim}]
            )
            """
        )
        conn.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_cyber_chunks_delete_embeddings
            AFTER DELETE ON cyber_chunks
            BEGIN
                DELETE FROM cyber_chunk_embeddings WHERE chunk_id = OLD.id;
            END
            """
        )
        conn.commit()
    finally:
        conn.close()


@contextmanager
def get_connection():
    settings = get_settings()
    conn = _connect(settings.resolved_db_path)
    try:
        yield conn
    finally:
        conn.close()
