import { useState } from 'react'
import NavRail from './components/NavRail.jsx'
import TopHeader from './components/TopHeader.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import DraftPanel from './components/DraftPanel.jsx'
import EvidencePanel from './components/EvidencePanel.jsx'
import MatterSidebar from './components/MatterSidebar.jsx'
import SettingsDrawer from './components/SettingsDrawer.jsx'
import AuthPage from './pages/AuthPage.jsx'
import { listConversations, getConversation, deleteConversation } from './lib/conversationStore.js'
import { getSession, logout } from './lib/session.js'

function routeFromHash() {
  const h = window.location.hash
  if (h.startsWith('#/signup')) return 'signup'
  return 'login'
}

function extractPrefill() {
  try {
    const stored = sessionStorage.getItem('juryai.prefill')
    if (stored) {
      sessionStorage.removeItem('juryai.prefill')
      return stored
    }
    const params = new URLSearchParams(window.location.search)
    const fromQuery = params.get('q')
    if (fromQuery) return fromQuery
    const hashMatch = window.location.hash.match(/[?&]q=([^&]*)/)
    if (hashMatch) return decodeURIComponent(hashMatch[1].replace(/\+/g, ' '))
  } catch (e) {}
  return null
}

export default function App() {
  const [user, setUser] = useState(() => getSession())
  const [authMode, setAuthMode] = useState(() => routeFromHash())
  const [prefill, setPrefill] = useState(() => extractPrefill())

  const [mode, setMode] = useState('ask')
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [activeChunks, setActiveChunks] = useState([])
  const [activeQuestion, setActiveQuestion] = useState('')
  const [activeVerification, setActiveVerification] = useState(null)
  const [sourcePanelLoading, setSourcePanelLoading] = useState(false)
  const [evidenceCollapsed, setEvidenceCollapsed] = useState(false)
  const [mattersCollapsed, setMattersCollapsed] = useState(false)
  const [useWebSearch, setUseWebSearch] = useState(false)
  const [conversations, setConversations] = useState(() => listConversations())
  const [activeConversationId, setActiveConversationId] = useState(null)

  function handleAuthed() {
    setUser(getSession())
    window.location.hash = '#/app'
  }

  async function handleLogout() {
    await logout()
    setUser(null)
    window.location.hash = '#/login'
  }

  function handleSwitchAuthMode(next) {
    setAuthMode(next)
    window.location.hash = next === 'signup' ? '#/signup' : '#/login'
  }

  function handleSelectConversation(id) {
    setActiveChunks([])
    setActiveQuestion('')
    setActiveVerification(null)
    setPrefill(null)
    setActiveConversationId(id)
  }

  function handleNewConversation() {
    setActiveChunks([])
    setActiveQuestion('')
    setActiveVerification(null)
    setPrefill(null)
    setActiveConversationId(null)
  }

  function handleDeleteConversation(id) {
    deleteConversation(id)
    setConversations(listConversations())
    if (id === activeConversationId) handleNewConversation()
  }

  function handlePersistConversation() {
    setConversations(listConversations())
  }

  if (!user) {
    return (
      <AuthPage
        mode={authMode}
        onAuthed={handleAuthed}
        onSwitchMode={handleSwitchAuthMode}
      />
    )
  }

  const resumedConversation = activeConversationId ? getConversation(activeConversationId) : null
  const matterLabel = resumedConversation?.title || (mode === 'draft' ? 'Drafts' : 'New research')

  return (
    <div className="h-screen flex overflow-hidden">
      <NavRail
        mode={mode}
        onModeChange={setMode}
        onSettingsClick={() => setSettingsOpen(true)}
        user={user}
        onLogout={handleLogout}
      />

      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        <TopHeader
          matterLabel={matterLabel}
          activeTitle={mode === 'draft' ? null : resumedConversation?.title}
          onToggleMatters={() => setMattersCollapsed(c => !c)}
          mattersCollapsed={mattersCollapsed}
          onToggleEvidence={() => setEvidenceCollapsed(c => !c)}
          evidenceCollapsed={evidenceCollapsed}
          evidenceCount={activeChunks.length}
          useWebSearch={useWebSearch}
          onToggleWebSearch={() => setUseWebSearch(w => !w)}
          user={user}
        />

        <div className="flex-1 flex overflow-hidden relative">
          {mode === 'draft' ? (
            <DraftPanel />
          ) : (
            <>
              <MatterSidebar
                conversations={conversations}
                activeId={activeConversationId}
                onSelect={handleSelectConversation}
                onNew={handleNewConversation}
                onDelete={handleDeleteConversation}
                collapsed={mattersCollapsed}
              />

              <ChatPanel
                key={activeConversationId || 'new'}
                initialConversationId={activeConversationId}
                initialMessages={resumedConversation?.messages || []}
                initialQuestion={prefill}
                onPersist={handlePersistConversation}
                onNewSources={(chunks, question, verification) => {
                  setActiveChunks(chunks)
                  setActiveQuestion(question)
                  setActiveVerification(verification || null)
                  setSourcePanelLoading(false)
                  if (chunks.length > 0) setEvidenceCollapsed(false)
                }}
                onLoading={(q) => {
                  setActiveChunks([])
                  setActiveQuestion(q)
                  setActiveVerification(null)
                  setSourcePanelLoading(true)
                }}
                useWebSearch={useWebSearch}
                onToggleWebSearch={() => setUseWebSearch(w => !w)}
              />

              <EvidencePanel
                chunks={activeChunks}
                question={activeQuestion}
                isLoading={sourcePanelLoading}
                collapsed={evidenceCollapsed}
                verification={activeVerification}
              />
            </>
          )}
        </div>
      </div>

      {settingsOpen && (
        <SettingsDrawer
          onClose={() => setSettingsOpen(false)}
          useWebSearch={useWebSearch}
          onToggleWebSearch={() => setUseWebSearch(w => !w)}
          user={user}
          onLogout={handleLogout}
        />
      )}
    </div>
  )
}