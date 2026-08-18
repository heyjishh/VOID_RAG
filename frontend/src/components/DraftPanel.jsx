import { useState } from 'react'
import { marked } from 'marked'
import { Paperclip, X, Sparkles } from 'lucide-react'
import { draftDocument, uploadDraftDocument } from '../lib/api.js'
import { downloadTextFile } from '../lib/exportAnswer.js'
import DraftHistorySidebar from './DraftHistorySidebar.jsx'

marked.setOptions({ gfm: true, breaks: true })

const DOCUMENT_TYPES = [
  'Opinion/memo',
  'Plaint',
  'Written statement/Counter',
  'Petition (writ/SLP/review)',
  'Written submissions',
  'Application (IA/bail/misc.)',
  'Order/Judgment',
  'Notice/letter',
  'Reply notice',
  'Agreement',
  'Affidavit',
  'Other',
]

const ATTACHMENT_SLOTS = [
  { key: 'houseStyle', label: 'House style' },
  { key: 'inputDocument', label: 'Input document' },
]

function newSessionId() {
  return typeof crypto !== 'undefined' && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function AttachSlot({ config, attachment, uploading, onAttach, onRemove }) {
  const inputId = `draft-attach-${config.key}`
  return (
    <>
      <input
        id={inputId}
        type="file"
        accept=".pdf,.txt,.md"
        className="hidden"
        onChange={e => {
          const file = e.target.files?.[0]
          if (file) onAttach(config.key, file)
          e.target.value = ''
        }}
      />
      {attachment ? (
        <span
          className="inline-flex items-center gap-1.5 pl-2.5 pr-1.5 py-1 rounded-[6px] text-[11.5px] font-medium"
          style={{ background: 'var(--ink-light)', border: '1px solid var(--ink-border)', color: 'var(--ink)' }}
        >
          {config.label}: {attachment.filename}
          <button
            type="button"
            onClick={() => onRemove(config.key)}
            className="w-4 h-4 flex items-center justify-center rounded-full"
            style={{ background: 'transparent', border: 'none', color: 'var(--ink)', cursor: 'pointer' }}
          >
            <X size={11} />
          </button>
        </span>
      ) : (
        <label
          htmlFor={inputId}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-[6px] text-[11.5px] font-medium transition-colors duration-150"
          style={{
            background: 'var(--bg-soft)',
            border: '1px solid var(--border-default)',
            color: 'var(--text-secondary)',
            cursor: uploading ? 'wait' : 'pointer',
            opacity: uploading ? 0.6 : 1,
          }}
        >
          <Paperclip size={12} />
          {uploading ? 'Uploading…' : config.label}
        </label>
      )}
    </>
  )
}

export default function DraftPanel() {
  const [sessionId] = useState(newSessionId)
  const [brief, setBrief] = useState('')
  const [documentType, setDocumentType] = useState(DOCUMENT_TYPES[0])
  const [researchBeforeDrafting, setResearchBeforeDrafting] = useState(false)
  const [attachments, setAttachments] = useState({})
  const [uploadingSlot, setUploadingSlot] = useState(null)
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [historyKey, setHistoryKey] = useState(0)

  async function handleAttach(slotKey, file) {
    setUploadingSlot(slotKey)
    setError('')
    try {
      const data = await uploadDraftDocument(sessionId, file)
      setAttachments(prev => ({ ...prev, [slotKey]: { filename: file.name, file_hash: data.file_hash } }))
    } catch (err) {
      setError(err?.response?.data?.detail || 'File upload failed. Please try again.')
    } finally {
      setUploadingSlot(null)
    }
  }

  function handleRemoveAttachment(slotKey) {
    setAttachments(prev => {
      const next = { ...prev }
      delete next[slotKey]
      return next
    })
  }

  async function handleGenerate() {
    if (!brief.trim() || loading) return
    setLoading(true)
    setError('')
    try {
      const data = await draftDocument({
        brief: brief.trim(),
        document_type: documentType,
        house_style_file_hash: attachments.houseStyle?.file_hash,
        input_document_file_hash: attachments.inputDocument?.file_hash,
        research_before_drafting: researchBeforeDrafting,
        session_id: sessionId,
      })
      setContent(data.content || '')
      setHistoryKey(k => k + 1)
    } catch (err) {
      setError(err?.response?.data?.detail || 'Draft generation failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  function handleDownload() {
    downloadTextFile('juryai-draft.md', content.endsWith('\n') ? content : content + '\n')
  }

  return (
    <div className="flex-1 flex overflow-hidden min-w-0">
      <DraftHistorySidebar refreshKey={historyKey} />

      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        {/* Workspace toolbar */}
        <div
          className="flex items-center gap-3 px-5 h-[52px] flex-shrink-0"
          style={{ borderBottom: '1px solid var(--border-default)', background: 'var(--bg-card)', backdropFilter: 'blur(24px) saturate(160%)', WebkitBackdropFilter: 'blur(24px) saturate(160%)' }}
        >
          <span className="text-[13px] font-semibold" style={{ color: 'var(--text-primary)' }}>
            Drafting workspace
          </span>
          {content && (
            <span
              className="text-[10px] font-bold px-1.5 py-0.5 rounded-[4px] uppercase"
              style={{ color: 'var(--sage)', background: 'var(--sage-light)', border: '1px solid var(--sage-border)', letterSpacing: '0.05em' }}
            >
              Draft ready
            </span>
          )}
          <div className="flex-1" />
          {content && (
            <button
              onClick={handleDownload}
              className="px-3 py-1.5 rounded-[7px] text-[12px] font-semibold transition-colors duration-150"
              style={{
                border: '1px solid var(--border-default)',
                background: 'var(--bg-soft)',
                color: 'var(--text-secondary)',
                cursor: 'pointer',
              }}
              onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--ink)'; e.currentTarget.style.color = 'var(--ink)' }}
              onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border-default)'; e.currentTarget.style.color = 'var(--text-secondary)' }}
            >
              Download .md
            </button>
          )}
        </div>

        {/* Prompt composer */}
        <div className="px-6 pt-5 flex-shrink-0">
          <div className="max-w-[820px] mx-auto">
            <div className="flex items-center gap-2 mb-2">
              <label className="text-[11px] font-semibold" style={{ color: 'var(--text-secondary)', letterSpacing: '0.02em' }}>
                Describe what you want drafted
              </label>
              <select
                value={documentType}
                onChange={e => setDocumentType(e.target.value)}
                className="ml-auto text-[11.5px] font-medium rounded-[6px] px-2 py-1 focus:outline-none"
                style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', color: 'var(--text-primary)' }}
              >
                {DOCUMENT_TYPES.map(type => (
                  <option key={type} value={type}>{type}</option>
                ))}
              </select>
            </div>
            <textarea
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
              placeholder='e.g. "Opinion memo on force majeure clauses", "Reply to a legal notice from X", "Agreement between A and B for..."'
              rows={3}
              className="w-full p-3 rounded-[2px] text-[13px] resize-none focus:outline-none transition-colors"
              style={{
                background: 'var(--bg-card)',
                border: '1px solid var(--border-input)',
                color: 'var(--text-primary)',
                boxShadow: 'var(--shadow-card)',
              }}
              onFocus={e => {
                e.target.style.borderColor = 'var(--ink)'
                e.target.style.boxShadow = 'var(--shadow-focus)'
              }}
              onBlur={e => {
                e.target.style.borderColor = 'var(--border-input)'
                e.target.style.boxShadow = 'var(--shadow-card)'
              }}
            />

            <div className="flex items-center gap-2 mt-2.5 flex-wrap">
              {ATTACHMENT_SLOTS.map(config => (
                <AttachSlot
                  key={config.key}
                  config={config}
                  attachment={attachments[config.key]}
                  uploading={uploadingSlot === config.key}
                  onAttach={handleAttach}
                  onRemove={handleRemoveAttachment}
                />
              ))}
              <label className="inline-flex items-center gap-1.5 text-[11.5px] font-medium ml-1" style={{ color: 'var(--text-secondary)', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={researchBeforeDrafting}
                  onChange={e => setResearchBeforeDrafting(e.target.checked)}
                  className="w-3.5 h-3.5"
                />
                <Sparkles size={12} style={{ color: 'var(--gold)' }} />
                Research before drafting
              </label>
            </div>

            <div className="flex items-center gap-3 mt-3 mb-4">
              <button
                onClick={handleGenerate}
                disabled={!brief.trim() || loading}
                className="px-4 py-2 rounded-[2px] text-[13px] font-semibold transition-colors duration-150"
                style={{
                  background: 'var(--primary)',
                  color: 'var(--on-primary)',
                  opacity: !brief.trim() || loading ? 0.5 : 1,
                  cursor: !brief.trim() || loading ? 'not-allowed' : 'pointer',
                  boxShadow: 'var(--shadow-primary-sm)',
                }}
              >
                {loading ? 'Drafting…' : 'Generate draft'}
              </button>
              {error && <span className="text-[12px]" style={{ color: 'var(--color-error)' }}>{error}</span>}
            </div>
          </div>
        </div>

        {/* Document surface */}
        <div className="flex-1 overflow-y-auto px-6 pb-8 pt-2">
          <div
            className="max-w-[820px] mx-auto rounded-[3px] px-10 py-9 min-h-[480px]"
            style={{
              background: 'var(--bg-card)',
              border: '1px solid var(--border-default)',
              boxShadow: 'var(--shadow-card)',
            }}
          >
            {!content && !loading && (
              <div className="flex flex-col items-center justify-center h-[400px] gap-2">
                <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="var(--border-input)" strokeWidth="1.4">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14,2 14,8 20,8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                </svg>
                <p className="m-0 text-[12.5px]" style={{ color: 'var(--text-muted)' }}>
                  Your generated document appears here as a ready-to-review draft.
                </p>
              </div>
            )}
            {content && (
              <div className="prose-md" style={{ color: 'var(--text-primary)' }} dangerouslySetInnerHTML={{ __html: marked.parse(content) }} />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
