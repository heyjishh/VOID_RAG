import { useState, useRef } from 'react'
import gsap from 'gsap'
import Navbar from './components/Navbar.jsx'
import ChatPanel from './components/ChatPanel.jsx'
import SourcePanel from './components/SourcePanel.jsx'
import SettingsDrawer from './components/SettingsDrawer.jsx'
import ConversationSidebar from './components/ConversationSidebar.jsx'
import CollapsedPanelPill from './components/CollapsedPanelPill.jsx'
import { listConversations, getConversation, deleteConversation } from './lib/conversationStore.js'

export default function App() {
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [activeChunks, setActiveChunks] = useState([])
  const [activeQuestion, setActiveQuestion] = useState('')
  const [activeVerification, setActiveVerification] = useState(null)
  const [sourcePanelLoading, setSourcePanelLoading] = useState(false)
  const [sourcePanelCollapsed, setSourcePanelCollapsed] = useState(true)
  const [historyCollapsed, setHistoryCollapsed] = useState(true)
  const [useWebSearch, setUseWebSearch] = useState(false)
  const [conversations, setConversations] = useState(() => listConversations())
  const [activeConversationId, setActiveConversationId] = useState(null)
  const pillRef = useRef(null)
  const historyPillRef = useRef(null)

  function handleToggleSources() {
    if (pillRef.current && sourcePanelCollapsed) {
      // Snap the pill out before uncollapsing
      gsap.to(pillRef.current, { x: 30, opacity: 0, duration: 0.15, ease: 'power2.in' })
    }
    setSourcePanelCollapsed(c => !c)
  }

  function handleToggleHistory() {
    if (historyPillRef.current && historyCollapsed) {
      gsap.to(historyPillRef.current, { x: -30, opacity: 0, duration: 0.15, ease: 'power2.in' })
    }
    setHistoryCollapsed(c => !c)
  }

  function handleSelectConversation(id) {
    setActiveChunks([])
    setActiveQuestion('')
    setActiveVerification(null)
    setActiveConversationId(id)
  }

  function handleNewConversation() {
    setActiveChunks([])
    setActiveQuestion('')
    setActiveVerification(null)
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

  const resumedConversation = activeConversationId ? getConversation(activeConversationId) : null

  return (
    <div className="h-screen flex flex-col overflow-hidden" style={{ background: 'var(--bg-main)' }}>
      <Navbar
        onSettingsClick={() => setSettingsOpen(true)}
        onToggleSources={handleToggleSources}
        sourcesCollapsed={sourcePanelCollapsed}
        sourcesCount={activeChunks.length}
        onToggleHistory={handleToggleHistory}
        historyCollapsed={historyCollapsed}
      />

      <div className="flex-1 flex overflow-hidden relative">
        <ConversationSidebar
          conversations={conversations}
          activeId={activeConversationId}
          onSelect={handleSelectConversation}
          onNew={handleNewConversation}
          onDelete={handleDeleteConversation}
          collapsed={historyCollapsed}
        />

        <ChatPanel
          key={activeConversationId || 'new'}
          initialConversationId={activeConversationId}
          initialMessages={resumedConversation?.messages || []}
          onPersist={handlePersistConversation}
          onNewSources={(chunks, question, verification) => {
            setActiveChunks(chunks)
            setActiveQuestion(question)
            setActiveVerification(verification || null)
            setSourcePanelLoading(false)
            if (chunks.length > 0) setSourcePanelCollapsed(false)
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

        <SourcePanel
          chunks={activeChunks}
          question={activeQuestion}
          isLoading={sourcePanelLoading}
          collapsed={sourcePanelCollapsed}
          verification={activeVerification}
        />

        {historyCollapsed && (
          <CollapsedPanelPill
            ref={historyPillRef}
            side="left"
            label="History"
            title="Show conversation history"
            onClick={handleToggleHistory}
          />
        )}

        {sourcePanelCollapsed && (
          <CollapsedPanelPill
            ref={pillRef}
            side="right"
            label={`Sources${activeChunks.length > 0 ? ` · ${activeChunks.length}` : ''}`}
            title={`Show sources${activeChunks.length > 0 ? ` (${activeChunks.length})` : ''}`}
            onClick={handleToggleSources}
          />
        )}
      </div>

      {settingsOpen && (
        <SettingsDrawer
          onClose={() => setSettingsOpen(false)}
          useWebSearch={useWebSearch}
          onToggleWebSearch={() => setUseWebSearch(w => !w)}
        />
      )}
    </div>
  )
}
