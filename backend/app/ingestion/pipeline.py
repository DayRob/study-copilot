import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import sqlite_vec

from app.config import get_settings
from app.db.connection import get_connection
from app.ingestion.chunking import (
    TARGET_WORDS,
    OVERLAP_WORDS,
    Chunk,
    _split_words,
    chunk_code,
    chunk_docx_sections,
    chunk_pdf_pages,
    enforce_char_cap,
)
from app.ingestion.embed import embed_documents
from app.ingestion.extractors.code import extract_code
from app.ingestion.extractors.docx import extract_docx
from app.ingestion.extractors.pdf import extract_pdf
from app.ingestion.walker import DiscoveredFile, discover_files


@dataclass
class IngestStats:
    files_scanned: int = 0
    files_added: int = 0
    files_updated: int = 0
    files_deleted: int = 0
    files_skipped: int = 0


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _get_or_create_subject(conn: sqlite3.Connection, file: DiscoveredFile) -> int:
    row = conn.execute(
        "SELECT id FROM subjects WHERE year = ? AND semester IS ? AND name = ?",
        (file.year, file.semester, file.subject),
    ).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO subjects (year, semester, name, root_path) VALUES (?, ?, ?, ?)",
        (file.year, file.semester, file.subject, str(file.subject_root)),
    )
    return cur.lastrowid


def _extract_and_chunk(file: DiscoveredFile) -> list[Chunk]:
    if file.file_type == "pdf":
        chunks = chunk_pdf_pages(extract_pdf(file.absolute_path))
    elif file.file_type == "docx":
        chunks = chunk_docx_sections(extract_docx(file.absolute_path))
    elif file.file_type == "code":
        text, language = extract_code(file.absolute_path)
        chunks = chunk_code(text, language)
    else:
        # plain-text prose: .md, .txt, .json, .csv, .xml
        text, _ = extract_code(file.absolute_path)
        pieces = _split_words(text, TARGET_WORDS, OVERLAP_WORDS) or ([text] if text.strip() else [])
        chunks = [Chunk(text=p, content_type="prose") for p in pieces]
    return enforce_char_cap(chunks)


def _store_file_chunks(conn: sqlite3.Connection, source_file_id: int, chunks: list[Chunk]) -> None:
    embeddings = embed_documents([c.text for c in chunks])
    for idx, (chunk, vector) in enumerate(zip(chunks, embeddings)):
        cur = conn.execute(
            """
            INSERT INTO chunks
                (source_file_id, content_type, text, page_start, page_end, line_start, line_end, language, chunk_index)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_file_id, chunk.content_type, chunk.text,
                chunk.page_start, chunk.page_end, chunk.line_start, chunk.line_end,
                chunk.language, idx,
            ),
        )
        chunk_id = cur.lastrowid
        conn.execute(
            "INSERT INTO chunk_embeddings (chunk_id, embedding) VALUES (?, ?)",
            (chunk_id, sqlite_vec.serialize_float32(vector.tolist())),
        )


def run_ingestion(progress_cb=None) -> IngestStats:
    settings = get_settings()
    stats = IngestStats()
    discovered = discover_files(settings.course_roots)
    stats.files_scanned = len(discovered)
    seen_paths: set[str] = set()

    with get_connection() as conn:
        for i, file in enumerate(discovered):
            seen_paths.add(str(file.absolute_path))
            if progress_cb:
                progress_cb(i + 1, len(discovered), str(file.relative_path))

            existing = conn.execute(
                "SELECT id, content_hash FROM source_files WHERE absolute_path = ?",
                (str(file.absolute_path),),
            ).fetchone()

            content_hash = _hash_file(file.absolute_path)
            if existing and existing["content_hash"] == content_hash:
                stats.files_skipped += 1
                continue

            try:
                chunks = _extract_and_chunk(file)
            except Exception:
                stats.files_skipped += 1
                continue
            if not chunks:
                stats.files_skipped += 1
                continue

            subject_id = _get_or_create_subject(conn, file)
            now = datetime.now(timezone.utc).isoformat()

            # Upsert rather than a separate insert/update branch: two ingestion
            # runs (e.g. a manual script alongside a "Sync now" click) can both
            # pass the `existing` check before either commits, so a plain
            # INSERT would race into a UNIQUE constraint violation on
            # absolute_path. ON CONFLICT makes the write atomic regardless.
            cur = conn.execute(
                """
                INSERT INTO source_files
                    (subject_id, relative_path, absolute_path, file_type, content_hash, last_ingested_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(absolute_path) DO UPDATE SET
                    subject_id = excluded.subject_id,
                    relative_path = excluded.relative_path,
                    file_type = excluded.file_type,
                    content_hash = excluded.content_hash,
                    last_ingested_at = excluded.last_ingested_at
                RETURNING id
                """,
                (
                    subject_id, str(file.relative_path), str(file.absolute_path),
                    file.file_type, content_hash, now,
                ),
            )
            source_file_id = cur.fetchone()["id"]
            conn.execute("DELETE FROM chunks WHERE source_file_id = ?", (source_file_id,))
            if existing:
                stats.files_updated += 1
            else:
                stats.files_added += 1

            _store_file_chunks(conn, source_file_id, chunks)
            conn.commit()

        resolved_roots = [r.resolve() for r in settings.course_roots]
        for row in conn.execute("SELECT id, absolute_path FROM source_files").fetchall():
            # Path containment, not string-prefix matching: a plain
            # str.startswith() would treat root ".../4A" as a match for a
            # sibling folder ".../4AB" since "4AB" starts with "4A" as text.
            path = Path(row["absolute_path"])
            under_a_root = any(path.is_relative_to(root) for root in resolved_roots)
            if under_a_root and row["absolute_path"] not in seen_paths:
                conn.execute("DELETE FROM source_files WHERE id = ?", (row["id"],))
                stats.files_deleted += 1
        conn.commit()

    _sync_obsidian_export()
    return stats


def _sync_obsidian_export() -> None:
    """Best-effort: keep the Obsidian mirror fresh after every ingestion run,
    without needing a manual export step. Never fails ingestion itself."""
    try:
        from app.obsidian.export import export_to_obsidian

        export_to_obsidian()
    except Exception:
        pass
