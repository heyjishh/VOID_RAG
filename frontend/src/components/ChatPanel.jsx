import { useState, useRef, useEffect } from 'react'
import gsap from 'gsap'
import { BookOpen, Wand2, Sparkles, ChevronDown, Paperclip, X } from 'lucide-react'
import { streamChat, analyzeQuestion, improveQuestion, interactApi } from '../lib/api.js'
import { deriveTitle, upsertConversation, listConversations } from '../lib/conversationStore.js'
import { refineDraft } from '../lib/refinePrompt.js'
import { deriveFollowups } from '../lib/followups.js'
import { prefersReducedMotion } from '../lib/motion.js'
import LegalFlick from './LegalFlick.jsx'
import MessageBubble from './MessageBubble.jsx'
import ReasoningTimeline from './ReasoningTimeline.jsx'
import PromptLibrary from './PromptLibrary.jsx'
import FollowUpSuggestions from './FollowUpSuggestions.jsx'
import SourcePicker from './SourcePicker.jsx'

const SUGGESTION_CHIPS = [
  'Punishment under Section 302 IPC?',
  'Bail provisions under CrPC?',
  'Fundamental rights under Article 19?',
  'What constitutes hearsay under the Evidence Act?',
]

export default function ChatPanel({
  mode = 'ask',
  onNewSources,
  onLoading,
  useWebSearch,
  initialConversationId = null,
  initialMessages = [],
  initialQuestion = null,
  onPersist,
}) {
  const [messages, setMessages] = useState(initialMessages)
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [convId, setConvId] = useState(() => initialConversationId || (mode === 'interact' ? crypto.randomUUID() : null))
  const [reasoningSteps, setReasoningSteps] = useState([])
  const [reasoningExpanded, setReasoningExpanded] = useState(true)
  const [promptLibraryOpen, setPromptLibraryOpen] = useState(false)
  const [outputFormat, setOutputFormat] = useState('CREAC')
  const [selectedSources, setSelectedSources] = useState([])
  const [queryAnalysis, setQueryAnalysis] = useState(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [attachMenuOpen, setAttachMenuOpen] = useState(false)
  const [attachedFiles, setAttachedFiles] = useState([])
  const [reusePicker, setReusePicker] = useState(false)
  const [reuseSourceId, setReuseSourceId] = useState(null)
  const [reuseDocs, setReuseDocs] = useState([])
  const bottomRef = useRef(null)
  const inputRef = useRef(null)
  const fileInputRef = useRef(null)
  const autoRanRef = useRef(false)
  const messagesRef = useRef(messages)
  useEffect(() => { messagesRef.current = messages }, [messages])

  useEffect(() => {
    if (mode !== 'interact' || !convId) return
    interactApi.listDocuments(convId)
      .then(res => setAttachedFiles(res.documents || []))
      .catch(() => {})
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  function handleFileSelected(e) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    interactApi.uploadDocument(convId, file)
      .then(res => setAttachedFiles(prev => [...prev, res.document]))
      .catch(() => {})
    setAttachMenuOpen(false)
  }

  function handleRemoveFile(fileHash) {
    setAttachedFiles(prev => prev.filter(d => d.file_hash !== fileHash))
    interactApi.deleteDocument(convId, fileHash).catch(() => {})
  }

  function openReusePicker() {
    setReusePicker(true)
    setReuseSourceId(null)
    setReuseDocs([])
  }

  function handlePickReuseSource(sourceId) {
    setReuseSourceId(sourceId)
    interactApi.listDocuments(sourceId)
      .then(res => setReuseDocs(res.documents || []))
      .catch(() => setReuseDocs([]))
  }

  function handleBackToSources() {
    setReuseSourceId(null)
    setReuseDocs([])
  }

  function handleReuseDocument(fileHash) {
    interactApi.reuseDocument(convId, reuseSourceId, fileHash)
      .then(res => setAttachedFiles(prev => [...prev, res.document]))
      .catch(() => {})
    setAttachMenuOpen(false)
    setReusePicker(false)
  }

  function closeAttachMenu() {
    setAttachMenuOpen(false)
    setReusePicker(false)
  }

  function persist(finalMessages, id) {
    if (!onPersist || !id) return
    const firstUser = finalMessages.find(m => m.role === 'user')
    const record = upsertConversation({ id, title: deriveTitle(firstUser?.content), messages: finalMessages })
    onPersist(record)
  }

  function handleRefine(question) {
    setInput(refineDraft(question))
    inputRef.current?.focus()
  }

  function handleRefineDraft() {
    if (!input.trim()) return
    setInput(refineDraft(input))
    inputRef.current?.focus()
  }

  async function handleAnalyze() {
    if (!input.trim() || analyzing) return
    setAnalyzing(true)
    setQueryAnalysis(null)
    try {
      const data = await analyzeQuestion(input.trim())
      setQueryAnalysis(data)
    } catch (err) {
      console.error('Analysis failed:', err)
    } finally {
      setAnalyzing(false)
    }
  }

  async function handleImprove() {
    if (!input.trim() || analyzing) return
    setAnalyzing(true)
    setQueryAnalysis(null)
    try {
      const data = await improveQuestion(input.trim())
      if (data.improved_question && data.improved_question !== input.trim()) {
        setInput(data.improved_question)
      }
      setQueryAnalysis(data.analysis || data)
    } catch (err) {
      console.error('Improve failed:', err)
    } finally {
      setAnalyzing(false)
    }
  }

  function handleInsertTemplate(template) {
    setInput(template)
    setPromptLibraryOpen(false)
    inputRef.current?.focus()
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, reasoningSteps])

  function handleSubmit(e) {
    e.preventDefault()
    send(input)
  }

  useEffect(() => {
    if (autoRanRef.current || !initialQuestion?.trim() || messages.length > 0) return
    autoRanRef.current = true
    send(initialQuestion.trim())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function send(rawQuestion) {
    const q = rawQuestion.trim()
    if (!q || loading) return

    setInput('')
    setLoading(true)
    setReasoningSteps([])
    setReasoningExpanded(true)
    onLoading(q)

    const userMsgId = Date.now()
    const assistantMsgId = Date.now() + 1

    setMessages(prev => [
      ...prev,
      { role: 'user', content: q, id: userMsgId },
      { role: 'assistant', id: assistantMsgId, streaming: true, content: '', source_chunks: [], question: q },
    ])

    let accumulatedChunks = []
    let accumulatedSteps = []

    const callbacks = {
      onReasoningStep: (step) => {
        accumulatedSteps = [...accumulatedSteps, step]
        setReasoningSteps(accumulatedSteps)
      },
      onSourceChunk: (chunk) => {
        accumulatedChunks = [...accumulatedChunks, chunk]
        onNewSources(accumulatedChunks, q, null)
      },
      onAnswerToken: ({ token }) => {
        setMessages(prev => {
          const msgs = [...prev]
          const last = msgs[msgs.length - 1]
          if (last?.id === assistantMsgId && last.streaming) {
            msgs[msgs.length - 1] = { ...last, content: last.content + (token || '') }
          }
          return msgs
        })
      },
      onGate: (data) => {
        setMessages(prev => {
          const msgs = [...prev]
          const last = msgs[msgs.length - 1]
          if (last?.id === assistantMsgId) {
            msgs[msgs.length - 1] = { ...last, content: data.answer, blocked: data.blocked, regenerated: data.regenerated }
          }
          return msgs
        })
      },
      onVerification: (verification) => {
        setMessages(prev => {
          const msgs = [...prev]
          const last = msgs[msgs.length - 1]
          if (last?.id === assistantMsgId) {
            msgs[msgs.length - 1] = { ...last, verification }
          }
          return msgs
        })
      },
      onDone: (data) => {
        const finalChunks = data.source_chunks || accumulatedChunks
        const resolvedConvId = data.conversation_id || convId
        if (data.conversation_id) setConvId(data.conversation_id)

        const msgs = [...messagesRef.current]
        const last = msgs[msgs.length - 1]
        const resolvedVerification = data.verification || last?.verification || null
        if (last?.id === assistantMsgId) {
          msgs[msgs.length - 1] = {
            role: 'assistant',
            id: assistantMsgId,
            streaming: false,
            content: data.answer || last.content,
            intent: data.intent,
            sources_used: data.sources_used,
            source_chunks: finalChunks,
            citations: data.citations || [],
            verification: resolvedVerification,
            reasoning_steps: accumulatedSteps,
            question: q,
            conversation_id: resolvedConvId,
          }
        }
        setMessages(msgs)
        onNewSources(finalChunks, q, resolvedVerification)
        setReasoningExpanded(false)
        persist(msgs, resolvedConvId)
      },
      onError: (err) => {
        setMessages(prev => {
          const msgs = [...prev]
          const last = msgs[msgs.length - 1]
          if (last?.id === assistantMsgId && last.streaming) {
            msgs[msgs.length - 1] = {
              ...last,
              streaming: false,
              content: 'Request failed: ' + (err?.message || 'unknown error'),
            }
          }
          return msgs
        })
        onNewSources([], q, null)
      },
    }

    try {
      await streamChat(q, convId, useWebSearch, callbacks, outputFormat, selectedSources, mode, mode === 'interact' ? convId : null)
    } catch (err) {
      callbacks.onError(err)
    } finally {
      setLoading(false)
    }
  }

  const streamingMsgIdx = messages.findLastIndex?.(m => m.streaming) ?? -1

  return (
    <div className="flex-1 flex flex-col overflow-hidden min-w-0">
      {/* Messages area */}
      <div
        className="flex-1 overflow-y-auto px-4 sm:px-6 lg:px-8 py-6 flex flex-col gap-4"
      >
        {/* Empty state */}
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center flex-1 gap-4 pb-16">
            <LegalFlick
              variant="compact"
              className="w-48 h-48"
              onPrompt={q => { setInput(q); inputRef.current?.focus() }}
              style={{
                border: '1px solid var(--border-default)',
                background: 'radial-gradient(ellipse 70% 50% at 50% 60%, rgba(193,18,31,0.12), transparent 70%)',
              }}
            />

            <div className="text-center">
              <h2
                className="font-display m-0 mb-1.5"
                style={{
                  color: 'var(--text-primary)',
                  fontSize: '19px',
                  fontWeight: 600,
                  letterSpacing: '-0.015em',
                }}
              >
                Start a research matter
              </h2>
              <p className="m-0 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
                Ask a legal question — the answer arrives with ranked evidence and a groundedness verdict.
              </p>
            </div>

            {/* Suggestion chips */}
            <div className="flex gap-2 flex-wrap justify-center max-w-md mt-2">
              {SUGGESTION_CHIPS.map(suggestion => (
                <SuggestionChip
                  key={suggestion}
                  text={suggestion}
                  onClick={() => { setInput(suggestion); inputRef.current?.focus() }}
                />
              ))}
            </div>

            <div className="flex items-center gap-4 flex-wrap justify-center mt-4" style={{ color: 'var(--text-muted)' }}>
              {[
                { n: '1', t: 'Ask' },
                { n: '2', t: 'Review evidence' },
                { n: '3', t: 'Draft' },
              ].map((step, i) => (
                <div key={step.n} className="flex items-center gap-4">
                  {i > 0 && <span className="w-6 h-px" style={{ background: 'var(--border-default)' }} />}
                  <div className="flex items-center gap-1.5">
                    <span
                      className="w-[18px] h-[18px] rounded-full flex items-center justify-center text-[9.5px] font-bold tabular-nums"
                      style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', fontFamily: 'var(--font-mono)' }}
                    >
                      {step.n}
                    </span>
                    <span className="text-[11px] font-medium">{step.t}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Message list */}
        {messages.map((m, idx) => (
          <div key={m.id}>
            {idx === streamingMsgIdx && (
              <div className="mb-3">
                <ReasoningTimeline
                  steps={reasoningSteps}
                  isActive={loading}
                  expanded={reasoningExpanded}
                />
              </div>
            )}
            {idx !== streamingMsgIdx && m.role === 'assistant' && m.reasoning_steps?.length > 0 && (
              <div className="mb-3">
                <ReasoningTimeline steps={m.reasoning_steps} />
              </div>
            )}
            <MessageBubble message={m} onRefine={handleRefine} />
            {m.role === 'assistant' && !m.streaming && idx === messages.length - 1 && (
              <FollowUpSuggestions
                questions={deriveFollowups(m)}
                onSelect={q => { setInput(q); inputRef.current?.focus() }}
              />
            )}
          </div>
        ))}

        {loading && streamingMsgIdx === -1 && reasoningSteps.length > 0 && (
          <ReasoningTimeline steps={reasoningSteps} isActive={loading} expanded={reasoningExpanded} />
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div
        className="px-4 sm:px-6 lg:px-8 pt-4 pb-5 flex-shrink-0"
        style={{
          borderTop: '1px solid var(--border-default)',
          background: 'var(--bg-card)',
          backdropFilter: 'blur(24px) saturate(160%)',
          WebkitBackdropFilter: 'blur(24px) saturate(160%)',
        }}
      >
        {/* Input form */}
        <form onSubmit={handleSubmit} className="flex flex-col gap-2">
          {/* Query analysis banner */}
          {queryAnalysis && (
            <div className="flex items-start gap-2 px-3 py-2 rounded-[var(--radius-sm)]" style={{ background: 'var(--bg-soft)', border: '1px solid var(--border-default)' }}>
              <Sparkles size={14} style={{ color: 'var(--ink)', marginTop: 2 }} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-0.5">
                  <span className="text-[11px] font-semibold" style={{ color: 'var(--text-primary)' }}>Prompt score: {queryAnalysis.score || queryAnalysis.analysis?.score || 5}/10</span>
                </div>
                {queryAnalysis.improvement_reason && (
                  <p className="text-[11px] mb-1" style={{ color: 'var(--text-secondary)' }}>{queryAnalysis.improvement_reason}</p>
                )}
                {(queryAnalysis.suggested_rewrite || queryAnalysis.analysis?.suggested_rewrite) && (
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-[10.5px] font-medium px-2 py-0.5 rounded-[3px]" style={{ background: 'var(--ink-light)', color: 'var(--ink)' }}>Improved rewrite</span>
                    <span className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>{queryAnalysis.suggested_rewrite || queryAnalysis.analysis?.suggested_rewrite}</span>
                    <button type="button" onClick={handleImprove} className="text-[10.5px] font-semibold px-2 py-0.5 rounded-[3px]" style={{ background: 'var(--primary)', color: 'var(--on-primary)', border: 'none', cursor: 'pointer' }}>Apply</button>
                  </div>
                )}
              </div>
              <button type="button" onClick={() => setQueryAnalysis(null)} className="text-[10px]" style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>✕</button>
            </div>
          )}

          {/* Below `sm`, the toolbar+select+submit row has nowhere near enough
              width next to a usable input — stack input above controls
              instead of letting five fixed-width elements fight for 375px. */}
          <div className="flex flex-col sm:flex-row gap-2.5 sm:items-center">
            <div className="flex gap-2.5 items-center sm:flex-1 sm:min-w-0">
              <div className="relative flex-shrink-0 flex gap-1">
                <ToolbarIconButton
                  title="Skills · Prompt library"
                  active={promptLibraryOpen}
                  onClick={() => setPromptLibraryOpen(v => !v)}
                >
                  <BookOpen size={15} />
                </ToolbarIconButton>
                <ToolbarIconButton
                  title="Refine this draft"
                  disabled={!input.trim()}
                  onClick={handleRefineDraft}
                >
                  <Wand2 size={15} />
                </ToolbarIconButton>
                <ToolbarIconButton
                  title="Analyze prompt quality"
                  disabled={!input.trim() || analyzing}
                  onClick={handleAnalyze}
                >
                  <Sparkles size={15} />
                </ToolbarIconButton>
                {mode === 'interact' && (
                  <ToolbarIconButton
                    title="Attach document"
                    active={attachMenuOpen}
                    onClick={() => setAttachMenuOpen(v => !v)}
                  >
                    <Paperclip size={15} />
                  </ToolbarIconButton>
                )}
                {promptLibraryOpen && (
                  <PromptLibrary onSelect={handleInsertTemplate} onClose={() => setPromptLibraryOpen(false)} />
                )}
                {attachMenuOpen && (
                  <AttachMenu
                    reusePicker={reusePicker}
                    conversations={listConversations().filter(c => c.id !== convId)}
                    reuseSourceId={reuseSourceId}
                    reuseDocs={reuseDocs}
                    onUpload={() => fileInputRef.current?.click()}
                    onOpenReuse={openReusePicker}
                    onPickSource={handlePickReuseSource}
                    onPickDocument={handleReuseDocument}
                    onBack={() => setReusePicker(false)}
                    onBackToSources={handleBackToSources}
                    onClose={closeAttachMenu}
                  />
                )}
                <input
                  ref={fileInputRef}
                  type="file"
                  onChange={handleFileSelected}
                  style={{ display: 'none' }}
                />
              </div>
              <input
                ref={inputRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                disabled={loading}
                placeholder="e.g. What does Section 302 IPC prescribe?"
                className="flex-1 min-w-0 text-sm rounded-[var(--radius-md)] px-4 py-2.5 outline-none disabled:opacity-60"
                style={{
                  border: '1px solid var(--border-input)',
                  color: 'var(--text-primary)',
                  background: 'var(--bg-main)',
                  transition: 'border-color 0.15s, box-shadow 0.15s',
                  fontFamily: "var(--font-sans)",
                }}
                onFocus={e => {
                  e.target.style.borderColor = 'var(--ink)'
                  e.target.style.boxShadow = 'var(--shadow-focus)'
                }}
                onBlur={e => {
                  e.target.style.borderColor = 'var(--border-input)'
                  e.target.style.boxShadow = 'none'
                }}
              />
            </div>
            <div className="flex gap-2.5 items-center flex-wrap sm:flex-nowrap">
              <SourcePicker selected={selectedSources} onChange={setSelectedSources} />
              <select
                value={outputFormat}
                onChange={e => setOutputFormat(e.target.value)}
                disabled={loading}
                className="text-sm rounded-[var(--radius-md)] px-2 py-2.5 outline-none disabled:opacity-60 cursor-pointer"
                style={{
                  border: '1px solid var(--border-input)',
                  color: 'var(--text-primary)',
                  background: 'var(--bg-card)',
                  fontFamily: "var(--font-sans)",
                }}
              >
                <option value="CREAC">CREAC</option>
                <option value="IRAC">IRAC</option>
                <option value="BRIEF">Brief</option>
              </select>
              <SubmitButton loading={loading} disabled={loading || !input.trim()} />
            </div>
          </div>
        </form>

        {/* Attached document chips */}
        {mode === 'interact' && attachedFiles.length > 0 && (
          <div className="flex items-center gap-1.5 flex-wrap mb-3">
            {attachedFiles.map(doc => (
              <span
                key={doc.file_hash}
                className="inline-flex items-center gap-1.5 pl-2.5 pr-1.5 py-1 rounded-[var(--radius-sm)] text-[11.5px] font-medium"
                style={{ border: '1px solid var(--border-default)', background: 'var(--bg-card)', color: 'var(--text-secondary)' }}
              >
                {doc.filename}
                <button
                  type="button"
                  onClick={() => handleRemoveFile(doc.file_hash)}
                  title="Remove document"
                  className="flex items-center justify-center rounded-full transition-colors duration-150"
                  style={{ width: 16, height: 16, border: 'none', background: 'transparent', color: 'var(--text-muted)', cursor: 'pointer' }}
                  onMouseEnter={e => { e.currentTarget.style.background = 'var(--color-error-bg)'; e.currentTarget.style.color = 'var(--color-error)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-muted)' }}
                >
                  <X size={11} />
                </button>
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function ToolbarIconButton({ children, onClick, title, active, disabled }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      disabled={disabled}
      className="w-9 h-9 rounded-[var(--radius-sm)] flex items-center justify-center transition-colors duration-150"
      style={{
        border: `1px solid ${active ? 'var(--ink-border)' : 'var(--border-default)'}`,
        background: active ? 'var(--ink-light)' : 'transparent',
        color: disabled ? 'var(--text-muted)' : active ? 'var(--ink)' : 'var(--text-secondary)',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.5 : 1,
      }}
      onMouseEnter={e => { if (!disabled && !active) { e.currentTarget.style.background = 'var(--ink-light)'; e.currentTarget.style.color = 'var(--ink)' } }}
      onMouseLeave={e => { if (!disabled && !active) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-secondary)' } }}
    >
      {children}
    </button>
  )
}

function AttachMenu({
  reusePicker,
  conversations,
  reuseSourceId,
  reuseDocs,
  onUpload,
  onOpenReuse,
  onPickSource,
  onPickDocument,
  onBack,
  onBackToSources,
  onClose,
}) {
  const panelRef = useRef(null)

  useEffect(() => {
    function handleOutside(e) {
      if (panelRef.current && !panelRef.current.contains(e.target)) onClose()
    }
    function handleKey(e) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', handleOutside)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handleOutside)
      document.removeEventListener('keydown', handleKey)
    }
  }, [onClose])

  const itemStyle = {
    background: 'transparent',
    border: 'none',
    cursor: 'pointer',
    textAlign: 'left',
    color: 'var(--text-primary)',
  }
  const hoverOn = e => { e.currentTarget.style.background = 'var(--ink-light)' }
  const hoverOff = e => { e.currentTarget.style.background = 'transparent' }

  return (
    <div
      ref={panelRef}
      className="absolute bottom-full left-0 mb-2 z-30 flex flex-col overflow-hidden"
      style={{
        width: '260px',
        maxHeight: '280px',
        borderRadius: 'var(--radius-md)',
        border: '1px solid var(--border-default)',
        background: 'var(--bg-card)',
        boxShadow: 'var(--shadow-panel)',
      }}
    >
      {!reusePicker && (
        <div className="p-1.5">
          <button
            type="button"
            onClick={onUpload}
            className="w-full px-2.5 py-2 rounded-[6px] text-[12.5px] font-medium transition-colors duration-150"
            style={itemStyle}
            onMouseEnter={hoverOn}
            onMouseLeave={hoverOff}
          >
            Upload from device
          </button>
          <button
            type="button"
            onClick={onOpenReuse}
            className="w-full px-2.5 py-2 rounded-[6px] text-[12.5px] font-medium transition-colors duration-150"
            style={itemStyle}
            onMouseEnter={hoverOn}
            onMouseLeave={hoverOff}
          >
            Reuse from another matter
          </button>
        </div>
      )}

      {reusePicker && !reuseSourceId && (
        <div className="p-1.5 overflow-y-auto">
          <button
            type="button"
            onClick={onBack}
            className="w-full px-2.5 py-1.5 text-[11px] font-medium"
            style={{ ...itemStyle, color: 'var(--text-muted)' }}
          >
            ← Back
          </button>
          {conversations.length === 0 ? (
            <p className="m-0 px-2.5 py-2 text-[11.5px]" style={{ color: 'var(--text-muted)' }}>
              No other matters yet.
            </p>
          ) : (
            conversations.map(c => (
              <button
                key={c.id}
                type="button"
                onClick={() => onPickSource(c.id)}
                className="w-full px-2.5 py-2 rounded-[6px] text-[12.5px] font-medium truncate transition-colors duration-150"
                style={itemStyle}
                onMouseEnter={hoverOn}
                onMouseLeave={hoverOff}
              >
                {c.title}
              </button>
            ))
          )}
        </div>
      )}

      {reusePicker && reuseSourceId && (
        <div className="p-1.5 overflow-y-auto">
          <button
            type="button"
            onClick={onBackToSources}
            className="w-full px-2.5 py-1.5 text-[11px] font-medium"
            style={{ ...itemStyle, color: 'var(--text-muted)' }}
          >
            ← Back
          </button>
          {reuseDocs.length === 0 ? (
            <p className="m-0 px-2.5 py-2 text-[11.5px]" style={{ color: 'var(--text-muted)' }}>
              No documents in that matter.
            </p>
          ) : (
            reuseDocs.map(doc => (
              <button
                key={doc.file_hash}
                type="button"
                onClick={() => onPickDocument(doc.file_hash)}
                className="w-full px-2.5 py-2 rounded-[6px] text-[12.5px] font-medium truncate transition-colors duration-150"
                style={itemStyle}
                onMouseEnter={hoverOn}
                onMouseLeave={hoverOff}
              >
                {doc.filename}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}

function SuggestionChip({ text, onClick }) {
  const ref = useRef(null)
  function handleEnter() {
    if (prefersReducedMotion()) return
    gsap.to(ref.current, { y: -1.5, duration: 0.15, ease: 'power2.out' })
  }
  function handleLeave() {
    if (prefersReducedMotion()) return
    gsap.to(ref.current, { y: 0, duration: 0.15, ease: 'power2.out' })
  }

  return (
    <button
      ref={ref}
      onClick={onClick}
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
      className="px-3.5 py-1.5 text-[12px] font-medium rounded-[var(--radius-sm)] cursor-pointer"
      style={{
        border: '1px solid var(--border-default)',
        background: 'var(--bg-card)',
        color: 'var(--text-secondary)',
        transition: 'border-color 0.15s, color 0.15s, background 0.15s',
      }}
      onFocus={e => {
        e.currentTarget.style.borderColor = 'var(--gold-border)'
        e.currentTarget.style.color = 'var(--gold)'
      }}
      onBlur={e => {
        e.currentTarget.style.borderColor = 'var(--border-default)'
        e.currentTarget.style.color = 'var(--text-secondary)'
      }}
    >
      {text}
    </button>
  )
}

function SubmitButton({ loading, disabled }) {
  const ref = useRef(null)

  function handleEnter() {
    if (disabled || prefersReducedMotion()) return
    gsap.to(ref.current, { scale: 1.02, duration: 0.15, ease: 'power2.out' })
  }
  function handleLeave() {
    if (prefersReducedMotion()) return
    gsap.to(ref.current, { scale: 1, duration: 0.15, ease: 'power2.out' })
  }

  return (
    <button
      ref={ref}
      type="submit"
      disabled={disabled}
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
      className="px-5 py-2.5 rounded-[var(--radius-md)] text-[13px] font-semibold whitespace-nowrap transition-colors duration-150"
      style={{
        background: disabled ? 'var(--border-default)' : 'var(--primary)',
        color: disabled ? 'var(--text-muted)' : 'var(--on-primary)',
        border: 'none',
        cursor: disabled ? 'not-allowed' : 'pointer',
        fontFamily: "var(--font-sans)",
        boxShadow: disabled ? 'none' : 'var(--shadow-primary)',
      }}
    >
      {loading ? (
        <span className="flex items-center gap-2">
          <span className="flex gap-0.5">
            {[0, 1, 2].map(i => (
              <span
                key={i}
                className="w-1 h-1 rounded-full inline-block"
                style={{
                  background: 'var(--text-muted)',
                  animation: 'chat-bounce 1.2s ease-in-out infinite',
                  animationDelay: `${i * 0.2}s`,
                }}
              />
            ))}
          </span>
          Searching
        </span>
      ) : 'Submit →'}
    </button>
  )
}
