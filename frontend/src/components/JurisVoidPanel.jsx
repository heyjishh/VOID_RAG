import { useState, useRef, useEffect, useCallback } from 'react'
import { Zap, Send, Copy, Download, Printer, Loader2, X, Globe, Database, Brain, Users, Paperclip, Telescope, FileText, Square, FileDown, ChevronDown, Trash2 } from 'lucide-react'
import { marked } from 'marked'
import AgentPipeline, { ThinkingStep } from './AgentPipeline.jsx'
import SourceCard, { VerificationBadge, UploadedFileChip } from './JVSourceCard.jsx'
import { answerToMarkdown, downloadTextFile } from '../lib/exportAnswer.js'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

const JV_STORAGE_KEY = 'juryai.jv_conversations.v1'
const MAX_JV_STORED = 30

function readJVConversations() {
  try { return JSON.parse(localStorage.getItem(JV_STORAGE_KEY) || '[]') } catch { return [] }
}
function writeJVConversations(list) {
  try { localStorage.setItem(JV_STORAGE_KEY, JSON.stringify(list.slice(0, MAX_JV_STORED))) } catch {}
}
function saveJVConversation(id, title, messages) {
  const all = readJVConversations()
  const idx = all.findIndex(c => c.id === id)
  const entry = { id, title, messages, updatedAt: Date.now() }
  if (idx === -1) all.unshift(entry); else all[idx] = entry
  writeJVConversations(all)
}
function deleteJVConversation(id) {
  writeJVConversations(readJVConversations().filter(c => c.id !== id))
}

function TogglePill({ active, onClick, Icon, label, title, disabled }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium transition-all duration-150"
      style={{
        background: active ? 'var(--primary)' : 'var(--bg-soft)',
        color: active ? '#fff' : 'var(--text-muted)',
        border: `1px solid ${active ? 'var(--primary)' : 'var(--border-default)'}`,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.5 : 1,
      }}
    >
      <Icon size={12} />
      {label}
    </button>
  )
}

function StatusPill({ ok, label, Icon }) {
  return (
    <div
      className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-[11px] font-medium"
      style={{
        background: ok ? 'var(--accent-green-bg, rgba(34,197,94,.1))' : 'var(--color-error-bg)',
        color: ok ? 'var(--accent-green, #16a34a)' : 'var(--color-error)',
        border: `1px solid ${ok ? 'var(--accent-green-border, rgba(34,197,94,.2))' : 'var(--color-error-border)'}`,
      }}
    >
      <Icon size={12} />
      {label}
    </div>
  )
}

function SpiceInfoBar({ info }) {
  if (!info?.datasets?.length && !info?.models?.length) return null
  return (
    <div className="flex items-center gap-2 flex-wrap mt-3">
      {info.datasets?.map(d => (
        <span key={d.name || d} className="text-[10px] px-2 py-0.5 rounded-full" style={{ background: 'rgba(234,179,8,.08)', color: '#ca8a04', border: '1px solid rgba(234,179,8,.15)' }}>
          {d.name || d} {d.status === 'Ready' && '✓'}
        </span>
      ))}
      {info.models?.map(m => (
        <span key={m.name || m} className="text-[10px] px-2 py-0.5 rounded-full" style={{ background: 'rgba(147,51,234,.08)', color: '#9333ea', border: '1px solid rgba(147,51,234,.15)' }}>
          {m.name || m}
        </span>
      ))}
    </div>
  )
}

