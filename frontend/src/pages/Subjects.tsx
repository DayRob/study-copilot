import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchIngestStatus, fetchSubjects, startIngestion, type Subject } from '../api/client'
import SubjectDrawer from '../components/SubjectDrawer'

export default function Subjects() {
  const queryClient = useQueryClient()
  const { data: subjects } = useQuery({ queryKey: ['subjects'], queryFn: fetchSubjects })
  const [polling, setPolling] = useState(false)
  const [selected, setSelected] = useState<Subject | null>(null)
  const { data: status } = useQuery({
    queryKey: ['ingest-status'],
    queryFn: fetchIngestStatus,
    refetchInterval: polling ? 1000 : false,
  })

  useEffect(() => {
    if (status?.status === 'running') setPolling(true)
    else if (polling) {
      setPolling(false)
      queryClient.invalidateQueries({ queryKey: ['subjects'] })
    }
  }, [status, polling, queryClient])

  async function handleSync() {
    await startIngestion()
    setPolling(true)
  }

  const running = status?.status === 'running'
  const progressPct = status && status.total > 0 ? Math.round((status.current / status.total) * 100) : 0

  const grouped = groupByYear(subjects ?? [])
  const totalFiles = subjects?.reduce((acc, s) => acc + s.file_count, 0) ?? 0
  const totalChunks = subjects?.reduce((acc, s) => acc + s.chunk_count, 0) ?? 0

  return (
    <div className="h-full overflow-y-auto grid-paper">
      <header className="bg-panel px-8 py-4 flex items-center justify-between border-b border-ink/8">
        <div>
          <p className="font-data text-[10px] tracking-wider text-ink-soft uppercase">Base de connaissances</p>
          <h1 className="font-display text-xl font-semibold text-ink">Cours ingérés</h1>
          <p className="font-data text-xs text-ink-soft mt-0.5">
            {subjects?.length ?? 0} sujets · {totalFiles} fichiers · {totalChunks} passages
          </p>
        </div>
        <button
          className="bg-amber hover:bg-amber/90 text-paper px-4 py-2.5 rounded text-sm font-medium disabled:opacity-50 transition-colors flex items-center gap-2 whitespace-nowrap shrink-0 font-display"
          onClick={handleSync}
          disabled={running}
        >
          {running && (
            <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8V0C5.373 0 0 5.373 0 12h4Z" />
            </svg>
          )}
          {running ? 'Synchronisation...' : 'Sync now'}
        </button>
      </header>

      <div className="max-w-4xl mx-auto px-8 py-6 flex flex-col gap-6">
        {running && (
          <div className="bg-panel border border-ink/10 rounded px-4 py-3">
            <div className="flex justify-between font-data text-xs text-ink-soft mb-1.5">
              <span className="truncate max-w-md">{status?.current_file}</span>
              <span>{status?.current} / {status?.total}</span>
            </div>
            <div className="h-1 bg-ink/8 rounded-full overflow-hidden">
              <div
                className="h-full bg-amber rounded-full transition-all duration-300"
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>
        )}

        {status?.status === 'failed' && (
          <div className="bg-alert-soft border border-alert/25 text-alert text-sm rounded px-4 py-3">
            Erreur d'ingestion : {status.error}
          </div>
        )}

        {Object.entries(grouped).map(([year, semesters]) => (
          <section key={year} className="flex flex-col gap-3">
            <h2 className="font-data text-xs font-semibold text-ink-soft uppercase tracking-widest">{year}</h2>
            {Object.entries(semesters).map(([semester, items]) => (
              <div key={semester} className="flex flex-col gap-2">
                {semester !== 'null' && (
                  <p className="font-data text-[11px] text-ink-soft/70">{semester}</p>
                )}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {items.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => setSelected(s)}
                      className="corner-marks text-left bg-panel border border-ink/10 rounded px-4 py-3 flex flex-col gap-2 hover:border-amber/50 hover:shadow-sm transition-all"
                    >
                      <p className="font-display font-medium text-ink text-sm">{s.name}</p>
                      <div className="flex gap-2">
                        <Badge>{s.file_count} fichiers</Badge>
                        <Badge>{s.chunk_count} chunks</Badge>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </section>
        ))}

        {subjects?.length === 0 && !running && (
          <div className="flex flex-col items-center justify-center text-center py-20 gap-3">
            <p className="text-ink-soft text-sm">Aucun sujet ingéré pour l'instant.</p>
            <button
              className="text-amber text-sm font-medium hover:underline"
              onClick={handleSync}
            >
              Lancer la première synchronisation
            </button>
          </div>
        )}
      </div>

      <SubjectDrawer subject={selected} onClose={() => setSelected(null)} />
    </div>
  )
}

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-data text-[11px] text-ink-soft bg-paper border border-ink/10 rounded px-2 py-0.5">
      {children}
    </span>
  )
}

function groupByYear(subjects: Subject[]) {
  const result: Record<string, Record<string, Subject[]>> = {}
  for (const s of subjects) {
    result[s.year] ??= {}
    const key = s.semester ?? 'null'
    result[s.year][key] ??= []
    result[s.year][key].push(s)
  }
  return result
}
