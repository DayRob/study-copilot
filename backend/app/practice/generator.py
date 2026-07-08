import asyncio
import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone

from app.db.connection import get_connection
from app.llm.factory import get_llm_provider
from app.practice.general_knowledge import GENERAL_CYBER_KNOWLEDGE
from app.rag.overview import SampledChunk, sample_subject_chunks

MIN_CHUNKS_REQUIRED = 6
QUESTIONS_PER_BATCH = 8
NUM_BATCHES = 2
OPTIONS_PER_QUESTION = 4
GENERAL_CULTURE_SUBJECT_NAME = "Culture Cyber Générale"
GENERAL_KNOWLEDGE_FRACTION = 0.25  # of a security subject's pool, when mixed in
MISSED_REVIEW_FRACTION = 0.35      # of a subject's sampled chunks, reserved for spaced review

SECURITY_KEYWORDS = [
    "securite", "sécurité", "cyber", "pentest", "offensive", "osint",
    "defense", "défense", "vuln", "port",
]

QUESTION_SYSTEM_PROMPT = (
    "Tu es un assistant pedagogique qui cree des questions a choix multiples (QCM) pour un jeu "
    "d'entrainement, dans la langue dominante des extraits. Pour chaque extrait numerote fourni, "
    "cree EXACTEMENT une question a partir du style indique entre parentheses :\n"
    "- (style: concept) -> question de comprehension classique sur la notion abordee.\n"
    "- (style: bug) -> montre un extrait de code et demande d'identifier le bug/l'erreur/le comportement "
    "correct ; les options sont des explications ou lignes candidates, une seule correcte.\n"
    "- (style: vuln) -> a partir du scenario/texte decrit, demande d'identifier la vulnerabilite, le risque "
    "ou la faille de securite pertinente ; les options sont des vulnerabilites/reponses candidates.\n"
    f"Chaque question doit avoir EXACTEMENT {OPTIONS_PER_QUESTION} options, une seule vraie, les autres "
    "plausibles mais fausses. 'correct_answer' doit etre le texte EXACT d'une des options. Precise aussi "
    "une difficulte (easy/medium/hard) et le numero de l'extrait source. Base-toi UNIQUEMENT sur l'extrait "
    "fourni, sans rien inventer au-dela."
)

GENERAL_KNOWLEDGE_SYSTEM_PROMPT = (
    "Tu es un assistant pedagogique qui cree des questions a choix multiples (QCM) de culture cybersecurite "
    "generale, en francais. Pour chaque fait numerote fourni, cree EXACTEMENT une question qui teste la "
    "comprehension de ce fait precis. N'INVENTE AUCUN FAIT : le fait donne est la seule verite, contente-toi "
    f"de le transformer en question et de fournir {OPTIONS_PER_QUESTION} options (une correcte, les autres "
    "plausibles mais fausses). 'correct_answer' doit etre le texte EXACT d'une des options. Precise une "
    "difficulte (easy/medium/hard) et le numero du fait source."
)

QUESTIONS_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": OPTIONS_PER_QUESTION,
                        "maxItems": OPTIONS_PER_QUESTION,
                    },
                    "correct_answer": {"type": "string"},
                    "difficulty": {"type": "string", "enum": ["easy", "medium", "hard"]},
                    "source_index": {"type": "integer"},
                },
                "required": ["prompt", "options", "correct_answer", "difficulty", "source_index"],
            },
        },
    },
    "required": ["questions"],
}


@dataclass
class StyledChunk:
    chunk: SampledChunk
    style: str  # 'concept' | 'bug' | 'vuln'
    subject_id: int


@dataclass
class GeneratedQuestion:
    prompt: str
    options: list[str]
    correct_answer: str
    difficulty: str
    style: str
    source_chunk_id: int
    subject_id: int


def _normalize(text: str) -> str:
    return text.lower().strip()


def _is_security_subject(name: str) -> bool:
    normalized = _normalize(name)
    return any(kw in normalized for kw in SECURITY_KEYWORDS)


def _style_for_chunk(chunk: SampledChunk, subject_name: str) -> str:
    if chunk.content_type == "code":
        return "bug"
    if _is_security_subject(subject_name):
        return "vuln"
    return "concept"


def _missed_chunk_ids(subject_id: int, limit: int) -> list[int]:
    """Retrieval-practice / light spaced-repetition: chunks behind questions
    the player recently got wrong, so they resurface in a later session
    instead of only ever seeing fresh material. This is the single biggest
    lever for 'actually learning something' per the gamification research
    (Duolingo's mechanics drive habit formation, but retrieval practice of
    previously-missed material is what drives retention)."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT e.source_chunk_ids FROM attempts a
            JOIN exercises e ON e.id = a.exercise_id
            WHERE e.subject_id = ? AND a.is_correct = 0
            ORDER BY a.attempted_at DESC
            LIMIT 50
            """,
            (subject_id,),
        ).fetchall()
    seen: set[int] = set()
    ordered: list[int] = []
    for row in rows:
        for chunk_id in json.loads(row["source_chunk_ids"]):
            if chunk_id not in seen:
                seen.add(chunk_id)
                ordered.append(chunk_id)
    return ordered[:limit]


