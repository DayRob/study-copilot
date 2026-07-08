from dataclasses import dataclass

from app.db.connection import get_connection

OVERVIEW_SYSTEM_PROMPT = (
    "Tu es un enseignant qui rédige une fiche de révision approfondie à partir d'extraits de cours réels. "
    "La fiche doit APPRENDRE quelque chose de concret au lecteur, pas seulement lister des mots-clés. "
    "Interdiction stricte : ne te contente jamais de reformuler le nom du sujet ou de citer des termes sans "
    "les expliquer — ce serait inutile.\n\n"
    "Résumé (3 à 5 paragraphes) : explique les mécanismes, méthodes, définitions ou raisonnements réellement "
    "présents dans les extraits, pas un sommaire de titres. Si les extraits décrivent une méthode en plusieurs "
    "étapes, détaille ces étapes ; si un concept est défini, donne la définition précise ; si deux notions sont "
    "comparées ou opposées, explique la différence ; si un exemple concret apparaît, réutilise-le.\n\n"
    "Notions clés (4 à 8) : pour chaque notion, donne un concept court ET une explication de 2 à 4 phrases qui "
    "enseigne réellement ce que c'est, comment ça marche ou pourquoi c'est important — jamais une simple étiquette "
    "sans contenu.\n\n"
    "Base-toi UNIQUEMENT sur les extraits fournis, dans la langue dominante des extraits, sans rien inventer au-delà."
)

OVERVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "Resume approfondi en 3-5 paragraphes expliquant les mecanismes/definitions "
            "reellement presents dans les extraits, pas un sommaire de titres",
        },
        "key_topics": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "concept": {"type": "string", "description": "Nom court de la notion"},
                    "explanation": {
                        "type": "string",
                        "description": "Explication concrete de 2 a 4 phrases qui enseigne reellement la notion",
                    },
                },
                "required": ["concept", "explanation"],
            },
            "minItems": 4,
            "maxItems": 8,
            "description": "Notions cles abordees, chacune avec une vraie explication",
        },
    },
    "required": ["summary", "key_topics"],
}


@dataclass
class SampledChunk:
    chunk_id: int
    text: str
    content_type: str
    relative_path: str
    page_start: int | None
    page_end: int | None
    line_start: int | None
    line_end: int | None


def sample_subject_chunks(subject_id: int, limit: int = 32) -> list[SampledChunk]:
    """Structural sampling (not similarity search): spreads across the whole
    subject rather than clustering around one query, which is what an
    'overview' needs."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT c.id AS chunk_id, c.text, c.content_type, c.page_start, c.page_end,
                   c.line_start, c.line_end, sf.relative_path
            FROM chunks c
            JOIN source_files sf ON sf.id = c.source_file_id
            WHERE sf.subject_id = ?
            ORDER BY sf.id, c.chunk_index
            """,
            (subject_id,),
        ).fetchall()

    if not rows:
        return []
    if len(rows) <= limit:
        picked = rows
    else:
        stride = len(rows) / limit
        picked = [rows[int(i * stride)] for i in range(limit)]

    return [
        SampledChunk(
            chunk_id=r["chunk_id"],
            text=r["text"],
            content_type=r["content_type"],
            relative_path=r["relative_path"],
            page_start=r["page_start"],
            page_end=r["page_end"],
            line_start=r["line_start"],
            line_end=r["line_end"],
        )
        for r in picked
    ]


def pick_examples(chunks: list[SampledChunk], n: int = 4) -> list[SampledChunk]:
    """Verbatim excerpts straight from the corpus (no LLM paraphrasing) so
    citations are guaranteed accurate. Prefers substantial prose, one per
    distinct file, falling back to code if there isn't enough prose."""
    prose = [c for c in chunks if c.content_type == "prose" and len(c.text) > 120]
    code = [c for c in chunks if c.content_type == "code" and len(c.text) > 60]

    examples: list[SampledChunk] = []
    seen_files: set[str] = set()
    for chunk in [*prose, *code]:
        if chunk.relative_path in seen_files:
            continue
        examples.append(chunk)
        seen_files.add(chunk.relative_path)
        if len(examples) >= n:
            break
    return examples


def build_overview_prompt(subject_name: str, chunks: list[SampledChunk]) -> str:
    context = "\n\n".join(f"[{i}] ({c.relative_path})\n{c.text[:1100]}" for i, c in enumerate(chunks, start=1))
    return f"Sujet : {subject_name}\n\nExtraits de cours :\n\n{context}"
