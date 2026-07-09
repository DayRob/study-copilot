from dataclasses import dataclass

import sqlite_vec

from app.db.connection import get_connection
from app.ingestion.embed import embed_query


@dataclass
class RetrievedChunk:
    chunk_id: int
    text: str
    content_type: str
    distance: float
    subject_id: int | None
    subject_name: str
    year: str | None
    semester: str | None
    relative_path: str
    absolute_path: str
    page_start: int | None
    page_end: int | None
    line_start: int | None
    line_end: int | None


def _knn_course(conn, vector, fetch_k: int) -> list[RetrievedChunk]:
    knn_rows = conn.execute(
        """
        SELECT chunk_id, distance
        FROM chunk_embeddings
        WHERE embedding MATCH ? AND k = ?
        ORDER BY distance
        """,
        (sqlite_vec.serialize_float32(vector.tolist()), fetch_k),
    ).fetchall()
    if not knn_rows:
        return []

    distance_by_chunk_id = {row["chunk_id"]: row["distance"] for row in knn_rows}
    placeholders = ",".join("?" * len(knn_rows))
    chunk_rows = conn.execute(
        f"""
        SELECT c.id AS chunk_id, c.text, c.content_type, c.page_start, c.page_end, c.line_start, c.line_end,
               sf.relative_path, sf.absolute_path, sf.subject_id,
               s.name AS subject_name, s.year, s.semester
        FROM chunks c
        JOIN source_files sf ON sf.id = c.source_file_id
        JOIN subjects s ON s.id = sf.subject_id
        WHERE c.id IN ({placeholders})
        """,
        [row["chunk_id"] for row in knn_rows],
    ).fetchall()

    results: list[RetrievedChunk] = []
    for row in chunk_rows:
        results.append(
            RetrievedChunk(
                chunk_id=row["chunk_id"],
                text=row["text"],
                content_type=row["content_type"],
                distance=distance_by_chunk_id[row["chunk_id"]],
                subject_id=row["subject_id"],
                subject_name=row["subject_name"],
                year=row["year"],
                semester=row["semester"],
                relative_path=row["relative_path"],
                absolute_path=row["absolute_path"],
                page_start=row["page_start"],
                page_end=row["page_end"],
                line_start=row["line_start"],
                line_end=row["line_end"],
            )
        )
    return results


def _knn_cyber(conn, vector, fetch_k: int) -> list[RetrievedChunk]:
    knn_rows = conn.execute(
        """
        SELECT chunk_id, distance
        FROM cyber_chunk_embeddings
        WHERE embedding MATCH ? AND k = ?
        ORDER BY distance
        """,
        (sqlite_vec.serialize_float32(vector.tolist()), fetch_k),
    ).fetchall()
    if not knn_rows:
        return []

    distance_by_chunk_id = {row["chunk_id"]: row["distance"] for row in knn_rows}
    placeholders = ",".join("?" * len(knn_rows))
    chunk_rows = conn.execute(
        f"""
        SELECT cc.id AS chunk_id, cc.text, cc.content_type,
               ci.title AS cyber_title, ci.url AS cyber_url, ci.authority_source
        FROM cyber_chunks cc
        JOIN cyber_items ci ON ci.id = cc.cyber_item_id
        WHERE cc.id IN ({placeholders})
        """,
        [row["chunk_id"] for row in knn_rows],
    ).fetchall()

    results: list[RetrievedChunk] = []
    for row in chunk_rows:
        results.append(
            RetrievedChunk(
                chunk_id=row["chunk_id"],
                text=row["text"],
                content_type=row["content_type"],
                distance=distance_by_chunk_id[row["chunk_id"]],
                # No subject_id: this is what naturally excludes cyber rows
                # from any subject-scoped retrieve() call, with no separate
                # "cyber only / course only" toggle needed.
                subject_id=None,
                subject_name=row["authority_source"],
                year=None,
                semester=None,
                relative_path=row["cyber_title"],
                absolute_path=row["cyber_url"],
                page_start=None,
                page_end=None,
                line_start=None,
                line_end=None,
            )
        )
    return results


def retrieve(query: str, top_k: int = 10, subject_id: int | None = None) -> list[RetrievedChunk]:
    """KNN search over both sqlite-vec tables (course chunks + cyber-veille
    chunks), merged by distance, then joined back to relational metadata for
    citations. Overfetches and filters in Python when scoping to a subject
    rather than pushing the filter into vec0 -- simplest option at this
    corpus scale (thousands, not millions, of chunks)."""
    vector = embed_query(query)
    fetch_k = top_k * 5 if subject_id is not None else top_k

    with get_connection() as conn:
        course_rows = _knn_course(conn, vector, fetch_k)
        cyber_rows = [] if subject_id is not None else _knn_cyber(conn, vector, fetch_k)
        merged = sorted(course_rows + cyber_rows, key=lambda r: r.distance)

        results: list[RetrievedChunk] = []
        for chunk in merged:
            if subject_id is not None and chunk.subject_id != subject_id:
                continue
            results.append(chunk)
            if len(results) >= top_k:
                break
    return results
