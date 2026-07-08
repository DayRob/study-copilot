import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  type SimulationNodeDatum,
} from 'd3-force'
import { fetchKnowledgeGraph, type GraphNode } from '../api/client'

interface SimNode extends SimulationNodeDatum {
  id: string
  type: 'subject' | 'concept'
  label: string
  explanation?: string
}

interface SimLink {
  source: string | SimNode
  target: string | SimNode
}

export default function KnowledgeGraph() {
  const { data, isLoading } = useQuery({ queryKey: ['knowledge-graph'], queryFn: fetchKnowledgeGraph })
  const circleRefs = useRef(new Map<string, SVGCircleElement>())
  const labelRefs = useRef(new Map<string, SVGTextElement>())
  const lineRefs = useRef<(SVGLineElement | null)[]>([])
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [search, setSearch] = useState('')
  const width = 860
  const height = 600

  const conceptsBySubject = useMemo(() => {
    const map = new Map<string, string[]>()
    if (!data) return map
    for (const edge of data.edges) {
      const list = map.get(edge.source) ?? []
      list.push(edge.target)
      map.set(edge.source, list)
    }
    return map
  }, [data])

  const subjectNodes = useMemo(() => data?.nodes.filter((n) => n.type === 'subject') ?? [], [data])

  const { nodes, links } = useMemo(() => {
    if (!data) return { nodes: [] as SimNode[], links: [] as SimLink[] }
    const nodeById = new Map(data.nodes.map((n) => [n.id, n]))
    const visibleIds = new Set<string>(subjectNodes.map((s) => s.id))
    for (const subjectId of expanded) {
      for (const conceptId of conceptsBySubject.get(subjectId) ?? []) visibleIds.add(conceptId)
    }
    const nodes: SimNode[] = [...visibleIds].map((id) => {
      const n = nodeById.get(id)!
      return { id: n.id, type: n.type, label: n.label, explanation: n.explanation }
    })
    const links: SimLink[] = data.edges
      .filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target) && expanded.has(e.source))
      .map((e) => ({ source: e.source, target: e.target }))
    return { nodes, links }
  }, [data, expanded, subjectNodes, conceptsBySubject])

  useEffect(() => {
    if (nodes.length === 0) return

    const simulation = forceSimulation<SimNode>(nodes)
      .force('charge', forceManyBody<SimNode>().strength((d) => (d.type === 'subject' ? -260 : -80)))
      .force('link', forceLink<SimNode, SimLink>(links).id((d) => d.id).distance(55))
      .force('center', forceCenter(width / 2, height / 2))
      .force('collide', forceCollide<SimNode>().radius((d) => (d.type === 'subject' ? 34 : 20)))

    simulation.on('tick', () => {
      for (const node of nodes) {
        const cx = node.x ?? 0
        const cy = node.y ?? 0
        circleRefs.current.get(node.id)?.setAttribute('cx', String(cx))
        circleRefs.current.get(node.id)?.setAttribute('cy', String(cy))
        const label = labelRefs.current.get(node.id)
        if (label) {
          label.setAttribute('x', String(cx))
          label.setAttribute('y', String(cy + (node.type === 'subject' ? 26 : 16)))
        }
      }
      links.forEach((link, i) => {
        const line = lineRefs.current[i]
        const source = link.source as SimNode
        const target = link.target as SimNode
        if (line) {
          line.setAttribute('x1', String(source.x ?? 0))
          line.setAttribute('y1', String(source.y ?? 0))
          line.setAttribute('x2', String(target.x ?? 0))
          line.setAttribute('y2', String(target.y ?? 0))
        }
      })
    })

    return () => {
      simulation.stop()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, links])

  function toggleExpand(node: SimNode) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(node.id)) next.delete(node.id)
      else next.add(node.id)
      return next
    })
    const full = data?.nodes.find((n) => n.id === node.id) ?? null
    setSelected(full)
  }

  function selectConcept(node: SimNode) {
    const full = data?.nodes.find((n) => n.id === node.id) ?? null
    setSelected(full)
  }

  const matches = (label: string) => search.trim().length > 0 && label.toLowerCase().includes(search.trim().toLowerCase())
  const hasSearch = search.trim().length > 0

  return (
    <div className="h-full flex flex-col">
      <header className="bg-panel px-8 py-4 border-b border-ink/8">
        <p className="font-data text-[10px] tracking-wider text-ink-soft uppercase">Vue d'ensemble</p>
        <h1 className="font-display text-xl font-semibold text-ink">Carte des connaissances</h1>
        <p className="text-sm text-ink-soft mt-1">
          Clique un sujet (ambre) pour révéler ses notions. Reclique pour les ranger.
        </p>
      </header>

      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 overflow-auto grid-paper relative">
          <div className="sticky top-0 z-10 bg-panel/90 backdrop-blur px-4 py-2.5 border-b border-ink/8 flex items-center gap-3">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="rechercher un sujet ou une notion..."
              className="flex-1 max-w-xs text-sm border border-ink/12 rounded px-3 py-1.5 bg-paper focus:outline-none focus:ring-2 focus:ring-amber/30"
            />
            <div className="flex items-center gap-3 font-data text-[11px] text-ink-soft">
              <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full inline-block" style={{ background: 'var(--color-amber)' }} /> sujet</span>
              <span className="flex items-center gap-1.5"><span className="w-2 h-2 rounded-full inline-block" style={{ background: 'var(--color-signal)' }} /> notion</span>
            </div>
            {expanded.size > 0 && (
              <button onClick={() => setExpanded(new Set())} className="font-data text-[11px] text-ink-soft hover:text-ink ml-auto">
                ↺ tout replier
              </button>
            )}
          </div>

          {isLoading && <p className="p-8 font-data text-sm text-ink-soft">chargement du graphe...</p>}

          <svg width={width} height={height} className="mx-auto">
            <g opacity={0.5}>
              {links.map((_link, i) => (
                <line
                  key={i}
                  ref={(el) => { lineRefs.current[i] = el }}
                  stroke="var(--color-ink)"
                  strokeOpacity={0.18}
                  strokeWidth={1}
                />
              ))}
            </g>
            <g>
              {nodes.map((node) => {
                const dimmed = hasSearch && !matches(node.label)
                const isExpanded = expanded.has(node.id)
                return (
                  <g key={node.id} opacity={dimmed ? 0.2 : 1} className="transition-opacity">
                    <circle
                      ref={(el) => {
                        if (el) circleRefs.current.set(node.id, el)
                        else circleRefs.current.delete(node.id)
                      }}
                      r={node.type === 'subject' ? 16 : 6}
                      fill={node.type === 'subject' ? 'var(--color-amber)' : 'var(--color-signal)'}
                      stroke={isExpanded ? 'var(--color-ink)' : 'var(--color-panel)'}
                      strokeWidth={isExpanded ? 2.5 : node.type === 'subject' ? 2 : 1.5}
                      className="cursor-pointer"
                      onClick={() => (node.type === 'subject' ? toggleExpand(node) : selectConcept(node))}
                    />
                    <text
                      ref={(el) => {
                        if (el) labelRefs.current.set(node.id, el)
                        else labelRefs.current.delete(node.id)
                      }}
                      textAnchor="middle"
                      className={`pointer-events-none select-none font-data ${node.type === 'subject' ? 'text-[11px] fill-ink font-medium' : 'text-[9px] fill-ink-soft'}`}
                    >
                      {node.label.length > 22 ? node.label.slice(0, 20) + '…' : node.label}
                    </text>
                  </g>
                )
              })}
            </g>
          </svg>
        </div>

        <aside className="w-72 shrink-0 border-l border-ink/8 bg-panel px-5 py-5 overflow-y-auto">
          {!selected && (
            <div className="flex flex-col gap-3 text-sm text-ink-soft">
              <p>Comment ça marche :</p>
              <ul className="list-disc list-inside flex flex-col gap-1.5">
                <li>Les points <span className="text-amber font-medium">ambre</span> sont tes sujets.</li>
                <li>Clique un sujet pour afficher ses notions (points <span className="text-signal font-medium">sarcelle</span>).</li>
                <li>Clique une notion pour lire son explication ici.</li>
                <li>Utilise la recherche pour repérer un mot précis.</li>
              </ul>
            </div>
          )}
          {selected && (
            <div className="flex flex-col gap-3">
              <div>
                <p className="font-data text-[10px] tracking-wider text-ink-soft uppercase">
                  {selected.type === 'subject' ? 'Sujet' : 'Notion'}
                </p>
                <p className="font-display text-lg font-semibold text-ink">{selected.label}</p>
              </div>
              {selected.explanation && (
                <p className="text-sm text-ink-soft leading-relaxed">{selected.explanation}</p>
              )}
              {selected.type === 'subject' && (
                <p className="font-data text-xs text-ink-soft">
                  {(conceptsBySubject.get(selected.id) ?? []).length} notions liées — clique le point pour {expanded.has(selected.id) ? 'les ranger' : 'les afficher'}.
                </p>
              )}
              <button
                onClick={() => setSelected(null)}
                className="font-data text-xs text-ink-soft hover:text-ink self-start mt-2"
              >
                ↺ fermer
              </button>
            </div>
          )}
        </aside>
      </div>
    </div>
  )
}
