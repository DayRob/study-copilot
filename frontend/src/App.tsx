import { useState, type ReactNode } from 'react'
import Chat from './pages/Chat'
import Subjects from './pages/Subjects'
import KnowledgeGraph from './pages/KnowledgeGraph'
import Game from './pages/Game'

type Tab = 'chat' | 'subjects' | 'graph' | 'game'

const NAV_ITEMS: { id: Tab; label: string; icon: ReactNode }[] = [
  {
    id: 'chat',
    label: 'Questions',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.6" stroke="currentColor" className="w-4 h-4">
        <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.7 9.7 0 0 1-3.5-.65L3 20l1.05-3.15A7.9 7.9 0 0 1 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8Z" />
      </svg>
    ),
  },
  {
    id: 'subjects',
    label: 'Cours',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.6" stroke="currentColor" className="w-4 h-4">
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20M4 19.5A2.5 2.5 0 0 0 6.5 22H20V4a2 2 0 0 0-2-2H6.5A2.5 2.5 0 0 0 4 4.5v15Z" />
      </svg>
    ),
  },
  {
    id: 'graph',
    label: 'Carte',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.6" stroke="currentColor" className="w-4 h-4">
        <circle cx="6" cy="6" r="2.2" />
        <circle cx="18" cy="7" r="2.2" />
        <circle cx="9" cy="18" r="2.2" />
        <path strokeLinecap="round" d="M7.8 7.2 16 7M8 8.2l1 7.8" />
      </svg>
    ),
  },
  {
    id: 'game',
    label: 'Jeu',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" strokeWidth="1.6" stroke="currentColor" className="w-4 h-4">
        <path strokeLinecap="round" strokeLinejoin="round" d="M6 12h4m-2-2v4M15.5 13.5h.01M18 11h.01M8 8h8a4 4 0 0 1 4 4v0a4 4 0 0 1-4 4h-.5l-1.5 2h-4L8.5 16H8a4 4 0 0 1-4-4v0a4 4 0 0 1 4-4Z" />
      </svg>
    ),
  },
]

function App() {
  const [tab, setTab] = useState<Tab>('chat')

  return (
    <div className="h-screen flex flex-col sm:flex-row bg-paper">
      {/* Desktop console rail */}
      <aside className="hidden sm:flex w-56 shrink-0 bg-rail text-paper flex-col">
        <div className="px-5 py-5 border-b border-rail-line">
          <p className="font-data text-[11px] tracking-wide text-amber">STUDY::COPILOT</p>
          <p className="font-data text-[10px] text-paper/40 mt-0.5">cpe · 4a-5a · local</p>
        </div>

        <nav className="flex-1 px-3 py-4 flex flex-col gap-0.5">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              onClick={() => setTab(item.id)}
              className={`group flex items-center gap-2.5 px-3 py-2 rounded-sm text-sm font-body transition-colors relative ${
                tab === item.id ? 'text-paper' : 'text-paper/45 hover:text-paper/80'
              }`}
            >
              <span
                className={`absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-4 bg-amber transition-opacity ${
                  tab === item.id ? 'opacity-100' : 'opacity-0'
                }`}
              />
              <span className="font-data text-amber/70 text-xs">{tab === item.id ? '›' : ' '}</span>
              {item.icon}
              {item.label}
            </button>
          ))}
        </nav>

        <div className="px-5 py-4 border-t border-rail-line flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-signal animate-pulse" />
          <p className="font-data text-[10px] text-paper/40">ollama · llama3.1:8b</p>
        </div>
      </aside>

      {/* Mobile top bar */}
      <header className="sm:hidden flex items-center justify-between bg-rail text-paper px-4 py-3 shrink-0">
        <p className="font-data text-xs tracking-wide text-amber">STUDY::COPILOT</p>
        <nav className="flex gap-1">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              onClick={() => setTab(item.id)}
              aria-label={item.label}
              className={`p-2 rounded-sm transition-colors ${tab === item.id ? 'text-amber' : 'text-paper/40'}`}
            >
              {item.icon}
            </button>
          ))}
        </nav>
      </header>

      <main className="flex-1 min-w-0 min-h-0">
        {tab === 'chat' && <Chat />}
        {tab === 'subjects' && <Subjects />}
        {tab === 'graph' && <KnowledgeGraph />}
        {tab === 'game' && <Game />}
      </main>
    </div>
  )
}

export default App