def sample_chunks_for_subject(subject_id: int, limit: int = 16) -> list[StyledChunk]:
    with get_connection() as conn:
        subject = conn.execute("SELECT name FROM subjects WHERE id = ?", (subject_id,)).fetchone()
        subject_name = subject["name"] if subject else ""

        review_slots = max(0, round(limit * MISSED_REVIEW_FRACTION))
        missed_ids = _missed_chunk_ids(subject_id, review_slots)
        review_chunks: list[SampledChunk] = []
        if missed_ids:
            placeholders = ",".join("?" * len(missed_ids))
            rows = conn.execute(
                f"""
                SELECT c.id AS chunk_id, c.text, c.content_type, c.page_start, c.page_end,
                       c.line_start, c.line_end, sf.relative_path
                FROM chunks c JOIN source_files sf ON sf.id = c.source_file_id
                WHERE c.id IN ({placeholders})
                """,
                missed_ids,
            ).fetchall()
            review_chunks = [
                SampledChunk(
                    chunk_id=r["chunk_id"], text=r["text"], content_type=r["content_type"],
                    relative_path=r["relative_path"], page_start=r["page_start"], page_end=r["page_end"],
                    line_start=r["line_start"], line_end=r["line_end"],
                )
                for r in rows
            ]

    fresh_chunks = sample_subject_chunks(subject_id, limit=max(limit - len(review_chunks), limit // 2))
    seen_ids = {c.chunk_id for c in review_chunks}
    combined = review_chunks + [c for c in fresh_chunks if c.chunk_id not in seen_ids]
    combined = combined[:limit]

    return [StyledChunk(chunk=c, style=_style_for_chunk(c, subject_name), subject_id=subject_id) for c in combined]


def sample_chunks_across_subjects(limit: int = 16) -> list[StyledChunk]:
    """Stratified sampling for 'play all subjects': a few chunks per subject
    rather than pooling everything, so subjects with a lot of ingested code
    (e.g. student projects) don't drown out smaller subjects."""
    with get_connection() as conn:
        subjects = conn.execute(
            """
            SELECT s.id, s.name FROM subjects s
            JOIN source_files sf ON sf.subject_id = s.id
            JOIN chunks c ON c.source_file_id = sf.id
            GROUP BY s.id
            """
        ).fetchall()
    if not subjects:
        return []

    per_subject = max(1, limit // len(subjects))
    styled: list[StyledChunk] = []
    for subject in subjects:
        chunks = sample_subject_chunks(subject["id"], limit=per_subject)
        styled.extend(
            StyledChunk(chunk=c, style=_style_for_chunk(c, subject["name"]), subject_id=subject["id"])
            for c in chunks
        )
    return styled[:limit]


def ensure_general_culture_subject() -> int:
    """Get-or-create the virtual 'subject' that general cyber-knowledge
    questions attach to. Using a real subjects row (instead of a nullable
    FK) means it gets its own level/XP track and shows up in the normal
    subject picker for free, no schema change needed."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM subjects WHERE year = 'Général' AND name = ?",
            (GENERAL_CULTURE_SUBJECT_NAME,),
        ).fetchone()
        if row:
            return row["id"]
        cur = conn.execute(
            "INSERT INTO subjects (year, semester, name, root_path) VALUES ('Général', NULL, ?, '')",
            (GENERAL_CULTURE_SUBJECT_NAME,),
        )
        conn.commit()
        return cur.lastrowid


async def generate_general_knowledge_questions(n: int) -> list[GeneratedQuestion]:
    subject_id = ensure_general_culture_subject()
    picked = random.sample(GENERAL_CYBER_KNOWLEDGE, k=min(n, len(GENERAL_CYBER_KNOWLEDGE)))
    facts_block = "\n\n".join(f"[{i}] {item['anchor_fact']}" for i, item in enumerate(picked, start=1))

    provider = get_llm_provider()
    try:
        result = await provider.complete_structured(
            GENERAL_KNOWLEDGE_SYSTEM_PROMPT, facts_block, QUESTIONS_SCHEMA, fast=True
        )
    except Exception:
        return []

    questions: list[GeneratedQuestion] = []
    for raw in result.get("questions", []) if isinstance(result, dict) else []:
        if not _validate_question(raw):
            continue
        questions.append(
            GeneratedQuestion(
                prompt=raw["prompt"],
                options=raw["options"],
                correct_answer=raw["correct_answer"],
                difficulty=raw["difficulty"],
                style="general",
                source_chunk_id=0,  # not grounded in a course chunk
                subject_id=subject_id,
            )
        )
    return questions


def _build_prompt(styled_chunks: list[StyledChunk]) -> str:
    blocks = []
    for i, sc in enumerate(styled_chunks, start=1):
        blocks.append(f"[{i}] (style: {sc.style}) ({sc.chunk.relative_path})\n{sc.chunk.text[:1200]}")
    return "Extraits de cours :\n\n" + "\n\n".join(blocks)


def _validate_question(raw: dict) -> bool:
    options = raw.get("options") or []
    if len(options) != OPTIONS_PER_QUESTION:
        return False
    if len(set(options)) != OPTIONS_PER_QUESTION:
        return False
    if raw.get("correct_answer") not in options:
        return False
    if raw.get("difficulty") not in ("easy", "medium", "hard"):
        return False
    if not raw.get("prompt", "").strip():
        return False
    return True


async def _generate_batch(styled_chunks: list[StyledChunk]) -> list[dict]:
    if not styled_chunks:
        return []
    provider = get_llm_provider()
    prompt = _build_prompt(styled_chunks)
    try:
        result = await provider.complete_structured(
            QUESTION_SYSTEM_PROMPT, prompt, QUESTIONS_SCHEMA, fast=True
        )
    except Exception:
        return []
    return result.get("questions", []) if isinstance(result, dict) else []


async def generate_question_pool(subject_id: int | None) -> list[GeneratedQuestion]:
    subject_name = ""
    if subject_id is not None:
        with get_connection() as conn:
            row = conn.execute("SELECT name FROM subjects WHERE id = ?", (subject_id,)).fetchone()
        subject_name = row["name"] if row else ""

        if subject_name == GENERAL_CULTURE_SUBJECT_NAME:
            # Pure general-knowledge session: no course content needed at all.
            questions = await generate_general_knowledge_questions(QUESTIONS_PER_BATCH * NUM_BATCHES)
            if not questions:
                raise ValueError("La génération de questions de culture générale a échoué.")
            return questions

    total_slots = QUESTIONS_PER_BATCH * NUM_BATCHES
    general_slots = round(total_slots * GENERAL_KNOWLEDGE_FRACTION) if _is_security_subject(subject_name) else 0

    styled_chunks = (
        sample_chunks_for_subject(subject_id, limit=total_slots - general_slots)
        if subject_id is not None
        else sample_chunks_across_subjects(limit=total_slots - general_slots)
    )
    if len(styled_chunks) < MIN_CHUNKS_REQUIRED:
        raise ValueError(
            f"Pas assez de contenu ingéré pour générer une partie ({len(styled_chunks)} extraits disponibles, "
            f"{MIN_CHUNKS_REQUIRED} minimum)."
        )

    batches = [
        styled_chunks[i : i + QUESTIONS_PER_BATCH] for i in range(0, len(styled_chunks), QUESTIONS_PER_BATCH)
    ]
    tasks = [_generate_batch(batch) for batch in batches]
    general_task_index = None
    if general_slots > 0:
        general_task_index = len(tasks)
        tasks.append(generate_general_knowledge_questions(general_slots))

    results = await asyncio.gather(*tasks)

    questions: list[GeneratedQuestion] = []
    if general_task_index is not None:
        questions.extend(results[general_task_index])
        results = results[:general_task_index]

    for batch, raw_questions in zip(batches, results):
        for raw in raw_questions:
            if not _validate_question(raw):
                continue
            source_index = raw.get("source_index", 1)
            idx = max(0, min(len(batch) - 1, source_index - 1))
            source_chunk = batch[idx].chunk
            questions.append(
                GeneratedQuestion(
                    prompt=raw["prompt"],
                    options=raw["options"],
                    correct_answer=raw["correct_answer"],
                    difficulty=raw["difficulty"],
                    style=batch[idx].style,
                    source_chunk_id=source_chunk.chunk_id,
                    subject_id=batch[idx].subject_id,
                )
            )
    return questions


def persist_questions(questions: list[GeneratedQuestion], generation_model: str) -> list[int]:
    """Each question is stored under the subject its source chunk actually
    belongs to (not the session's subject_id, which may be null for
    'play all subjects') so `exercises.subject_id NOT NULL` always holds."""
    now = datetime.now(timezone.utc).isoformat()
    ids: list[int] = []
    with get_connection() as conn:
        for q in questions:
            cur = conn.execute(
                """
                INSERT INTO exercises
                    (subject_id, type, prompt, options_json, correct_answer, source_chunk_ids,
                     difficulty, created_at, generation_model, style)
                VALUES (?, 'mcq', ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    q.subject_id,
                    q.prompt,
                    json.dumps(q.options),
                    q.correct_answer,
                    json.dumps([q.source_chunk_id]),
                    q.difficulty,
                    now,
                    generation_model,
                    q.style,
                ),
            )
            ids.append(cur.lastrowid)
        conn.commit()
    return ids
