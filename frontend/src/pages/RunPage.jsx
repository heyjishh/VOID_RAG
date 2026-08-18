import { useState, useEffect, useMemo, useRef } from 'react'
import { marked } from 'marked'
import { getRun, followUpRun, sourceAction, getRunSource, getRunSourceFile, downloadRunPdf } from '../lib/api.js'
import ReasoningTimeline from '../components/ReasoningTimeline.jsx'
import CitationStrip from '../components/CitationStrip.jsx'
import SourceCard from '../components/SourceCard.jsx'
import VerificationBadge from '../components/VerificationBadge.jsx'
import { ArrowLeft, Loader2, Copy, Download, Printer, Volume2, Pencil, Check, X } from 'lucide-react'

marked.setOptions({ gfm: true, breaks: true })

function injectCitations(html, citations) {
  if (!citations || citations.length === 0) return html
  return html.replace(/(<[^>]+>)|\[(\d{1,3})\]/g, (match, tag, num) => {
    if (tag) return tag
    const cite = citations[Number(num) - 1]
    if (!cite) return match
    const tip = cite.quote
      ? `"${cite.quote}" — ${cite.verified ? 'matched to source' : 'not directly matched, verify manually'}`
      : (cite.verified ? 'Matched to source text' : 'Not directly matched to source text — verify manually')
    const color = cite.verified ? 'var(--sage)' : 'var(--text-secondary)'
    const bg = cite.verified ? 'var(--sage-light)' : 'var(--bg-soft)'
    const border = cite.verified ? 'var(--sage-border)' : 'var(--border-default)'
    return (
      `<button type="button" class="citation-ref" data-cite="${num}" ` +
      `title="${tip.replace(/"/g, '&quot;')}" ` +
      `style="color:${color};background:${bg};border:1px solid ${border};border-radius:4px;padding:1px 6px;font-size:11px;font-weight:600;cursor:pointer">${num}</button>`
    )
  })
}

const CREAC_SECTIONS = ['Conclusion', 'Rule', 'Explanation', 'Application', 'Analysis', 'Conclusion']

function enhanceCreacHtml(html) {
  if (!html) return html
  let out = html
  CREAC_SECTIONS.forEach(section => {
    const re = new RegExp(`(<h2[^>]*>\\s*)(${section})(\\s*</h2>)`, 'gi')
    out = out.replace(re, `$1<div class="creac-section creac-${section.toLowerCase()}">$2</div>$3`)
    const re3 = new RegExp(`(<h3[^>]*>\\s*)(${section})(\\s*</h3>)`, 'gi')
    out = out.replace(re3, `$1<div class="creac-subsection creac-${section.toLowerCase()}">$2</div>$3`)
  })
  out = out.replace(/<blockquote>/g, '<blockquote class="judicial-quote">')
  out = out.replace(/<table>/g, '<div class="table-wrap"><table>')
  out = out.replace(/<\/table>/g, '</table></div>')
  return out
}

