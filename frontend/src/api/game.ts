import { readErrorDetail } from './client'

const BASE = '/api'

export type SessionStatus = 'generating' | 'active' | 'completed' | 'game_over' | 'failed'
export type DifficultyTier = 'easy' | 'medium' | 'hard'
export type QuestionStyle = 'concept' | 'bug' | 'vuln' | 'general'

export interface GameQuestion {
  exercise_id: number
  prompt: string
  options: string[]
  difficulty: DifficultyTier
  style: QuestionStyle
  index: number
  total: number
}

export interface GameSession {
  id: number
  subject_id: number | null
  status: SessionStatus
  score: number
  lives_remaining: number
  current_streak: number
  best_streak: number
  difficulty_tier: DifficultyTier
  questions_answered: number
  questions_correct: number
  xp_earned: number
  error: string | null
  question: GameQuestion | null
}

export interface AnswerResponse {
  is_correct: boolean
  correct_answer: string
  xp_awarded: number
  tier_changed: boolean
  session: GameSession
  next_question: GameQuestion | null
  session_ended: boolean
}

export interface PlayerProgress {
  subject_id: number | null
  subject_name: string
  xp: number
  level: number
}

export async function startGameSession(subjectId: number | null): Promise<{ session_id: number }> {
  const res = await fetch(`${BASE}/game/sessions`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ subject_id: subjectId }),
  })
  if (!res.ok) throw new Error(await readErrorDetail(res))
  return res.json()
}

export async function fetchGameSession(sessionId: number): Promise<GameSession> {
  const res = await fetch(`${BASE}/game/sessions/${sessionId}`)
  if (!res.ok) throw new Error(await readErrorDetail(res))
  return res.json()
}

export async function submitGameAnswer(
  sessionId: number,
  exerciseId: number,
  selectedOption: string,
): Promise<AnswerResponse> {
  const res = await fetch(`${BASE}/game/sessions/${sessionId}/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ exercise_id: exerciseId, selected_option: selectedOption }),
  })
  if (!res.ok) throw new Error(await readErrorDetail(res))
  return res.json()
}

export async function fetchPlayerProgress(): Promise<PlayerProgress[]> {
  const res = await fetch(`${BASE}/game/progress`)
  if (!res.ok) throw new Error(await readErrorDetail(res))
  return res.json()
}