function ConversationDropdown({ conversations, activeId, onSelect, onNew, onDelete }) {
  const [open, setOpen] = useState(false)
  if (!conversations.length && !activeId) return null

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-1.5 px-2.5 py-1 rounded-[5px] text-[11px] font-medium"
        style={{ background: 'var(--bg-soft)', border: '1px solid var(--border-default)', color: 'var(--text-secondary)', cursor: 'pointer' }}
      >
        <FileText size={11} />
        {activeId ? conversations.find(c => c.id === activeId)?.title?.slice(0, 24) || 'Session' : 'History'}
        <ChevronDown size={10} />
      </button>
      {open && (
        <div
          className="absolute top-full left-0 mt-1 rounded-[6px] overflow-hidden z-50 min-w-[220px] max-h-[260px] overflow-y-auto"
          style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', boxShadow: '0 8px 24px rgba(0,0,0,.2)' }}
        >
          <button
            type="button"
            onClick={() => { onNew(); setOpen(false) }}
            className="w-full text-left px-3 py-2 text-[11.5px] font-medium"
            style={{ background: 'transparent', border: 'none', borderBottom: '1px solid var(--border-default)', color: 'var(--primary)', cursor: 'pointer' }}
          >
            + New session
          </button>
          {conversations.map(c => (
            <div
              key={c.id}
              className="flex items-center gap-1 px-3 py-2 text-[11.5px]"
              style={{ background: c.id === activeId ? 'var(--bg-soft)' : 'transparent', cursor: 'pointer', color: 'var(--text-secondary)' }}
            >
              <button
                type="button"
                onClick={() => { onSelect(c); setOpen(false) }}
                className="flex-1 text-left truncate"
                style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', padding: 0 }}
              >
                {c.title}
              </button>
              <button
                type="button"
                onClick={e => { e.stopPropagation(); onDelete(c.id) }}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 2 }}
              >
                <Trash2 size={10} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function JurisVoidPanel({ useWebSearch }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [steps, setSteps] = useState([])
  const [sources, setSources] = useState([])
  const [sourcesOpen, setSourcesOpen] = useState(false)
  const [systemStatus, setSystemStatus] = useState(null)
  const [verification, setVerification] = useState(null)
  // Backend's multi-agent pipeline (planner/statute/case-law/web-verifier/
  // synthesizer with real agent negotiation) is the standardized path —
  // defaults on rather than requiring a manual toggle each session.
  const [subAgents, setSubAgents] = useState(true)
  const [deepResearch, setDeepResearch] = useState(false)
  const [uploadedFiles, setUploadedFiles] = useState([])
  const [uploading, setUploading] = useState(false)
  const [agentPipeline, setAgentPipeline] = useState([])
  const [agentMessages, setAgentMessages] = useState([])
  const [coordinationSummary, setCoordinationSummary] = useState('')
  const [sessionId] = useState(() => crypto.randomUUID())
  const [conversations, setConversations] = useState(() => readJVConversations())
  const [activeConvId, setActiveConvId] = useState(null)
  const answerRef = useRef(null)
  const inputRef = useRef(null)
  const scrollRef = useRef(null)
  const abortRef = useRef(null)
  const fileInputRef = useRef(null)

  useEffect(() => {
    fetch(`${API_BASE}/api/v1/juris-void/status`)
      .then(r => r.json())
      .then(setSystemStatus)
      .catch(() => setSystemStatus({ corpus_connected: false, llm_configured: false, web_search_available: false, spice_available: false }))
  }, [])

  const scrollToBottom = useCallback(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [])

  useEffect(scrollToBottom, [messages, steps, scrollToBottom])

  function persistMessages(msgs) {
    const done = msgs.filter(m => m.role === 'assistant' && m.done)
    if (!done.length) return
    const convId = activeConvId || sessionId
    const firstQ = msgs.find(m => m.role === 'user')?.content || 'Juris-VOID session'
    const title = firstQ.length > 50 ? firstQ.slice(0, 50) + '…' : firstQ
    saveJVConversation(convId, title, msgs)
    if (!activeConvId) setActiveConvId(convId)
    setConversations(readJVConversations())
  }

  function handleSelectConversation(conv) {
    setActiveConvId(conv.id)
    setMessages(conv.messages || [])
    setSteps([])
    setSources([])
    setSourcesOpen(false)
    setVerification(null)
    setAgentPipeline([])
    setAgentMessages([])
    setCoordinationSummary('')
  }

  function handleNewConversation() {
    setActiveConvId(null)
    setMessages([])
    setSteps([])
    setSources([])
    setSourcesOpen(false)
    setVerification(null)
    setAgentPipeline([])
    setAgentMessages([])
    setCoordinationSummary('')
  }

  function handleDeleteConversation(id) {
    deleteJVConversation(id)
    setConversations(readJVConversations())
    if (id === activeConvId) handleNewConversation()
  }

  async function handleFileUpload(e) {
    const files = Array.from(e.target.files || [])
    if (!files.length) return
    setUploading(true)
    for (const file of files) {
      try {
        const id = crypto.randomUUID()
        const formData = new FormData()
        formData.append('session_id', sessionId)
        formData.append('file', file)
        const resp = await fetch(`${API_BASE}/api/v1/juris-void/upload`, { method: 'POST', body: formData })
        if (resp.ok) {
          const data = await resp.json()
          setUploadedFiles(prev => [...prev, { id, name: file.name, hash: data.document?.file_hash, chunks: data.document?.chunk_count || 0 }])
        }
      } catch {}
    }
    setUploading(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  function removeFile(file) {
    fetch(`${API_BASE}/api/v1/juris-void/documents/${file.hash}?session_id=${sessionId}`, { method: 'DELETE' }).catch(() => {})
    setUploadedFiles(prev => prev.filter(f => f.id !== file.id))
  }

  async function handleSend() {
    const q = input.trim()
    if (!q || streaming) return
    setInput('')
    setStreaming(true)
    setSteps([])
    setSources([])
    setSourcesOpen(false)
    setVerification(null)
    setAgentPipeline([])
    setAgentMessages([])
    setCoordinationSummary('')

    const userMsg = { role: 'user', content: q, files: uploadedFiles.length ? [...uploadedFiles] : undefined }
    const assistantMsg = { role: 'assistant', content: '', sources: [], done: false }
    setMessages(prev => [...prev, userMsg, assistantMsg])

    const controller = new AbortController()
    abortRef.current = controller
    const effectiveWebSearch = deepResearch ? true : useWebSearch

    function handleReasoningStep(data) {
      if (data.step === 'agent_roster') {
        setAgentPipeline(data.agents.map(a => ({ ...a, status: 'waiting' })))
      } else if (data.step === 'agent_active') {
        setAgentPipeline(prev => prev.map(a => a.id === data.agent ? { ...a, status: 'active', detail: data.detail } : a))
      } else if (data.step === 'agent_done') {
        setAgentPipeline(prev => prev.map(a => a.id === data.agent ? { ...a, status: 'done', detail: data.detail } : a))
        if (data.coordination_summary) setCoordinationSummary(data.coordination_summary)
      } else if (data.step === 'agent_message') {
        setAgentMessages(prev => [...prev, data])
      }
      setSteps(prev => [...prev, data])
    }

    try {
      const resp = await fetch(`${API_BASE}/api/v1/juris-void/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: q, use_web_search: effectiveWebSearch, use_sub_agents: subAgents,
          output_format: 'CREAC', mode: deepResearch ? 'interact' : 'ask', session_id: sessionId,
        }),
        signal: controller.signal,
      })

      const reader = resp.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let currentAnswer = ''
      let currentSources = []

      function handleEvent(eventType, data) {
        if (eventType === 'reasoning_step') {
          handleReasoningStep(data)
        } else if (eventType === 'source_chunk') {
          currentSources = [...currentSources, data]
          setSources(currentSources)
        } else if (eventType === 'answer_token') {
          currentAnswer += data.token
          setMessages(prev => {
            const copy = [...prev]
            copy[copy.length - 1] = { ...copy[copy.length - 1], content: currentAnswer }
            return copy
          })
        } else if (eventType === 'verification') {
          setVerification(data)
        } else if (eventType === 'gate') {
          if (data.answer) {
            currentAnswer = data.answer
            setMessages(prev => {
              const copy = [...prev]
              copy[copy.length - 1] = { ...copy[copy.length - 1], content: currentAnswer }
              return copy
            })
          }
          setSteps(prev => [...prev, { step: 'gate', detail: data.blocked ? 'Answer blocked — insufficient evidence' : 'Answer regenerated for better grounding' }])
        } else if (eventType === 'error') {
          setSteps(prev => [...prev, { step: 'error', detail: data.message }])
        } else if (eventType === 'done') {
          const finalSources = data.source_chunks || currentSources
          const finalVerification = data.verification || null
          setSources(finalSources)
          if (finalVerification) setVerification(finalVerification)

          setMessages(prev => {
            const copy = [...prev]
            const final = {
              ...copy[copy.length - 1],
              content: data.answer || currentAnswer,
              sources: finalSources,
              verification: finalVerification,
              citations: data.citations || [],
              done: true,
              elapsed: data.elapsed_seconds,
              sourcesUsed: data.sources_used,
            }
            copy[copy.length - 1] = final
            persistMessages(copy)
            return copy
          })
          if (finalSources.length > 0) setSourcesOpen(true)
        }
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const parts = buffer.split('\n\n')
        buffer = parts.pop()
        for (const part of parts) {
          const lines = part.trim().split('\n')
          let eventType = 'message'
          let dataStr = ''
          for (const line of lines) {
            if (line.startsWith('event: ')) eventType = line.slice(7).trim()
            if (line.startsWith('data: ')) dataStr = line.slice(6).trim()
          }
          if (!dataStr) continue
          try { handleEvent(eventType, JSON.parse(dataStr)) } catch {}
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        setSteps(prev => [...prev, { step: 'error', detail: `Connection failed: ${err.message}` }])
      }
    } finally {
      setStreaming(false)
      abortRef.current = null
    }
  }

  function handleStop() { if (abortRef.current) abortRef.current.abort() }
  function handleCopy(content) { navigator.clipboard.writeText(content) }
  function handleKeyDown(e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }

  function handleDraftDownload(msg) {
    const md = answerToMarkdown(msg.content, msg.citations, { withCitations: true })
    downloadTextFile('juris-void-draft.md', md)
  }

  return (
    <div className="flex-1 flex overflow-hidden">
      <div className="flex-1 flex flex-col min-w-0">
        {messages.length === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center px-6">
            <div className="w-14 h-14 rounded-[14px] flex items-center justify-center mb-5" style={{ background: 'linear-gradient(135deg, var(--primary), var(--ink))', boxShadow: '0 8px 32px rgba(0,0,0,.18)' }}>
              <Zap size={26} color="#fff" />
            </div>
            <h1 className="m-0 text-[22px] font-bold tracking-[-0.02em]" style={{ color: 'var(--text-primary)' }}>Juris-VOID</h1>
            <p className="m-0 mt-2 text-[13.5px] text-center max-w-md leading-relaxed" style={{ color: 'var(--text-muted)' }}>
              Multi-agent legal research with corpus retrieval, web search, grounded citations, and verification — all in one pass.
            </p>

            {systemStatus && (
              <>
                <div className="mt-4 flex items-center gap-3 flex-wrap justify-center">
                  <StatusPill ok={systemStatus.corpus_connected} label="Corpus" Icon={Database} />
                  <StatusPill ok={systemStatus.llm_configured} label={systemStatus.llm_provider || 'LLM'} Icon={Brain} />
                  <StatusPill ok={useWebSearch && systemStatus.web_search_available} label="Web Search" Icon={Globe} />
                  <StatusPill ok={systemStatus.spice_available} label="SpiceAI Corpus" Icon={Zap} />
                </div>
                {systemStatus.spice_available && systemStatus.spice_info && (
                  <SpiceInfoBar info={systemStatus.spice_info} />
                )}
              </>
            )}

            <div className="mt-8 grid grid-cols-1 sm:grid-cols-2 gap-2.5 w-full max-w-lg">
              {['What is Section 302 of BNS 2023?', 'Bail provisions under BNSS 2023', 'Limitation period for money recovery suit', 'Capital gains tax on agricultural land'].map(q => (
                <button
                  key={q} type="button"
                  onClick={() => { setInput(q); inputRef.current?.focus() }}
                  className="text-left px-3.5 py-2.5 rounded-[6px] text-[12.5px] leading-snug transition-colors duration-100"
                  style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', color: 'var(--text-secondary)', cursor: 'pointer' }}
                  onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--primary)'; e.currentTarget.style.color = 'var(--text-primary)' }}
                  onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border-default)'; e.currentTarget.style.color = 'var(--text-secondary)' }}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4">
            <div className="max-w-3xl mx-auto flex flex-col gap-4">
              {messages.map((msg, i) => (
                <div key={i}>
                  {msg.role === 'user' ? (
                    <div className="flex justify-end">
                      <div className="max-w-[85%]">
                        <div className="px-4 py-3 rounded-[10px] text-[13.5px] leading-relaxed" style={{ background: 'var(--primary)', color: '#fff', borderBottomRightRadius: 2 }}>
                          {msg.content}
                        </div>
                        {msg.files?.length > 0 && (
                          <div className="flex items-center gap-1.5 mt-1 justify-end">
                            {msg.files.map((f, fi) => (
                              <span key={fi} className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded-[3px]" style={{ background: 'var(--bg-soft)', color: 'var(--text-muted)' }}>
                                <FileText size={10} /> {f.name}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-col gap-2">
                      {i === messages.length - 1 && agentPipeline.length > 0 && (
                        <AgentPipeline
                          agents={agentPipeline}
                          messages={agentMessages}
                          coordinationSummary={!streaming ? coordinationSummary : ''}
                        />
                      )}
                      {i === messages.length - 1 && steps.length > 0 && (
                        <div className="rounded-[6px] px-3 py-2" style={{ background: 'var(--bg-soft)', border: '1px solid var(--border-default)' }}>
                          <p className="m-0 text-[10.5px] font-semibold uppercase mb-1" style={{ color: 'var(--text-muted)', letterSpacing: '0.05em' }}>
                            {streaming ? 'Researching…' : `${steps.length} research steps`}
                          </p>
                          {steps.map((s, j) => <ThinkingStep key={j} step={s} isLast={j === steps.length - 1} streaming={streaming} />)}
                        </div>
                      )}

                      {msg.content && (
                        <div
                          ref={i === messages.length - 1 ? answerRef : null}
                          className="prose-void rounded-[10px] px-4 py-3 text-[13.5px] leading-relaxed"
                          style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', borderBottomLeftRadius: 2, color: 'var(--text-primary)' }}
                        >
                          <div className="prose-md" dangerouslySetInnerHTML={{ __html: marked.parse(msg.content) }} />
                        </div>
                      )}

                      {msg.done && (msg.verification || verification) && <VerificationBadge verification={msg.verification || verification} />}

                      {msg.done && msg.content && (
                        <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                          <button type="button" onClick={() => handleCopy(msg.content)} className="flex items-center gap-1 px-2 py-1 rounded-[4px] text-[11px] font-medium transition-colors" style={{ background: 'var(--bg-soft)', border: '1px solid var(--border-default)', color: 'var(--text-muted)', cursor: 'pointer' }}>
                            <Copy size={12} /> Copy
                          </button>
                          <button type="button" onClick={() => handleDraftDownload(msg)} className="flex items-center gap-1 px-2 py-1 rounded-[4px] text-[11px] font-medium transition-colors" style={{ background: 'var(--bg-soft)', border: '1px solid var(--border-default)', color: 'var(--text-muted)', cursor: 'pointer' }}>
                            <Download size={12} /> Download
                          </button>
                          <button type="button" onClick={() => { const md = answerToMarkdown(msg.content, msg.citations, { withCitations: true }); downloadTextFile('juris-void-draft.docx', md, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document') }} className="flex items-center gap-1 px-2 py-1 rounded-[4px] text-[11px] font-medium transition-colors" style={{ background: 'var(--bg-soft)', border: '1px solid var(--border-default)', color: 'var(--text-muted)', cursor: 'pointer' }}>
                            <FileDown size={12} /> Draft (.docx)
                          </button>
                          <button type="button" onClick={() => { const w = window.open('', '_blank'); w.document.write(`<pre style="white-space:pre-wrap;font-family:serif;padding:2em;max-width:800px;margin:auto">${msg.content}</pre>`); w.print() }} className="flex items-center gap-1 px-2 py-1 rounded-[4px] text-[11px] font-medium transition-colors" style={{ background: 'var(--bg-soft)', border: '1px solid var(--border-default)', color: 'var(--text-muted)', cursor: 'pointer' }}>
                            <Printer size={12} /> Print
                          </button>
                          {msg.sourcesUsed > 0 && <span className="text-[10.5px] ml-1" style={{ color: 'var(--text-muted)' }}>{msg.sourcesUsed} sources</span>}
                          {msg.elapsed && <span className="text-[10.5px] ml-1" style={{ color: 'var(--text-muted)' }}>{msg.elapsed}s</span>}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}

              {streaming && !messages[messages.length - 1]?.content && (
                <div className="flex items-center gap-2 py-2">
                  <Loader2 size={14} className="animate-spin" style={{ color: 'var(--primary)' }} />
                  <span className="text-[12px]" style={{ color: 'var(--text-muted)' }}>{subAgents ? 'Running multi-agent research…' : 'Researching…'}</span>
                </div>
              )}
            </div>
          </div>
        )}

        <div className="flex-shrink-0 px-4 pb-4 pt-2" style={{ borderTop: '1px solid var(--border-default)' }}>
          <div className="max-w-3xl mx-auto">
            <div className="flex items-center gap-2 mb-2 flex-wrap">
              <TogglePill active={subAgents} onClick={() => setSubAgents(v => !v)} Icon={Users} label={subAgents ? 'Sub-agents ON' : 'Sub-agents'} title="Collaborative multi-agent pipeline" />
              <TogglePill active={deepResearch} onClick={() => { if (!useWebSearch && !deepResearch) return; setDeepResearch(v => !v) }} disabled={!useWebSearch} Icon={Telescope} label={deepResearch ? 'Deep Research ON' : 'Deep Research'} title={useWebSearch ? 'Search all datasources exhaustively' : 'Enable Web Search first'} />
              <ConversationDropdown
                conversations={conversations}
                activeId={activeConvId}
                onSelect={handleSelectConversation}
                onNew={handleNewConversation}
                onDelete={handleDeleteConversation}
              />

              {uploadedFiles.length > 0 && (
                <div className="flex items-center gap-1.5 ml-1">
                  {uploadedFiles.map(f => (
                    <span key={f.id} className="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full" style={{ background: 'var(--bg-soft)', color: 'var(--text-secondary)', border: '1px solid var(--border-default)' }}>
                      <FileText size={10} />
                      <span className="max-w-[100px] truncate">{f.name}</span>
                      <button type="button" onClick={() => removeFile(f)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: 'var(--text-muted)', display: 'flex' }}><X size={10} /></button>
                    </span>
                  ))}
                </div>
              )}
            </div>

            <div className="flex items-end gap-2 rounded-[10px] px-3 py-2.5" style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', boxShadow: '0 2px 8px rgba(0,0,0,.06)' }}>
              <input ref={fileInputRef} type="file" multiple accept=".pdf,.txt,.md,.docx,.csv,.xlsx,.xlsm,.jpg,.jpeg,.png,.webp,.tiff,.tif,.bmp" onChange={handleFileUpload} className="hidden" />
              <button type="button" onClick={() => fileInputRef.current?.click()} disabled={uploading} className="flex-shrink-0 w-8 h-8 rounded-[6px] flex items-center justify-center transition-colors" style={{ background: 'transparent', color: uploadedFiles.length ? 'var(--primary)' : 'var(--text-muted)', border: 'none', cursor: 'pointer' }} title="Upload documents">
                {uploading ? <Loader2 size={16} className="animate-spin" /> : <Paperclip size={16} />}
              </button>
              <textarea
                ref={inputRef} value={input} onChange={e => setInput(e.target.value)} onKeyDown={handleKeyDown}
                placeholder={deepResearch ? 'Deep research — all datasources, exhaustive search…' : 'Ask a legal question — corpus + web + verification…'}
                rows={1}
                className="flex-1 resize-none text-[13.5px] leading-relaxed"
                style={{ background: 'transparent', border: 'none', outline: 'none', color: 'var(--text-primary)', minHeight: 24, maxHeight: 160 }}
                onInput={e => { e.target.style.height = 'auto'; e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px' }}
              />
              {streaming ? (
                <button type="button" onClick={handleStop} className="flex-shrink-0 h-8 rounded-[6px] flex items-center justify-center gap-1.5 px-3" style={{ background: 'var(--color-error)', color: '#fff', border: 'none', cursor: 'pointer' }} title="Stop generation">
                  <Square size={12} fill="currentColor" />
                  <span className="text-[11.5px] font-semibold">Stop</span>
                </button>
              ) : (
                <button type="button" onClick={handleSend} disabled={!input.trim()} className="flex-shrink-0 w-8 h-8 rounded-[6px] flex items-center justify-center transition-opacity" style={{ background: input.trim() ? 'var(--primary)' : 'var(--bg-soft)', color: input.trim() ? '#fff' : 'var(--text-muted)', border: 'none', cursor: input.trim() ? 'pointer' : 'default', opacity: input.trim() ? 1 : 0.5 }}>
                  <Send size={16} />
                </button>
              )}
            </div>
            <p className="m-0 mt-1.5 text-center text-[10px]" style={{ color: 'var(--text-muted)' }}>
              Juris-VOID · {subAgents ? 'Multi-agent' : 'Single pipeline'} · {useWebSearch ? 'Web + Corpus' : 'Corpus only'}{deepResearch ? ' · Deep Research' : ''} · Human review required
            </p>
          </div>
        </div>
      </div>

      {sourcesOpen && sources.length > 0 && (
        <div className="flex-shrink-0 flex flex-col overflow-hidden" style={{ width: 340, borderLeft: '1px solid var(--border-default)', background: 'var(--bg-base)' }}>
          <div className="flex items-center justify-between px-4 py-3 flex-shrink-0" style={{ borderBottom: '1px solid var(--border-default)' }}>
            <div className="flex items-center gap-2">
              <span className="text-[13px] font-semibold" style={{ color: 'var(--text-primary)' }}>Sources</span>
              <span className="text-[11px] font-medium px-1.5 py-0.5 rounded-[3px]" style={{ background: 'var(--primary-light)', color: 'var(--primary)' }}>{sources.length} retrieved</span>
              {sources.some(s => s.domain === 'web') && (
                <span className="text-[11px] font-medium px-1.5 py-0.5 rounded-[3px]" style={{ background: 'rgba(59,130,246,.1)', color: '#3b82f6' }}>{sources.filter(s => s.domain === 'web').length} web</span>
              )}
            </div>
            <button type="button" onClick={() => setSourcesOpen(false)} style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}><X size={16} /></button>
          </div>
          <div className="flex-1 overflow-y-auto px-3 py-3 flex flex-col gap-2.5">
            {sources.map((src, i) => <SourceCard key={i} source={src} index={i} />)}
          </div>
        </div>
      )}
    </div>
  )
}
