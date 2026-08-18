import { useState, useEffect } from 'react'
import { Routes, Route, Navigate, useNavigate, useLocation, useParams } from 'react-router-dom'
import NavRail from './components/NavRail.jsx'
import TopHeader from './components/TopHeader.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import DraftPanel from './components/DraftPanel.jsx'
import EvidencePanel from './components/EvidencePanel.jsx'
import MatterSidebar from './components/MatterSidebar.jsx'
import SettingsDrawer from './components/SettingsDrawer.jsx'
import AuthPage from './pages/AuthPage.jsx'
import RunPage from './pages/RunPage.jsx'
import { listConversations, getConversation, deleteConversation } from './lib/conversationStore.js'
import { getSession, logout } from './lib/session.js'
import { useMediaQuery } from './lib/useMediaQuery.js'

const CONTENT_MODES = ['ask', 'draft', 'interact']

function extractPrefill(location) {
  try {
    const stored = sessionStorage.getItem('juryai.prefill')
    if (stored) {
      sessionStorage.removeItem('juryai.prefill')
      return stored
    }
    const fromQuery = new URLSearchParams(location.search).get('q')
    if (fromQuery) return fromQuery
  } catch (e) {}
  return null
}

// Preserve a `?q=` prefill (e.g. from the landing page's "ask this" links)
// across the login detour by stashing it where extractPrefill() already
// looks first — sessionStorage — since the query string itself won't
// survive the redirect to /login.
function UnauthedRedirect({ location }) {
  try {
    const q = new URLSearchParams(location.search).get('q')
    if (q) sessionStorage.setItem('juryai.prefill', q)
  } catch (e) {}
  return <Navigate to="/login" replace />
}

export default function App() {
  const [user, setUser] = useState(() => getSession())
  const navigate = useNavigate()
  const location = useLocation()

  async function handleLogout() {
    await logout()
    setUser(null)
    navigate('/login')
  }

  return (
    <Routes>
      <Route
        path="/login"
        element={user ? <Navigate to="/ask" replace /> : (
          <AuthPage mode="login" onAuthed={u => { setUser(u); navigate('/ask') }} onSwitchMode={m => navigate(m === 'signup' ? '/register' : '/login')} />
        )}
      />
      <Route
        path="/register"
        element={user ? <Navigate to="/ask" replace /> : (
          <AuthPage mode="signup" onAuthed={u => { setUser(u); navigate('/ask') }} onSwitchMode={m => navigate(m === 'signup' ? '/register' : '/login')} />
        )}
      />
      <Route
        path="/run/:runId"
        element={user ? <RunShell user={user} onLogout={handleLogout} /> : <Navigate to="/login" replace />}
      />
      <Route
        path="/:mode"
        element={user ? <AppShell user={user} onLogout={handleLogout} location={location} /> : <UnauthedRedirect location={location} />}
      />
      <Route path="/" element={<Navigate to={user ? '/ask' : '/login'} replace />} />
      <Route path="*" element={<Navigate to={user ? '/ask' : '/login'} replace />} />
    </Routes>
  )
}

function RunShell({ user, onLogout }) {
  const { runId } = useParams()
  const navigate = useNavigate()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [useWebSearch, setUseWebSearch] = useState(false)
  const isMobileNav = useMediaQuery('(max-width: 639px)')

  const navRail = (
    <NavRail
      mode="ask"
      onModeChange={m => navigate(`/${m}`)}
      onSettingsClick={() => setSettingsOpen(true)}
      user={user}
      onLogout={onLogout}
      onBack={() => navigate('/ask')}
      horizontal={isMobileNav}
    />
  )

  return (
    <div className={`h-dvh flex ${isMobileNav ? 'flex-col' : ''} overflow-hidden`}>
      {!isMobileNav && navRail}
      <div className="flex-1 flex flex-col overflow-hidden min-w-0 min-h-0">
        <TopHeader
          matterLabel="Research run"
          activeTitle={null}
          onToggleMatters={() => {}}
          mattersCollapsed
          onToggleEvidence={() => {}}
          evidenceCollapsed
          evidenceCount={0}
          useWebSearch={useWebSearch}
          onToggleWebSearch={() => setUseWebSearch(w => !w)}
          user={user}
          onBack={() => navigate('/ask')}
        />
        <div className="flex-1 flex overflow-hidden relative">
          <RunPage runId={runId} onBack={() => navigate('/ask')} />
        </div>
      </div>
      {isMobileNav && navRail}
      {settingsOpen && (
        <SettingsDrawer
          onClose={() => setSettingsOpen(false)}
          useWebSearch={useWebSearch}
          onToggleWebSearch={() => setUseWebSearch(w => !w)}
          user={user}
          onLogout={onLogout}
        />
      )}
    </div>
  )
}

