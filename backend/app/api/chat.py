import json
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.db.connection import get_connection
from app.llm.factory import get_llm_provider
from app.rag.qa import SYSTEM_PROMPT, build_user_prompt, citations_from_answer
from app.rag.retriever import retrieve

router = APIRouter(prefix="/qa", tags=["qa"])


class AskRequest(BaseModel):
    # Bounded so a crafted request can't blow up the KNN fetch (retrieve()
    # overfetches top_k * 5) or the prompt size sent to a paid LLM API.
    question: str = Field(min_length=1, max_length=4000)
    subject_id: int | None = None
    top_k: int = Field(default=10, ge=1, le=50)


@router.post("/ask")
async def ask(request: AskRequest) -> StreamingResponse:
    chunks = retrieve(request.question, top_k=request.top_k, subject_id=request.subject_id)
    user_prompt = build_user_prompt(request.question, chunks)
    provider = get_llm_provider()

    async def event_stream():
        full_text = ""
        try:
            async for delta in provider.stream(SYSTEM_PROMPT, user_prompt):
                full_text += delta
                yield f"data: {json.dumps({'type': 'delta', 'text': delta})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            return

        citations = citations_from_answer(full_text, chunks)

        with get_connection() as conn:
            conn.execute(
                """
                INSERT INTO qa_history (subject_id, question, answer, chunk_ids_used, asked_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    request.subject_id,
                    request.question,
                    full_text,
                    json.dumps([c.chunk_id for c in chunks]),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()

        payload = {
            "type": "done",
            "citations": [c.__dict__ for c in citations],
        }
        yield f"data: {json.dumps(payload)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
