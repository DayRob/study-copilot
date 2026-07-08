import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { fetchSubjects } from '../api/client'
import {
  fetchGameSession,
  fetchPlayerProgress,
  startGameSession,
  submitGameAnswer,
  type GameSession,
} from '../api/game'

type Screen = 'landing' | 'generating' | 'playing' | 'ended'

const LOADING_MESSAGES = [
  "génération des questions à partir de tes cours...",
  'ça tourne en local, ça peut prendre 1 à 3 minutes...',
  'mélange de questions de cours et de culture cyber générale...',
  "presque prêt, encore un instant...",
]

const STYLE_LABEL: Record<string, string> = {
  concept: 'Notion',
  bug: 'Bug à trouver',
  vuln: 'Faille à identifier',
  general: 'Culture cyber',
}

const TIER_LABEL: Record<string, string> = { easy: 'Facile', medium: 'Moyen', hard: 'Difficile' }

export default function Game() {
  const { data: subjects } = useQuery({ queryKey: ['subjects'], queryFn: fetchSubjects })
  const { data: progress } = useQuery({ queryKey: ['game-progress'], queryFn: fetchPlayerProgress })

  const [screen, setScreen] = useState<Screen>('landing')
  const [sessionId, setSessionId] = useState<number | null>(null)
  const [session, setSession] = useState<GameSession | null>(null)
  const [loadingMsgIndex, setLoadingMsgIndex] = useState(0)
  const [selected, setSelected] = useState<string | null>(null)
  const [feedback, setFeedback] = useState<{ isCorrect: boolean; correctAnswer: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<number | null>(null)

  useEffect(() => {
    if (screen !== 'generating') return
    const id = window.setInterval(() => setLoadingMsgIndex((i) => (i + 1) % LOADING_MESSAGES.length), 4000)
    return () => window.clearInterval(id)
  }, [screen])

  useEffect(() => {
    if (screen !== 'generating' || sessionId === null) return
    pollRef.current = window.setInterval(async () => {
      try {
        const s = await fetchGameSession(sessionId)
        if (s.status === 'active') {
          setSession(s)
          setScreen('playing')
        } else if (s.status === 'failed') {
          setError(s.error ?? "La génération a échoué.")
          setScreen('landing')
        }
      } catch {
        // transient network hiccup, keep polling
      }
    }, 2000)
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
  }, [screen, sessionId])

  async function handlePlay(subjectId: number | null) {
    setError(null)
    try {
      const { session_id } = await startGameSession(subjectId)
      setSessionId(session_id)
      setScreen('generating')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Impossible de lancer la partie.')
    }
  }

  async function handleAnswer(option: string) {
    if (!session?.question || feedback || sessionId === null) return
    setSelected(option)
    try {
      const res = await submitGameAnswer(sessionId, session.question.exercise_id, option)
      setFeedback({ isCorrect: res.is_correct, correctAnswer: res.correct_answer })
      setTimeout(() => {
        setFeedback(null)
        setSelected(null)
        setSession(res.session)
        if (res.session_ended) {
          setScreen('ended')
        } else if (res.next_question) {
          setSession((prev) => (prev ? { ...prev, question: res.next_question } : prev))
        }
      }, 1400)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Réponse non prise en compte.')
    }
  }

  function reset() {
    setScreen('landing')
    setSession(null)
    setSessionId(null)
    setSelected(null)
    setFeedback(null)
  }

  return (
    <div className="h-full flex flex-col">
      <header className="bg-panel px-8 py-4 border-b border-ink/8">
        <p className="font-data text-[10px] tracking-wider text-ink-soft uppercase">Entraînement</p>
        <h1 className="font-display text-xl font-semibold text-ink">Mode Jeu</h1>
      </header>

      <div className="flex-1 overflow-y-auto grid-paper">
        {screen === 'landing' && (
          <LandingScreen
            subjects={subjects ?? []}
            progress={progress ?? []}
            error={error}
            onPlay={handlePlay}
          />
        )}

        {screen === 'generating' && (
          <div className="flex flex-col items-center justify-center h-full gap-4 px-8 text-center">
            <div className="flex gap-1.5">
              {[0, 1, 2].map((i) => (
                <span key={i} className="w-2 h-2 rounded-full bg-amber animate-bounce" style={{ animationDelay: `${i * 0.15}s` }} />
              ))}
            </div>
            <p className="font-data text-sm text-ink-soft max-w-sm">{LOADING_MESSAGES[loadingMsgIndex]}</p>
          </div>
        )}

        {screen === 'playing' && session?.question && (
          <PlayScreen
            session={session}
            selected={selected}
            feedback={feedback}
            onAnswer={handleAnswer}
          />
        )}

        {screen === 'ended' && session && <EndedScreen session={session} onReplay={reset} />}
      </div>
    </div>
  )
}

function LandingScreen({
  subjects,
  progress,
  error,
  onPlay,
}: {
  subjects: { id: number; name: string; year: string; semester: string | null; chunk_count: number }[]
  progress: { subject_id: number | null; xp: number; level: number }[]
  error: string | null
  onPlay: (subjectId: number | null) => void
}) {
  const progressBySubject = new Map(progress.map((p) => [p.subject_id, p]))
  const globalProgress = progressBySubject.get(null)

  return (
    <div className="max-w-3xl mx-auto px-8 py-6 flex flex-col gap-6">
      {error && (
        <div className="bg-alert-soft border border-alert/25 text-alert text-sm rounded px-4 py-3">{error}</div>
      )}

      <div className="corner-marks bg-panel border border-ink/10 rounded px-5 py-4 flex items-center justify-between">
        <div>
          <p className="font-data text-[10px] tracking-wider text-ink-soft uppercase">Progression globale</p>
          <p className="font-display text-lg font-semibold text-ink">Niveau {globalProgress?.level ?? 1}</p>
        </div>
        <button
          onClick={() => onPlay(null)}
          className="bg-amber hover:bg-amber/90 text-paper px-5 py-2.5 rounded text-sm font-medium font-display"
        >
          Jouer (tous sujets)
        </button>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {subjects.map((s) => {
          const p = progressBySubject.get(s.id)
          const tooLight = s.chunk_count < 6
          return (
            <button
              key={s.id}
              onClick={() => onPlay(s.id)}
              disabled={tooLight}
              className="corner-marks text-left bg-panel border border-ink/10 rounded px-4 py-3 flex flex-col gap-1.5 hover:border-amber/50 hover:shadow-sm transition-all disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <p className="font-display font-medium text-ink text-sm">{s.name}</p>
              <p className="font-data text-[11px] text-ink-soft">
                {p ? `Niveau ${p.level} · ${p.xp} XP` : 'Pas encore joué'}
              </p>
              {tooLight && <p className="font-data text-[10px] text-alert">contenu insuffisant</p>}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function PlayScreen({
  session,
  selected,
  feedback,
  onAnswer,
}: {
  session: GameSession
  selected: string | null
  feedback: { isCorrect: boolean; correctAnswer: string } | null
  onAnswer: (option: string) => void
}) {
  const q = session.question!
  return (
    <div className="max-w-2xl mx-auto px-8 py-6 flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <div className="flex gap-1">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className={`w-3 h-3 rounded-sm ${i < session.lives_remaining ? 'bg-alert' : 'bg-ink/10'}`}
            />
          ))}
        </div>
        <div className="flex items-center gap-3 font-data text-xs text-ink-soft">
          <span>🔥 {session.current_streak}</span>
          <span>{session.score} pts</span>
          <span className="evidence-tag">{TIER_LABEL[session.difficulty_tier]}</span>
        </div>
      </div>

      <div className="h-1 bg-ink/8 rounded-full overflow-hidden">
        <div
          className="h-full bg-amber transition-all duration-300"
          style={{ width: `${(q.index / q.total) * 100}%` }}
        />
      </div>

      <div className="corner-marks bg-panel border border-ink/10 rounded px-6 py-6 flex flex-col gap-4">
        <span className="text-xs font-data text-signal bg-signal-soft border border-signal/20 rounded px-2 py-0.5 self-start">
          {STYLE_LABEL[q.style]}
        </span>
        <p className="text-base text-ink leading-relaxed whitespace-pre-wrap">{q.prompt}</p>

        <div className="flex flex-col gap-2">
          {q.options.map((option) => {
            const isSelected = selected === option
            const isCorrectOption = feedback && option === feedback.correctAnswer
            const isWrongSelected = feedback && isSelected && !feedback.isCorrect
            return (
              <button
                key={option}
                onClick={() => onAnswer(option)}
                disabled={!!feedback}
                className={`text-left px-4 py-3 rounded border text-sm transition-colors ${
                  isCorrectOption
                    ? 'border-signal bg-signal-soft text-signal'
                    : isWrongSelected
                      ? 'border-alert bg-alert-soft text-alert'
                      : 'border-ink/10 bg-paper text-ink hover:border-amber/40'
                }`}
              >
                {option}
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function EndedScreen({ session, onReplay }: { session: GameSession; onReplay: () => void }) {
  const accuracy = session.questions_answered > 0
    ? Math.round((session.questions_correct / session.questions_answered) * 100)
    : 0
  return (
    <div className="max-w-md mx-auto px-8 py-16 flex flex-col items-center text-center gap-4">
      <p className="font-data text-3xl text-amber">
        {session.status === 'game_over' ? '[game over]' : '[terminé]'}
      </p>
      <p className="font-display text-xl font-semibold text-ink">
        {session.status === 'game_over' ? 'Plus de vies !' : 'Pool de questions terminé'}
      </p>
      <div className="grid grid-cols-2 gap-3 w-full mt-2">
        <Stat label="XP gagné" value={`+${session.xp_earned}`} />
        <Stat label="Précision" value={`${accuracy}%`} />
        <Stat label="Meilleur streak" value={String(session.best_streak)} />
        <Stat label="Score" value={String(session.score)} />
      </div>
      <button
        onClick={onReplay}
        className="mt-4 bg-amber hover:bg-amber/90 text-paper px-5 py-2.5 rounded text-sm font-medium font-display"
      >
        Rejouer
      </button>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="corner-marks bg-panel border border-ink/10 rounded px-4 py-3">
      <p className="font-data text-[10px] tracking-wider text-ink-soft uppercase">{label}</p>
      <p className="font-display text-lg font-semibold text-ink">{value}</p>
    </div>
  )
}
