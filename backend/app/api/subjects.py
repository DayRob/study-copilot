import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.config import get_settings
from app.db.connection import get_connection
from app.llm.factory import get_llm_provider
from app.rag.overview import (
    OVERVIEW_SCHEMA,
    OVERVIEW_SYSTEM_PROMPT,
    build_overview_prompt,
    pick_examples,
    sample_subject_chunks,
)
from app.rag.resources import match_resources

router = APIRouter(prefix="/subjects", tags=["subjects"])


@router.get("")
def list_subjects():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT s.id, s.year, s.semester, s.name,
                   COUNT(DISTINCT sf.id) AS file_count,
                   COUNT(DISTINCT c.id) AS chunk_count
            FROM subjects s
            LEFT JOIN source_files sf ON sf.subject_id = s.id
            LEFT JOIN chunks c ON c.source_file_id = sf.id
            GROUP BY s.id
            ORDER BY s.year, s.semester, s.name
            """
        ).fetchall()
        return [dict(row) for row in rows]


@router.get("/{subject_id}/files")
def list_subject_files(subject_id: int):
    with get_connection() as conn:
        subject = conn.execute("SELECT id FROM subjects WHERE id = ?", (subject_id,)).fetchone()
        if not subject:
            raise HTTPException(status_code=404, detail="Subject not found")
        rows = conn.execute(
            """
            SELECT sf.id, sf.relative_path, sf.file_type, sf.last_ingested_at,
                   COUNT(c.id) AS chunk_count
            FROM source_files sf
            LEFT JOIN chunks c ON c.source_file_id = sf.id
            WHERE sf.subject_id = ?
            GROUP BY sf.id
            ORDER BY sf.relative_path
            """,
            (subject_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def _row_to_overview(row) -> dict:
    return {
        "subject_id": row["subject_id"],
        "summary": row["summary"],
        "key_topics": json.loads(row["key_topics"]),
        "examples": json.loads(row["examples"]),
        "resources": json.loads(row["resources"]),
        "generated_at": row["generated_at"],
        "cached": True,
    }


async def _generate_overview(subject_id: int, subject_name: str) -> dict:
    settings = get_settings()
    if settings.llm_provider == "anthropic" and not settings.anthropic_api_key:
        raise HTTPException(
            status_code=503,
            detail="ANTHROPIC_API_KEY n'est pas configurée (backend/.env) — nécessaire pour générer la fiche.",
        )

    chunks = sample_subject_chunks(subject_id)
    if not chunks:
        raise HTTPException(status_code=404, detail="Aucun contenu ingéré pour ce sujet pour l'instant.")

    provider = get_llm_provider()
    user_prompt = build_overview_prompt(subject_name, chunks)
    try:
        result = await provider.complete_structured(
            OVERVIEW_SYSTEM_PROMPT, user_prompt, OVERVIEW_SCHEMA, fast=True
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Le modèle ({settings.llm_provider}) n'a pas répondu : {exc}",
        ) from exc

    examples = [
        {
            "text": c.text,
            "relative_path": c.relative_path,
            "page_start": c.page_start,
            "page_end": c.page_end,
            "line_start": c.line_start,
            "line_end": c.line_end,
        }
        for c in pick_examples(chunks)
    ]
    resources = match_resources(result["key_topics"], subject_name)
    now = datetime.now(timezone.utc).isoformat()
    model_used = settings.ollama_model if settings.llm_provider == "ollama" else settings.llm_fast_model

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO subject_overviews (subject_id, summary, key_topics, examples, resources, generated_at, model)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(subject_id) DO UPDATE SET
                summary = excluded.summary,
                key_topics = excluded.key_topics,
                examples = excluded.examples,
                resources = excluded.resources,
                generated_at = excluded.generated_at,
                model = excluded.model
            """,
            (
                subject_id,
                result["summary"],
                json.dumps(result["key_topics"]),
                json.dumps(examples),
                json.dumps(resources),
                now,
                model_used,
            ),
        )
        conn.commit()

    try:
        from app.obsidian.export import export_to_obsidian

        export_to_obsidian()
    except Exception:
        pass

    return {
        "subject_id": subject_id,
        "summary": result["summary"],
        "key_topics": result["key_topics"],
        "examples": examples,
        "resources": resources,
        "generated_at": now,
        "cached": False,
    }


@router.get("/{subject_id}/overview")
async def get_subject_overview(subject_id: int):
    with get_connection() as conn:
        subject = conn.execute("SELECT id, name FROM subjects WHERE id = ?", (subject_id,)).fetchone()
        if not subject:
            raise HTTPException(status_code=404, detail="Subject not found")
        cached = conn.execute(
            "SELECT * FROM subject_overviews WHERE subject_id = ?", (subject_id,)
        ).fetchone()
    if cached:
        return _row_to_overview(cached)
    return await _generate_overview(subject_id, subject["name"])


@router.post("/{subject_id}/overview/regenerate")
async def regenerate_subject_overview(subject_id: int):
    with get_connection() as conn:
        subject = conn.execute("SELECT id, name FROM subjects WHERE id = ?", (subject_id,)).fetchone()
        if not subject:
            raise HTTPException(status_code=404, detail="Subject not found")
    return await _generate_overview(subject_id, subject["name"])
