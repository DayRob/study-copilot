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
    subject_id: int
    subject_name: str
    year: str
    semester: str | None
    relative_path: str
    absolute_path: str
    page_start: int | None
    page_end: int | None
    line_start: int | None
    line_end: int | None


def retrieve(query: str, top_k: int = 10, subject_id: int | None = None) -> list[RetrievedChunk]:
    """KNN search over sqlite-vec, then join back to relational metadata for
    citations. Overfetches and filters in Python when scoping to a subject
    rather than pushing the filter into vec0 -- simplest option at this
    corpus scale (thousands, not millions, of chunks)."""
    vector = embed_query(query)
    fetch_k = top_k * 5 if subject_id is not None else top_k

    with get_connection() as conn:
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

        by_id = {row["chunk_id"]: row for row in chunk_rows}
        results: list[RetrievedChunk] = []
        # Preserve KNN distance order (the IN query above has no guaranteed order).
        for chunk_id in distance_by_chunk_id:
            chunk_row = by_id.get(chunk_id)
            if chunk_row is None:
                continue
            if subject_id is not None and chunk_row["subject_id"] != subject_id:
                continue
            results.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    text=chunk_row["text"],
                    content_type=chunk_row["content_type"],
                    distance=distance_by_chunk_id[chunk_id],
                    subject_id=chunk_row["subject_id"],
                    subject_name=chunk_row["subject_name"],
                    year=chunk_row["year"],
                    semester=chunk_row["semester"],
                    relative_path=chunk_row["relative_path"],
                    absolute_path=chunk_row["absolute_path"],
                    page_start=chunk_row["page_start"],
                    page_end=chunk_row["page_end"],
                    line_start=chunk_row["line_start"],
                    line_end=chunk_row["line_end"],
                )
            )
            if len(results) >= top_k:
                break
    return results
