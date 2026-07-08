import { Fragment, useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { askQuestion, fetchSubjects, type Citation } from '../api/client'

interface Turn {
  question: string
  answer: string
  citations: Citation[]
  error: string | null
  pending: boolean
}

const SUGGESTIONS = [
  "Explique-moi les principes de l'architecture hexagonale",
  'Quelles sont les étapes clés du threat hunting ?',
  "Résume les bonnes pratiques vues en cours sur Terraform",
]

export default function Chat() {
  const { data: subjects } = useQuery({ queryKey: ['subjects'], queryFn: fetchSubjects })
  const [subjectId, setSubjectId] = useState<number | null>(null)
  const [question, setQuestion] = useState('')
  const [turns, setTurns] = useState<Turn[]>([])
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [turns])

  const loading = turns.length > 0 && turns[turns.length - 1].pending

  async function handleAsk(q?: string) {
    const text = (q ?? question).trim()
    if (!text || loading) return
    setQuestion('')
    setTurns((prev) => [...prev, { question: text, answer: '', citations: [], error: null, pending: true }])

    const update = (patch: Partial<Turn>) =>
      setTurns((prev) => prev.map((t, i) => (i === prev.length - 1 ? { ...t, ...patch } : t)))

    let fullAnswer = ''
    try {
      await askQuestion(
        text,
        subjectId,
        (delta) => {
          fullAnswer += delta
          update({ answer: fullAnswer })
        },
        (citations) => update({ citations, pending: false }),
      )
    } catch (err) {
      update({
        error: err instanceof Error ? err.message : "La question n'a pas pu aboutir.",
        pending: false,
      })
    }
  }

  return (
    <div className="h-full flex flex-col">
      <header className="bg-panel px-8 py-4 flex flex-wrap items-center justify-between gap-3 border-b border-ink/8">
        <div className="min-w-0">
          <p className="font-data text-[10px] tracking-wider text-ink-soft uppercase">Session active</p>
          <h1 className="font-display text-xl font-semibold text-ink truncate">Questions de cours</h1>
        </div>
        <select
          className="border border-ink/12 rounded px-3 py-2 text-sm bg-paper text-ink font-data focus:outline-none focus:ring-2 focus:ring-amber/30 shrink-0 max-w-[240px]"
          value={subjectId ?? ''}
          onChange={(e) => setSubjectId(e.target.value ? Number(e.target.value) : null)}
        >
          <option value="">tous les sujets</option>
          {subjects?.map((s) => (
            <option key={s.id} value={s.id}>
              {s.year}{s.semester ? ` · ${s.semester}` : ''} · {s.name}
            </option>
          ))}
        </select>
      </header>

      <div ref={scrollRef} className="flex-1 overflow-y-auto grid-paper px-8 py-6">
        <div className="max-w-3xl mx-auto flex flex-col gap-6">
          {turns.length === 0 && (
            <div className="flex flex-col items-center justify-center text-center py-20 gap-4">
              <p className="font-data text-3xl text-amber/70">[?]</p>
              <p className="text-ink-soft text-sm max-w-sm">
                Pose une question sur n'importe lequel de tes cours ingérés — chaque réponse cite ses sources exactes.
              </p>
              <div className="flex flex-col gap-2 w-full max-w-md">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => handleAsk(s)}
                    className="text-left text-sm px-4 py-2.5 rounded border border-ink/10 bg-panel hover:border-amber/50 hover:bg-amber-soft/40 transition-colors text-ink-soft"
                  >
                    <span className="font-data text-amber/60 mr-1.5">›</span>
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {turns.map((turn, i) => (
            <div key={i} className="flex flex-col gap-3">
              <div className="flex justify-end">
                <div className="bg-ink text-paper rounded-lg rounded-br-sm px-4 py-2.5 max-w-lg text-sm">
                  {turn.question}
                </div>
              </div>

              <div className="flex justify-start">
                <div className="corner-marks bg-panel border border-ink/10 rounded-lg rounded-bl-sm px-4 py-3 max-w-lg shadow-sm">
                  {turn.error ? (
                    <p className="text-sm text-alert">{turn.error}</p>
                  ) : (
                    <>
                      <p className="text-sm text-ink whitespace-pre-wrap leading-relaxed">
                        {turn.answer ? <AnnotatedAnswer text={turn.answer} /> : turn.pending && <TypingDots />}
                      </p>
                      {turn.citations.length > 0 && (
                        <div className="mt-3 pt-3 border-t border-dashed border-ink/12 flex flex-col gap-1">
                          {turn.citations.map((c) => (
                            <div key={c.marker} title={c.absolute_path} className="flex items-baseline gap-2 text-xs">
                              <span className="evidence-tag shrink-0">{c.marker}</span>
                              <span className="font-data text-ink-soft truncate">
                                {c.subject_name} · {c.relative_path.split(/[\\/]/).pop()}
                                {c.page_start ? ` · p.${c.page_start}` : ''}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-panel px-8 py-4 border-t border-ink/8">
        <div className="max-w-3xl mx-auto flex gap-3">
          <div className="flex-1 flex items-center border border-ink/12 rounded-lg px-4 focus-within:ring-2 focus-within:ring-amber/30 bg-paper">
            <span className="font-data text-amber/60 mr-2">›</span>
            <input
              className="flex-1 bg-transparent py-3 text-sm focus:outline-none placeholder:text-ink-soft/60"
              placeholder="pose une question sur tes cours..."
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAsk()}
              disabled={loading}
            />
          </div>
          <button
            className="bg-amber hover:bg-amber/90 text-paper px-5 py-3 rounded-lg text-sm font-medium disabled:opacity-40 transition-colors font-display"
            onClick={() => handleAsk()}
            disabled={loading || !question.trim()}
          >
            Envoyer
          </button>
        </div>
      </div>
    </div>
  )
}

function AnnotatedAnswer({ text }: { text: string }) {
  const parts = text.split(/(\[\d+\])/g)
  return (
    <>
      {parts.map((part, i) => {
        const match = part.match(/^\[(\d+)\]$/)
        if (!match) return <Fragment key={i}>{part}</Fragment>
        return (
          <span key={i} className="evidence-tag mx-0.5 align-middle">
            {match[1]}
          </span>
        )
      })}
    </>
  )
}

function TypingDots() {
  return (
    <span className="inline-flex gap-1 items-center h-4">
      <span className="w-1.5 h-1.5 rounded-full bg-amber/50 animate-bounce [animation-delay:-0.3s]" />
      <span className="w-1.5 h-1.5 rounded-full bg-amber/50 animate-bounce [animation-delay:-0.15s]" />
      <span className="w-1.5 h-1.5 rounded-full bg-amber/50 animate-bounce" />
    </span>
  )
}