export default function RunPage({ runId, onBack }) {
  const [run, setRun] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [followupLoading, setFollowupLoading] = useState(false)
  const [followupAnswer, setFollowupAnswer] = useState('')
  const [followupCitations, setFollowupCitations] = useState([])
  const [followupSources, setFollowupSources] = useState([])
  const [followupText, setFollowupText] = useState('')
  const [renaming, setRenaming] = useState(false)
  const [draftTitle, setDraftTitle] = useState('')
  const [sourceFilter, setSourceFilter] = useState('all')
  const [copiedTable, setCopiedTable] = useState(false)

  const answerRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    getRun(runId)
      .then(data => {
        if (!cancelled) {
          setRun(data)
          setDraftTitle(data.question || '')
          setLoading(false)
        }
      })
      .catch(err => {
        if (!cancelled) {
          setError(err?.message || 'Failed to load run')
          setLoading(false)
        }
      })
    return () => { cancelled = true }
  }, [runId])

  const htmlContent = useMemo(() => {
    if (!run?.answer) return null
    try {
      const raw = marked.parse(run.answer)
      const withCitations = injectCitations(raw, run.citations)
      return enhanceCreacHtml(withCitations)
    } catch { return null }
  }, [run])

  useEffect(() => {
    if (!htmlContent || !answerRef.current) return
    const tables = answerRef.current.querySelectorAll('.table-wrap table')
    tables.forEach(table => {
      if (table.parentElement?.querySelector('.table-copy-btn')) return
      const btn = document.createElement('button')
      btn.className = 'table-copy-btn'
      btn.textContent = 'Copy table'
      btn.onclick = () => {
        const rows = Array.from(table.querySelectorAll('tr')).map(tr =>
          Array.from(tr.querySelectorAll('th, td')).map(cell => cell.innerText).join('\t')
        )
        navigator.clipboard.writeText(rows.join('\n'))
        btn.textContent = 'Copied'
        setTimeout(() => { btn.textContent = 'Copy table' }, 1500)
      }
      table.parentElement.style.position = 'relative'
      table.parentElement.appendChild(btn)
    })
  }, [htmlContent])

  const citedCount = useMemo(() => {
    if (!run?.source_chunks) return 0
    return run.source_chunks.filter(c => c.cited).length
  }, [run])

  const filteredSources = useMemo(() => {
    if (!run?.source_chunks) return []
    if (sourceFilter === 'referred') return run.source_chunks.filter(c => c.cited)
    return run.source_chunks
  }, [run, sourceFilter])

  async function handleFollowUp(question) {
    setFollowupLoading(true)
    setFollowupAnswer('')
    setFollowupCitations([])
    setFollowupSources([])
    try {
      const data = await followUpRun(runId, question, false)
      setFollowupAnswer(data.answer || '')
      setFollowupCitations(data.citations || [])
      setFollowupSources(data.source_chunks || [])
    } catch (err) {
      setFollowupAnswer('Follow-up failed: ' + (err?.message || 'unknown error'))
    } finally {
      setFollowupLoading(false)
    }
  }

  async function handleSourceAction(index, action) {
    try {
      if (action === 'read_chunk') {
        const data = await getRunSource(runId, index)
        alert(data.text || 'No content available.')
        return
      }
      if (action === 'copy_chunk') {
        const data = await getRunSource(runId, index)
        await navigator.clipboard.writeText(data.text || '')
        return
      }
      if (action === 'open_window') {
        const data = await getRunSource(runId, index)
        const url = data.url || data.source || ''
        if (url) window.open(url, '_blank', 'noopener,noreferrer')
        return
      }
      if (action === 'download') {
        const fileData = await getRunSourceFile(runId, index)
        const blob = new Blob([fileData.content || ''], { type: 'text/plain' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `source-${index + 1}.txt`
        a.click()
        URL.revokeObjectURL(url)
        return
      }
      const data = await sourceAction(runId, index, action)
      if (action === 'copy_citation') {
        await navigator.clipboard.writeText(data.citation || '')
      }
    } catch (err) {
      console.error('Source action failed:', err)
    }
  }

  function handleCopyAnswer() {
    if (!run?.answer) return
    navigator.clipboard.writeText(run.answer)
  }

  async function handleDownloadAnswer() {
    if (!run?.answer) return
    try {
      const blob = await downloadRunPdf(runId)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `run-${runId}.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (err) {
      console.error('PDF download failed:', err)
    }
  }

  function handlePrint() {
    window.print()
  }

  function handleCopyTable(tableEl) {
    const rows = Array.from(tableEl.querySelectorAll('tr')).map(tr =>
      Array.from(tr.querySelectorAll('th, td')).map(cell => cell.innerText).join('\t')
    )
    navigator.clipboard.writeText(rows.join('\n'))
    setCopiedTable(true)
    setTimeout(() => setCopiedTable(false), 1500)
  }

  function handleRenameSave() {
    if (!draftTitle.trim()) {
      setDraftTitle(run?.question || '')
    }
    setRenaming(false)
  }

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ background: 'var(--bg-main)' }}>
        <div className="flex flex-col items-center gap-3">
          <Loader2 size={28} className="animate-spin" style={{ color: 'var(--primary)' }} />
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Loading research run…</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ background: 'var(--bg-main)' }}>
        <div className="flex flex-col items-center gap-3 max-w-md text-center px-4">
          <p className="text-sm" style={{ color: 'var(--color-error)' }}>{error}</p>
          <button
            onClick={onBack}
            className="px-4 py-2 rounded-[2px] text-sm font-medium"
            style={{ background: 'var(--primary)', color: 'var(--on-primary)' }}
          >
            Back to research
          </button>
        </div>
      </div>
    )
  }

  if (!run) return null

  const verdict = run.verification?.verdict || 'unsupported'
  const queryAnalysis = run.query_analysis || null
  const retrievedCount = run.source_chunks?.length || 0
  const groundedCount = run.source_chunks?.filter(c => c.verified).length || 0

  return (
    <div className="flex-1 overflow-y-auto" style={{ background: 'var(--bg-main)' }}>
      <div className="max-w-3xl mx-auto px-4 py-6">
        {/* Top banner */}
        <div className="flex items-center gap-3 mb-4">
          <button
            onClick={onBack}
            className="flex items-center gap-2 px-3 py-2 rounded-[2px] text-sm font-medium transition-colors"
            style={{ background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-default)' }}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-soft)'; e.currentTarget.style.color = 'var(--text-primary)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'var(--bg-card)'; e.currentTarget.style.color = 'var(--text-secondary)' }}
          >
            <ArrowLeft size={16} />
            Back to research
          </button>
          {!renaming ? (
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-semibold truncate" style={{ color: 'var(--text-primary)' }}>{run.question}</h1>
              <button
                onClick={() => setRenaming(true)}
                className="p-1 rounded-[2px] transition-colors"
                style={{ background: 'transparent', color: 'var(--text-muted)', border: 'none', cursor: 'pointer' }}
                onMouseEnter={e => { e.currentTarget.style.color = 'var(--text-primary)'; e.currentTarget.style.background = 'var(--bg-soft)' }}
                onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-muted)'; e.currentTarget.style.background = 'transparent' }}
                title="Rename run"
              >
                <Pencil size={12} />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-1">
              <input
                autoFocus
                value={draftTitle}
                onChange={e => setDraftTitle(e.target.value)}
                onBlur={handleRenameSave}
                onKeyDown={e => { if (e.key === 'Enter') handleRenameSave(); if (e.key === 'Escape') setRenaming(false) }}
                className="px-2 py-1 text-sm rounded-[2px]"
                style={{ background: 'var(--bg-card)', color: 'var(--text-primary)', border: '1px solid var(--primary)', outline: 'none', minWidth: 200 }}
              />
              <button onClick={handleRenameSave} className="p-1 rounded-[2px]" style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--sage)' }}><Check size={14} /></button>
              <button onClick={() => { setRenaming(false); setDraftTitle(run.question || '') }} className="p-1 rounded-[2px]" style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}><X size={14} /></button>
            </div>
          )}
        </div>

        <div className="flex items-center gap-3 mb-4 flex-wrap">
          <span className="text-[11px] font-semibold px-2 py-[3px] rounded-[3px] uppercase" style={{ background: 'var(--ink-light)', color: 'var(--ink)', border: '1px solid var(--ink-border)' }}>
            {run.output_format || 'CREAC'}
          </span>
          <span className="text-[11px] font-mono" style={{ color: 'var(--text-muted)' }}>
            Run {run.run_id}
          </span>
          <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
            {run.created_at ? new Date(run.created_at).toLocaleString() : ''}
          </span>
          {verdict && <VerificationBadge verdict={verdict} score={run.verification?.groundedness_score} />}
        </div>

        {/* Prompt metadata */}
        {queryAnalysis && (
          <div className="mb-4 p-3 rounded-[2px]" style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)' }}>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs font-semibold" style={{ color: 'var(--text-primary)' }}>Prompt score</span>
              <span className="text-[11px] px-2 py-0.5 rounded-[3px] font-medium" style={{ background: 'var(--ink-light)', color: 'var(--ink)' }}>
                {queryAnalysis.score || 5}/10
              </span>
            </div>
            {queryAnalysis.improvement_reason && (
              <p className="text-xs mb-1" style={{ color: 'var(--text-secondary)' }}>{queryAnalysis.improvement_reason}</p>
            )}
            {queryAnalysis.suggested_rewrite && (
              <div className="flex items-center gap-2 mt-2 p-2 rounded-[2px]" style={{ background: 'var(--sage-light)', border: '1px solid var(--sage-border)' }}>
                <span className="text-[11px] font-semibold" style={{ color: 'var(--sage)' }}>Improved rewrite</span>
                <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>{queryAnalysis.suggested_rewrite}</span>
              </div>
            )}
          </div>
        )}

        {/* Answer toolbar */}
        <div className="flex items-center gap-2 mb-3">
          <button onClick={handleCopyAnswer} className="flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1.5 rounded-[2px] transition-colors" style={{ background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-default)', cursor: 'pointer' }} onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-soft)'; e.currentTarget.style.color = 'var(--text-primary)' }} onMouseLeave={e => { e.currentTarget.style.background = 'var(--bg-card)'; e.currentTarget.style.color = 'var(--text-secondary)' }}>
            <Copy size={13} /> Copy
          </button>
          <button onClick={handleDownloadAnswer} className="flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1.5 rounded-[2px] transition-colors" style={{ background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-default)', cursor: 'pointer' }} onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-soft)'; e.currentTarget.style.color = 'var(--text-primary)' }} onMouseLeave={e => { e.currentTarget.style.background = 'var(--bg-card)'; e.currentTarget.style.color = 'var(--text-secondary)' }}>
            <Download size={13} /> Download
          </button>
          <button onClick={handlePrint} className="flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1.5 rounded-[2px] transition-colors" style={{ background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-default)', cursor: 'pointer' }} onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-soft)'; e.currentTarget.style.color = 'var(--text-primary)' }} onMouseLeave={e => { e.currentTarget.style.background = 'var(--bg-card)'; e.currentTarget.style.color = 'var(--text-secondary)' }}>
            <Printer size={13} /> Print
          </button>
          <button className="flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-1.5 rounded-[2px] transition-colors" style={{ background: 'var(--bg-card)', color: 'var(--text-secondary)', border: '1px solid var(--border-default)', cursor: 'pointer' }} onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-soft)'; e.currentTarget.style.color = 'var(--text-primary)' }} onMouseLeave={e => { e.currentTarget.style.background = 'var(--bg-card)'; e.currentTarget.style.color = 'var(--text-secondary)' }}>
            <Volume2 size={13} /> Listen
          </button>
        </div>

        {/* Answer body */}
        {htmlContent && (
          <div
            ref={answerRef}
            className="prose-md creac-body rounded-[2px] p-4"
            style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', boxShadow: 'var(--shadow-card)' }}
            onClick={e => {
              const badge = e.target.closest('.citation-ref')
              if (!badge) return
              const n = Number(badge.dataset.cite)
              const el = document.querySelector(`[data-source-index="${n - 1}"]`)
              if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
            }}
            dangerouslySetInnerHTML={{ __html: htmlContent }}
          />
        )}

        {/* Follow-up */}
        <div className="mt-6">
          <h3 className="text-[12px] font-semibold uppercase mb-2" style={{ color: 'var(--text-muted)', letterSpacing: '0.06em' }}>Follow-up</h3>
          <div className="flex gap-2">
            <input
              type="text"
              value={followupText}
              onChange={e => setFollowupText(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && followupText.trim()) { handleFollowUp(followupText.trim()); setFollowupText('') } }}
              placeholder="Ask a follow-up question"
              className="flex-1 px-3 py-2 text-sm rounded-[2px]"
              style={{ background: 'var(--bg-card)', color: 'var(--text-primary)', border: '1px solid var(--border-default)', outline: 'none' }}
            />
            <button
              onClick={() => { if (followupText.trim()) { handleFollowUp(followupText.trim()); setFollowupText('') } }}
              disabled={!followupText.trim() || followupLoading}
              className="px-4 py-2 rounded-[2px] text-sm font-medium transition-colors"
              style={{ background: followupText.trim() && !followupLoading ? 'var(--primary)' : 'var(--bg-soft)', color: followupText.trim() && !followupLoading ? 'var(--on-primary)' : 'var(--text-muted)', border: '1px solid var(--border-default)', cursor: followupText.trim() && !followupLoading ? 'pointer' : 'not-allowed' }}
            >
              Send
            </button>
          </div>
          <div className="flex gap-2 mt-2">
            <button className="text-[10.5px] font-medium px-2 py-1 rounded-[3px] transition-colors" style={{ background: 'var(--bg-soft)', color: 'var(--text-muted)', border: '1px solid var(--border-default)', cursor: 'pointer' }} onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-card)'; e.currentTarget.style.color = 'var(--text-secondary)' }} onMouseLeave={e => { e.currentTarget.style.background = 'var(--bg-soft)'; e.currentTarget.style.color = 'var(--text-muted)' }}>
              Improve follow-up
            </button>
            <button className="text-[10.5px] font-medium px-2 py-1 rounded-[3px] transition-colors" style={{ background: 'var(--bg-soft)', color: 'var(--text-muted)', border: '1px solid var(--border-default)', cursor: 'pointer' }} onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-card)'; e.currentTarget.style.color = 'var(--text-secondary)' }} onMouseLeave={e => { e.currentTarget.style.background = 'var(--bg-soft)'; e.currentTarget.style.color = 'var(--text-muted)' }}>
              Dictate your follow-up
            </button>
          </div>
        </div>

        {followupLoading && (
          <div className="mt-4 flex items-center gap-2" style={{ color: 'var(--text-muted)' }}>
            <Loader2 size={16} className="animate-spin" />
            <span className="text-sm">Running follow-up…</span>
          </div>
        )}

        {followupAnswer && (
          <div className="mt-4">
            <div className="text-sm font-semibold mb-1" style={{ color: 'var(--text-secondary)' }}>Follow-up answer</div>
            <div className="rounded-[2px] p-4" style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)' }}>
              <p className="m-0 text-sm leading-relaxed whitespace-pre-wrap" style={{ color: 'var(--text-primary)' }}>{followupAnswer}</p>
            </div>
          </div>
        )}

        {/* Sources */}
        {run.source_chunks?.length > 0 && (
          <div className="mt-8">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-[12px] font-semibold uppercase" style={{ color: 'var(--text-muted)', letterSpacing: '0.06em' }}>Sources</h3>
              <div className="flex items-center gap-3">
                <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                  {retrievedCount} retrieved · {citedCount} cited · {groundedCount} grounded
                </span>
                <div className="flex gap-1 p-0.5 rounded-[2px]" style={{ background: 'var(--bg-soft)', border: '1px solid var(--border-default)' }}>
                  <button
                    onClick={() => setSourceFilter('all')}
                    className="text-[10.5px] font-medium px-2 py-1 rounded-[2px] transition-colors"
                    style={{ background: sourceFilter === 'all' ? 'var(--bg-card)' : 'transparent', color: sourceFilter === 'all' ? 'var(--text-primary)' : 'var(--text-muted)', border: 'none', cursor: 'pointer' }}
                  >
                    All
                  </button>
                  <button
                    onClick={() => setSourceFilter('referred')}
                    className="text-[10.5px] font-medium px-2 py-1 rounded-[2px] transition-colors"
                    style={{ background: sourceFilter === 'referred' ? 'var(--bg-card)' : 'transparent', color: sourceFilter === 'referred' ? 'var(--text-primary)' : 'var(--text-muted)', border: 'none', cursor: 'pointer' }}
                  >
                    Referred
                  </button>
                </div>
              </div>
            </div>
            <div className="flex flex-col gap-2">
              {filteredSources.map((chunk, idx) => {
                const originalIndex = run.source_chunks.indexOf(chunk)
                return (
                  <SourceCard
                    key={originalIndex}
                    chunk={chunk}
                    question={run.question}
                    rank={originalIndex}
                    onAction={(action) => handleSourceAction(originalIndex, action)}
                  />
                )
              })}
            </div>
          </div>
        )}

        {run.reasoning_steps?.length > 0 && (
          <div className="mt-6">
            <h3 className="text-[12px] font-semibold uppercase mb-2" style={{ color: 'var(--text-muted)', letterSpacing: '0.06em' }}>Research process</h3>
            <ReasoningTimeline steps={run.reasoning_steps} />
          </div>
        )}

        {run.citations?.length > 0 && (
          <div className="mt-6">
            <h3 className="text-[12px] font-semibold uppercase mb-2" style={{ color: 'var(--text-muted)', letterSpacing: '0.06em' }}>Citations</h3>
            <CitationStrip citations={run.citations} />
          </div>
        )}
      </div>
    </div>
  )
}