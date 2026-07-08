import json
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.db.connection import get_connection
from app.game.difficulty import (
    STARTING_LIVES,
    AnswerResult,
    SessionState,
    apply_answer,
    level_from_xp,
    starting_tier_for_level,
)
from app.practice.generator import generate_question_pool, persist_questions

router = APIRouter(prefix="/game", tags=["game"])


class StartSessionRequest(BaseModel):
    subject_id: int | None = None


class AnswerRequest(BaseModel):
    exercise_id: int
    selected_option: str


def _player_level(conn, subject_id: int | None) -> int:
    row = conn.execute("SELECT xp FROM player_progress WHERE subject_id IS ?", (subject_id,)).fetchone()
    return level_from_xp(row["xp"]) if row else 1


def _upsert_progress(conn, subject_id: int | None, added_xp: int, now: str) -> None:
    if added_xp <= 0:
        return
    if subject_id is None:
        existing = conn.execute("SELECT xp FROM player_progress WHERE subject_id IS NULL").fetchone()
        new_xp = (existing["xp"] if existing else 0) + added_xp
        new_level = level_from_xp(new_xp)
        if existing:
            conn.execute(
                "UPDATE player_progress SET xp = ?, level = ?, updated_at = ? WHERE subject_id IS NULL",
                (new_xp, new_level, now),
            )
        else:
            conn.execute(
                "INSERT INTO player_progress (subject_id, xp, level, updated_at) VALUES (NULL, ?, ?, ?)",
                (new_xp, new_level, now),
            )
        return

    existing = conn.execute("SELECT xp FROM player_progress WHERE subject_id = ?", (subject_id,)).fetchone()
    new_xp = (existing["xp"] if existing else 0) + added_xp
    new_level = level_from_xp(new_xp)
    conn.execute(
        """
        INSERT INTO player_progress (subject_id, xp, level, updated_at) VALUES (?, ?, ?, ?)
        ON CONFLICT(subject_id) DO UPDATE SET xp = excluded.xp, level = excluded.level, updated_at = excluded.updated_at
        """,
        (subject_id, new_xp, new_level, now),
    )


async def _generate_session(session_id: int, subject_id: int | None) -> None:
    settings = get_settings()
    try:
        questions = await generate_question_pool(subject_id)
        if not questions:
            raise ValueError("Aucune question valide n'a pu être générée.")
        model_used = settings.ollama_model if settings.llm_provider == "ollama" else settings.llm_model
        exercise_ids = persist_questions(questions, model_used)
        with get_connection() as conn:
            conn.execute(
                "UPDATE game_sessions SET status = 'active', question_pool_json = ? WHERE id = ?",
                (json.dumps(exercise_ids), session_id),
            )
            conn.commit()
    except Exception as exc:
        with get_connection() as conn:
            conn.execute(
                "UPDATE game_sessions SET status = 'failed', error = ? WHERE id = ?",
                (str(exc), session_id),
            )
            conn.commit()


@router.post("/sessions")
def start_session(request: StartSessionRequest, background_tasks: BackgroundTasks):
    with get_connection() as conn:
        if request.subject_id is not None:
            subject = conn.execute("SELECT id FROM subjects WHERE id = ?", (request.subject_id,)).fetchone()
            if not subject:
                raise HTTPException(status_code=404, detail="Subject not found")
        level = _player_level(conn, request.subject_id)
        tier = starting_tier_for_level(level)
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            """
            INSERT INTO game_sessions (subject_id, status, started_at, lives_remaining, difficulty_tier)
            VALUES (?, 'generating', ?, ?, ?)
            """,
            (request.subject_id, now, STARTING_LIVES, tier),
        )
        conn.commit()
        session_id = cur.lastrowid

    background_tasks.add_task(_generate_session, session_id, request.subject_id)
    return {"session_id": session_id}


def _row_to_session(row) -> dict:
    return {
        "id": row["id"],
        "subject_id": row["subject_id"],
        "status": row["status"],
        "score": row["score"],
        "lives_remaining": row["lives_remaining"],
        "current_streak": row["current_streak"],
        "best_streak": row["best_streak"],
        "difficulty_tier": row["difficulty_tier"],
        "questions_answered": row["questions_answered"],
        "questions_correct": row["questions_correct"],
        "xp_earned": row["xp_earned"],
        "error": row["error"],
    }


def _current_question(conn, row) -> dict | None:
    if row["status"] != "active" or not row["question_pool_json"]:
        return None
    pool = json.loads(row["question_pool_json"])
    idx = row["current_index"]
    if idx >= len(pool):
        return None
    exercise = conn.execute(
        "SELECT id, prompt, options_json, difficulty, style FROM exercises WHERE id = ?",
        (pool[idx],),
    ).fetchone()
    if not exercise:
        return None
    return {
        "exercise_id": exercise["id"],
        "prompt": exercise["prompt"],
        "options": json.loads(exercise["options_json"]),
        "difficulty": exercise["difficulty"],
        "style": exercise["style"],
        "index": idx,
        "total": len(pool),
    }


