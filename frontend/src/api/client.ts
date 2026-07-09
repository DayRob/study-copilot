export interface Subject {
  id: number
  year: string
  semester: string | null
  name: string
  file_count: number
  chunk_count: number
}

export interface GraphNode {
  id: string
  type: 'subject' | 'concept'
  label: string
  year?: string
  semester?: string | null
  explanation?: string
}

export interface GraphEdge {
  source: string
  target: string
}

export interface KnowledgeGraph {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface SubjectFile {
  id: number
  relative_path: string
  file_type: string
  last_ingested_at: string
  chunk_count: number
}

export interface Citation {
  marker: number
  subject_name: string
  relative_path: string
  absolute_path: string
  page_start: number | null
  page_end: number | null
  line_start: number | null
  line_end: number | null
}

export interface IngestStatus {
  status: 'idle' | 'running' | 'completed' | 'failed'
  current: number
  total: number
  current_file: string | null
  stats: Record<string, number> | null
  error: string | null
}

export interface CyberSyncStatus {
  status: 'idle' | 'running' | 'completed' | 'failed'
  current: number
  total: number
  current_item: string | null
  stats: Record<string, number> | null
  error: string | null
}

export interface CyberItem {
  id: number
  connector: string
  url: string
  title: string
  published_at: string | null
  fetched_at: string
  summary: string
  content_type: string
  technical_domain: string
  level: string
  authority_source: string
  referentiel: string | null
  tags_json: string
}

export interface OverviewExample {
  text: string
  relative_path: string
  page_start: number | null
  page_end: number | null
  line_start: number | null
  line_end: number | null
}

export interface OverviewResource {
  label: string
  url: string
}

export interface KeyTopic {
  concept: string
  explanation: string
}

export interface SubjectOverview {
  subject_id: number
  summary: string
  key_topics: KeyTopic[]
  examples: OverviewExample[]
  resources: OverviewResource[]
  generated_at: string
  cached: boolean
}

const BASE = '/api'

export async function fetchSubjects(): Promise<Subject[]> {
  const res = await fetch(`${BASE}/subjects`)
  if (!res.ok) throw new Error('Failed to fetch subjects')
  return res.json()
}

export async function fetchKnowledgeGraph(): Promise<KnowledgeGraph> {
  const res = await fetch(`${BASE}/knowledge-graph`)
  if (!res.ok) throw new Error('Failed to fetch knowledge graph')
  return res.json()
}

export async function fetchSubjectFiles(subjectId: number): Promise<SubjectFile[]> {
  const res = await fetch(`${BASE}/subjects/${subjectId}/files`)
  if (!res.ok) throw new Error('Failed to fetch subject files')
  return res.json()
}

export async function startIngestion(): Promise<void> {
  await fetch(`${BASE}/ingest/run`, { method: 'POST' })
}

export async function fetchIngestStatus(): Promise<IngestStatus> {
  const res = await fetch(`${BASE}/ingest/status`)
  if (!res.ok) throw new Error('Failed to fetch ingest status')
  return res.json()
}

export async function startCyberSync(): Promise<void> {
  await fetch(`${BASE}/cyber/sync`, { method: 'POST' })
}

export async function fetchCyberStatus(): Promise<CyberSyncStatus> {
  const res = await fetch(`${BASE}/cyber/status`)
  if (!res.ok) throw new Error('Failed to fetch cyber sync status')
  return res.json()
}

export async function fetchCyberItems(): Promise<CyberItem[]> {
  const res = await fetch(`${BASE}/cyber/items`)
  if (!res.ok) throw new Error('Failed to fetch cyber items')
  return res.json()
}

export async function readErrorDetail(res: Response): Promise<string> {
  try {
    const body = await res.json()
    return body.detail ?? `Erreur ${res.status}`
  } catch {
    return `Erreur ${res.status}`
  }
}

export async function fetchSubjectOverview(subjectId: number): Promise<SubjectOverview> {
  const res = await fetch(`${BASE}/subjects/${subjectId}/overview`)
  if (!res.ok) throw new Error(await readErrorDetail(res))
  return res.json()
}

export async function regenerateSubjectOverview(subjectId: number): Promise<SubjectOverview> {
  const res = await fetch(`${BASE}/subjects/${subjectId}/overview/regenerate`, { method: 'POST' })
  if (!res.ok) throw new Error(await readErrorDetail(res))
  return res.json()
}

export async function askQuestion(
  question: string,
  subjectId: number | null,
  onDelta: (text: string) => void,
  onDone: (citations: Citation[]) => void,
): Promise<void> {
  const res = await fetch(`${BASE}/qa/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, subject_id: subjectId, top_k: 10 }),
  })
  if (!res.ok || !res.body) throw new Error('Failed to ask question')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const events = buffer.split('\n\n')
    buffer = events.pop() ?? ''
    for (const event of events) {
      const line = event.trim()
      if (!line.startsWith('data: ')) continue
      const payload = JSON.parse(line.slice('data: '.length))
      if (payload.type === 'delta') onDelta(payload.text)
      if (payload.type === 'done') onDone(payload.citations)
      if (payload.type === 'error') throw new Error(payload.message)
    }
  }
}
