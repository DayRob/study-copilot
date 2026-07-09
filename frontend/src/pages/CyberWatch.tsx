import { useEffect, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { fetchCyberItems, fetchCyberStatus, startCyberSync, type CyberItem } from '../api/client'

export default function CyberWatch() {
  const queryClient = useQueryClient()
  const { data: items } = useQuery({ queryKey: ['cyber-items'], queryFn: fetchCyberItems })
  const [polling, setPolling] = useState(false)
  const { data: status } = useQuery({
    queryKey: ['cyber-status'],
    queryFn: fetchCyberStatus,
    refetchInterval: polling ? 1000 : false,
  })

  useEffect(() => {
    if (status?.status === 'running') setPolling(true)
    else if (polling) {
      setPolling(false)
      queryClient.invalidateQueries({ queryKey: ['cyber-items'] })
    }
  }, [status, polling, queryClient])

  async function handleSync() {
    await startCyberSync()
    setPolling(true)
  }

  const running = status?.status === 'running'
  const progressPct = status && status.total > 0 ? Math.round((status.current / status.total) * 100) : 0

  return (
    <div className="h-full overflow-y-auto grid-paper">
      <header className="bg-panel px-8 py-4 flex items-center justify-between border-b border-ink/8">
        <div>
          <p className="font-data text-[10px] tracking-wider text-ink-soft uppercase">Base de connaissances</p>
          <h1 className="font-display text-xl font-semibold text-ink">Veille Cyber</h1>
          <p className="font-data text-xs text-ink-soft mt-0.5">{items?.length ?? 0} fiches capitalisées</p>
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

      <div className="max-w-4xl mx-auto px-8 py-6 flex flex-col gap-3">
        {running && (
          <div className="bg-panel border border-ink/10 rounded px-4 py-3">
            <div className="flex justify-between font-data text-xs text-ink-soft mb-1.5">
              <span className="truncate max-w-md">{status?.current_item}</span>
              <span>{status?.current} / {status?.total}</span>
            </div>
            <div className="h-1 bg-ink/8 rounded-full overflow-hidden">
              <div className="h-full bg-amber rounded-full transition-all duration-300" style={{ width: `${progressPct}%` }} />
            </div>
          </div>
        )}

        {status?.status === 'failed' && (
          <div className="bg-alert-soft border border-alert/25 text-alert text-sm rounded px-4 py-3">
            Erreur de synchronisation : {status.error}
          </div>
        )}

        {items?.length === 0 && !running && (
          <div className="flex flex-col items-center justify-center text-center py-20 gap-3">
            <p className="text-ink-soft text-sm">Aucune fiche pour l'instant.</p>
            <button className="text-amber text-sm font-medium hover:underline" onClick={handleSync}>
              Lancer la première synchronisation
            </button>
          </div>
        )}

        {items?.map((item) => <ItemCard key={item.id} item={item} />)}
      </div>
    </div>
  )
}

function ItemCard({ item }: { item: CyberItem }) {
  const tags: string[] = JSON.parse(item.tags_json || '[]')
  return (
    <a
      href={item.url}
      target="_blank"
      rel="noreferrer"
      className="corner-marks bg-panel border border-ink/10 rounded px-4 py-3 flex flex-col gap-1.5 hover:border-amber/50 hover:shadow-sm transition-all"
    >
      <div className="flex items-center gap-2">
        <span className="font-data text-[11px] text-ink-soft bg-paper border border-ink/10 rounded px-2 py-0.5">
          {item.authority_source}
        </span>
        <p className="font-display font-medium text-ink text-sm">{item.title}</p>
      </div>
      <p className="text-xs text-ink-soft">{item.summary}</p>
      <div className="flex gap-1.5 flex-wrap">
        <Badge>{item.content_type}</Badge>
        <Badge>{item.technical_domain}</Badge>
        <Badge>{item.level}</Badge>
        {tags.map((tag) => <Badge key={tag}>{tag}</Badge>)}
      </div>
    </a>
  )
}

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-data text-[10px] text-ink-soft bg-paper border border-ink/10 rounded px-1.5 py-0.5">
      {children}
    </span>
  )
}