@router.get("/sessions/{session_id}")
def get_session(session_id: int):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM game_sessions WHERE id = ?", (session_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Session not found")
        result = _row_to_session(row)
        result["question"] = _current_question(conn, row)
    return result


@router.post("/sessions/{session_id}/answer")
def submit_answer(session_id: int, request: AnswerRequest):
    with get_connection() as conn:
        session_row = conn.execute("SELECT * FROM game_sessions WHERE id = ?", (session_id,)).fetchone()
        if not session_row:
            raise HTTPException(status_code=404, detail="Session not found")
        if session_row["status"] != "active":
            raise HTTPException(status_code=400, detail="La session n'est pas active")

        # The submitted exercise must be the session's current expected question --
        # otherwise a stale/duplicate request (double-click, retried network call,
        # a second browser tab) could grade an arbitrary or already-answered
        # question and double-apply score/xp/lives. This check also makes the
        # endpoint naturally idempotent: once current_index advances, resubmitting
        # the same exercise_id no longer matches and is rejected.
        pool = json.loads(session_row["question_pool_json"] or "[]")
        current_index = session_row["current_index"]
        if current_index >= len(pool) or pool[current_index] != request.exercise_id:
            raise HTTPException(
                status_code=409,
                detail="Cette question ne correspond plus à la question courante de la session.",
            )

        exercise = conn.execute(
            "SELECT id, correct_answer, difficulty FROM exercises WHERE id = ?",
            (request.exercise_id,),
        ).fetchone()
        if not exercise:
            raise HTTPException(status_code=404, detail="Exercise not found")

        is_correct = request.selected_option == exercise["correct_answer"]
        state = SessionState(
            difficulty_tier=session_row["difficulty_tier"],
            current_streak=session_row["current_streak"],
            wrong_streak=session_row["wrong_streak"],
            lives_remaining=session_row["lives_remaining"],
            score=session_row["score"],
            xp_earned=session_row["xp_earned"],
            questions_answered=session_row["questions_answered"],
            questions_correct=session_row["questions_correct"],
            best_streak=session_row["best_streak"],
        )
        result: AnswerResult = apply_answer(state, is_correct, exercise["difficulty"])

        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO attempts (exercise_id, submitted_answer, is_correct, session_id, attempted_at, graded_by)
            VALUES (?, ?, ?, ?, ?, 'auto')
            """,
            (request.exercise_id, request.selected_option, int(is_correct), session_id, now),
        )

        new_index = current_index + 1
        pool_exhausted = new_index >= len(pool)

        new_status = "active"
        ended_at = None
        if result.game_over:
            new_status = "game_over"
            ended_at = now
        elif pool_exhausted:
            new_status = "completed"
            ended_at = now

        conn.execute(
            """
            UPDATE game_sessions SET
                status = ?, ended_at = ?, score = ?, lives_remaining = ?, current_streak = ?,
                wrong_streak = ?, best_streak = ?, difficulty_tier = ?, questions_answered = ?,
                questions_correct = ?, xp_earned = ?, current_index = ?
            WHERE id = ?
            """,
            (
                new_status, ended_at, result.state.score, result.state.lives_remaining,
                result.state.current_streak, result.state.wrong_streak, result.state.best_streak,
                result.state.difficulty_tier, result.state.questions_answered,
                result.state.questions_correct, result.state.xp_earned, new_index, session_id,
            ),
        )

        session_ended = new_status in ("game_over", "completed")
        if session_ended:
            _upsert_progress(conn, session_row["subject_id"], result.state.xp_earned, now)

        conn.commit()

        # Build the response from values already computed above instead of
        # re-querying game_sessions twice more -- everything needed is either
        # in `result.state` or was just written verbatim in the UPDATE.
        next_question = (
            _current_question(conn, {"status": new_status, "question_pool_json": session_row["question_pool_json"], "current_index": new_index})
            if new_status == "active"
            else None
        )
        session_dict = {
            "id": session_id,
            "subject_id": session_row["subject_id"],
            "status": new_status,
            "score": result.state.score,
            "lives_remaining": result.state.lives_remaining,
            "current_streak": result.state.current_streak,
            "best_streak": result.state.best_streak,
            "difficulty_tier": result.state.difficulty_tier,
            "questions_answered": result.state.questions_answered,
            "questions_correct": result.state.questions_correct,
            "xp_earned": result.state.xp_earned,
            "error": None,
        }

    return {
        "is_correct": is_correct,
        "correct_answer": exercise["correct_answer"],
        "xp_awarded": result.xp_awarded,
        "tier_changed": result.tier_changed,
        "session": session_dict,
        "next_question": next_question,
        "session_ended": session_ended,
    }


@router.get("/progress")
def get_progress():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT p.subject_id, p.xp, p.level, s.name AS subject_name
            FROM player_progress p
            LEFT JOIN subjects s ON s.id = p.subject_id
            """
        ).fetchall()
    return [
        {
            "subject_id": r["subject_id"],
            "subject_name": r["subject_name"] or "Global",
            "xp": r["xp"],
            "level": r["level"],
        }
        for r in rows
    ]
