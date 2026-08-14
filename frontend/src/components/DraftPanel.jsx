import { useState } from 'react'
import { marked } from 'marked'
import { draftDocument } from '../lib/api.js'
import { downloadTextFile } from '../lib/exportAnswer.js'

marked.setOptions({ gfm: true, breaks: true })

export default function DraftPanel() {
  const [brief, setBrief] = useState('')
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleGenerate() {
    if (!brief.trim() || loading) return
    setLoading(true)
    setError('')
    try {
      const data = await draftDocument(brief.trim())
      setContent(data.content || '')
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
          <label className="block text-[11px] font-semibold mb-2" style={{ color: 'var(--text-secondary)', letterSpacing: '0.02em' }}>
            Describe what you want drafted
          </label>
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
          <div className="flex items-center gap-3 mt-2.5 mb-4">
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
  )
}