function AppShell({ user, onLogout, location }) {
  const { mode: modeParam } = useParams()
  const navigate = useNavigate()

  // /settings has no content of its own — it overlays whichever content mode
  // (ask/draft) was last active, so remember it instead of losing the
  // background view when the drawer opens.
  const [lastMode, setLastMode] = useState('ask')
  useEffect(() => {
    if (CONTENT_MODES.includes(modeParam)) setLastMode(modeParam)
  }, [modeParam])

  const mode = CONTENT_MODES.includes(modeParam) ? modeParam : lastMode
  const settingsOpen = modeParam === 'settings'

  // Below 1024px, Matters and Evidence become slide-over overlays instead of
  // panels that push the chat column — three fixed-width columns plus chat
  // has no room to breathe under ~1000px, let alone on a phone.
  const isOverlayLayout = useMediaQuery('(max-width: 1023px)')
  const isMobileNav = useMediaQuery('(max-width: 639px)')

  const [prefill, setPrefill] = useState(() => extractPrefill(location))
  const [activeChunks, setActiveChunks] = useState([])
  const [activeQuestion, setActiveQuestion] = useState('')
  const [activeVerification, setActiveVerification] = useState(null)
  const [sourcePanelLoading, setSourcePanelLoading] = useState(false)
  const [evidenceCollapsed, setEvidenceCollapsed] = useState(true)
  const [mattersCollapsed, setMattersCollapsed] = useState(
    () => typeof window !== 'undefined' && window.matchMedia('(max-width: 1023px)').matches
  )
  const [useWebSearch, setUseWebSearch] = useState(false)
  const [conversations, setConversations] = useState(() => listConversations())
  const [activeConversationId, setActiveConversationId] = useState(null)

  function handleSelectConversation(id) {
    setActiveChunks([])
    setActiveQuestion('')
    setActiveVerification(null)
    setPrefill(null)
    setActiveConversationId(id)
    setEvidenceCollapsed(true)
    if (isOverlayLayout) setMattersCollapsed(true)
  }

  function handleNewConversation() {
    setActiveChunks([])
    setActiveQuestion('')
    setActiveVerification(null)
    setPrefill(null)
    setActiveConversationId(null)
    setEvidenceCollapsed(true)
    if (isOverlayLayout) setMattersCollapsed(true)
  }

  function handleDeleteConversation(id) {
    deleteConversation(id)
    setConversations(listConversations())
    if (id === activeConversationId) handleNewConversation()
  }

  function handlePersistConversation() {
    setConversations(listConversations())
  }

  const resumedConversation = activeConversationId ? getConversation(activeConversationId) : null
  const matterLabel = resumedConversation?.title || (mode === 'draft' ? 'Drafts' : 'New research')

  const navRail = (
    <NavRail
      mode={mode}
      onModeChange={m => navigate(`/${m}`)}
      onSettingsClick={() => navigate('/settings')}
      user={user}
      onLogout={onLogout}
      horizontal={isMobileNav}
    />
  )

  return (
    <div className={`h-dvh flex ${isMobileNav ? 'flex-col' : ''} overflow-hidden`}>
      {!isMobileNav && navRail}

      <div className="flex-1 flex flex-col overflow-hidden min-w-0 min-h-0">
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
                overlay={isOverlayLayout}
                onRequestClose={() => setMattersCollapsed(true)}
              />

              <ChatPanel
                key={activeConversationId || 'new'}
                mode={mode}
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
              />

              <EvidencePanel
                chunks={activeChunks}
                question={activeQuestion}
                isLoading={sourcePanelLoading}
                collapsed={evidenceCollapsed}
                verification={activeVerification}
                overlay={isOverlayLayout}
                onRequestClose={() => setEvidenceCollapsed(true)}
              />
            </>
          )}
        </div>
      </div>

      {isMobileNav && navRail}

      {settingsOpen && (
        <SettingsDrawer
          onClose={() => navigate(`/${mode}`)}
          useWebSearch={useWebSearch}
          onToggleWebSearch={() => setUseWebSearch(w => !w)}
          user={user}
          onLogout={onLogout}
        />
      )}
    </div>
  )
}
