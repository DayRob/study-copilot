from dataclasses import dataclass

from app.rag.retriever import RetrievedChunk

SYSTEM_PROMPT = (
    "Tu es un assistant pedagogique qui aide un etudiant a reviser ses cours. "
    "Reponds UNIQUEMENT a partir des extraits de cours fournis ci-dessous, dans la langue de la question. "
    "Cite tes sources en utilisant des marqueurs [n] correspondant au numero de l'extrait utilise. "
    "Si les extraits ne permettent pas de repondre, dis-le clairement plutot que d'inventer."
)


@dataclass
class Citation:
    marker: int
    subject_name: str
    relative_path: str
    absolute_path: str
    page_start: int | None
    page_end: int | None
    line_start: int | None
    line_end: int | None


def format_context(chunks: list[RetrievedChunk]) -> str:
    blocks = []
    for i, chunk in enumerate(chunks, start=1):
        location = ""
        if chunk.page_start:
            location = f"page {chunk.page_start}"
            if chunk.page_end and chunk.page_end != chunk.page_start:
                location += f"-{chunk.page_end}"
        elif chunk.line_start:
            location = f"lignes {chunk.line_start}-{chunk.line_end}"
        header = f"[{i}] ({chunk.subject_name} / {chunk.relative_path}{', ' + location if location else ''})"
        blocks.append(f"{header}\n{chunk.text}")
    return "\n\n".join(blocks)


def build_user_prompt(question: str, chunks: list[RetrievedChunk]) -> str:
    context = format_context(chunks)
    return f"Extraits de cours :\n\n{context}\n\nQuestion : {question}"


def citations_from_answer(answer: str, chunks: list[RetrievedChunk]) -> list[Citation]:
    import re

    used_markers = {int(m) for m in re.findall(r"\[(\d+)\]", answer)}
    return [
        Citation(
            marker=i,
            subject_name=c.subject_name,
            relative_path=c.relative_path,
            absolute_path=c.absolute_path,
            page_start=c.page_start,
            page_end=c.page_end,
            line_start=c.line_start,
            line_end=c.line_end,
        )
        for i, c in enumerate(chunks, start=1)
        if i in used_markers
    ]
