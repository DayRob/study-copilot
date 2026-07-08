import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  fetchSubjectOverview,
  regenerateSubjectOverview,
  type Subject,
  type SubjectOverview,
} from '../api/client'

interface Props {
  subject: Subject | null
  onClose: () => void
}

export default function SubjectDrawer({ subject, onClose }: Props) {
  const queryClient = useQueryClient()
  const subjectId = subject?.id ?? null

  const { data, isLoading, isError, error } = useQuery<SubjectOverview, Error>({
    queryKey: ['subject-overview', subjectId],
    queryFn: () => fetchSubjectOverview(subjectId!),
    enabled: subjectId !== null,
    retry: false,
  })

  const regenerate = useMutation({
    mutationFn: () => regenerateSubjectOverview(subjectId!),
    onSuccess: (overview) => {
      queryClient.setQueryData(['subject-overview', subjectId], overview)
    },
  })

  if (!subject) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-ink/25" onClick={onClose} />

      <div className="relative w-full max-w-lg bg-paper h-full shadow-xl flex flex-col animate-[slide-in_0.2s_ease-out]">
        <div className="border-b border-ink/10 bg-panel px-6 py-4 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="font-data text-[10px] tracking-wider text-ink-soft uppercase">
              {subject.year}{subject.semester ? ` · ${subject.semester}` : ''}
            </p>
            <h2 className="font-display text-lg font-semibold text-ink truncate">{subject.name}</h2>
          </div>
          <button
            onClick={onClose}
            aria-label="Fermer"
            className="text-ink-soft hover:text-ink p-1 shrink-0"
          >
            <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.8" stroke="currentColor" className="w-5 h-5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5 flex flex-col gap-6">
          {isLoading && <OverviewSkeleton />}

          {isError && (
            <div className="bg-amber-soft border border-amber/30 text-ink text-sm rounded px-4 py-3">
              {error.message}
            </div>
          )}

          {data && (
            <>
              <section>
                <p className="font-data text-[10px] tracking-wider text-ink-soft uppercase mb-1.5">Résumé</p>
                <p className="text-sm text-ink leading-relaxed whitespace-pre-wrap">{data.summary}</p>
              </section>

              {data.key_topics.length > 0 && (
                <section>
                  <p className="font-data text-[10px] tracking-wider text-ink-soft uppercase mb-2">
                    Notions clés
                  </p>
                  <div className="flex flex-col gap-2.5">
                    {data.key_topics.map((topic) => (
                      <div key={topic.concept} className="border-l-2 border-signal pl-3">
                        <p className="text-sm font-semibold text-signal">{topic.concept}</p>
                        <p className="text-sm text-ink-soft leading-relaxed mt-0.5">{topic.explanation}</p>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {data.examples.length > 0 && (
                <section>
                  <p className="font-data text-[10px] tracking-wider text-ink-soft uppercase mb-2">
                    Pièces à l'appui
                  </p>
                  <div className="flex flex-col gap-2">
                    {data.examples.map((ex, i) => (
                      <div key={i} className="corner-marks border border-ink/10 rounded px-4 py-3 bg-panel">
                        <div className="flex items-baseline gap-2 mb-1.5">
                          <span className="evidence-tag">{i + 1}</span>
                        </div>
                        <p className="text-sm text-ink whitespace-pre-wrap line-clamp-6">{ex.text}</p>
                        <p className="font-data text-[11px] text-ink-soft mt-2">
                          {ex.relative_path.split(/[\\/]/).pop()}
                          {ex.page_start ? ` · p.${ex.page_start}` : ''}
                          {ex.line_start ? ` · l.${ex.line_start}-${ex.line_end}` : ''}
                        </p>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {data.resources.length > 0 && (
                <section>
                  <p className="font-data text-[10px] tracking-wider text-ink-soft uppercase mb-2">
                    Ressources
                  </p>
                  <div className="flex flex-col gap-1.5">
                    {data.resources.map((r) => (
                      <a
                        key={r.url}
                        href={r.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-sm text-signal hover:underline flex items-center gap-1.5"
                      >
                        <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.8" stroke="currentColor" className="w-3.5 h-3.5 shrink-0">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4M14 4h6v6M10 14 20 4" />
                        </svg>
                        {r.label}
                      </a>
                    ))}
                  </div>
                </section>
              )}

              <button
                onClick={() => regenerate.mutate()}
                disabled={regenerate.isPending}
                className="font-data text-xs text-ink-soft hover:text-ink self-start disabled:opacity-50"
              >
                {regenerate.isPending ? 'régénération...' : '↻ régénérer la fiche'}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function OverviewSkeleton() {
  return (
    <div className="flex flex-col gap-4 animate-pulse">
      <div className="h-3 bg-ink/8 rounded w-full" />
      <div className="h-3 bg-ink/8 rounded w-5/6" />
      <div className="h-3 bg-ink/8 rounded w-3/4" />
      <div className="flex gap-2 mt-2">
        <div className="h-6 w-20 bg-ink/8 rounded" />
        <div className="h-6 w-24 bg-ink/8 rounded" />
        <div className="h-6 w-16 bg-ink/8 rounded" />
      </div>
      <p className="font-data text-xs text-ink-soft mt-2">
        génération de la fiche en cours (peut prendre une minute en local)...
      </p>
    </div>
  )
}
