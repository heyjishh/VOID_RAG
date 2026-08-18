import { useEffect, useRef, useState } from 'react'
import gsap from 'gsap'
import { ScrollText } from 'lucide-react'
import SourceCard from './SourceCard.jsx'
import { prefersReducedMotion } from '../lib/motion.js'
import { verdictMeta } from '../lib/verdictMeta.js'

function RetrievalSummary({ chunks, verification }) {
  if (chunks.length === 0) return null
  const citedCount = chunks.filter(c => c.cited).length
  const verifiedCount = chunks.filter(c => c.verified).length
  const avgScore = Math.round((chunks.reduce((sum, c) => sum + (c.score ?? 0), 0) / chunks.length) * 100)
  const verdict = verification?.verdict
  const meta = verdict ? verdictMeta(verdict) : null
  const groundedPct = verification ? Math.round((Number(verification.groundedness_score) || 0) * 100) : null

  return (
    <div
      className="grid grid-cols-3 gap-px mb-3 rounded-[2px] overflow-hidden"
      style={{ background: 'var(--border-default)', border: '1px solid var(--border-default)' }}
    >
      {[
        { label: 'Retrieved', value: String(chunks.length), color: undefined },
        { label: 'Cited', value: String(citedCount), color: citedCount > 0 ? 'var(--gold)' : undefined },
        { label: 'Verified', value: String(verifiedCount), color: verifiedCount > 0 ? 'var(--sage)' : undefined },
      ].map(stat => (
        <div key={stat.label} className="px-2.5 py-2" style={{ background: 'var(--bg-card)' }}>
          <p className="m-0 text-[13px] font-bold tabular-nums" style={{ color: stat.color || 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
            {stat.value}
          </p>
          <p className="m-0 mt-0.5 text-[9.5px] uppercase" style={{ color: 'var(--text-muted)', letterSpacing: '0.07em' }}>
            {stat.label}
          </p>
        </div>
      ))}
      {meta && groundedPct != null && (
        <div
          className="col-span-3 px-2.5 py-1.5 flex items-center justify-between"
          style={{ background: meta.bg, borderTop: `1px solid ${meta.border}` }}
        >
          <span className="text-[10px] font-bold uppercase tabular-nums" style={{ color: meta.color, letterSpacing: '0.05em' }}>
            {meta.label}
          </span>
          <span className="text-[10px] font-semibold tabular-nums" style={{ color: meta.color, fontFamily: 'var(--font-mono)' }}>
            Avg. match {avgScore}% · Grounded {groundedPct}%
          </span>
        </div>
      )}
    </div>
  )
}

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'cited', label: 'Cited' },
  { id: 'verified', label: 'Verified' },
]

export default function EvidencePanel({ chunks = [], question = '', isLoading = false, collapsed = false, verification = null, overlay = false, onRequestClose }) {
  const containerRef = useRef(null)
  const prevChunksRef = useRef([])
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    if (!containerRef.current) return
    if (chunks.length === 0 || chunks === prevChunksRef.current) return
    prevChunksRef.current = chunks
    if (prefersReducedMotion()) return

    const cards = containerRef.current.querySelectorAll('.doc-card')
    if (cards.length === 0) return
    gsap.fromTo(
      cards,
      { opacity: 0, y: 8 },
      { opacity: 1, y: 0, duration: 0.32, stagger: 0.05, ease: 'power3.out' }
    )
  }, [chunks])

  useEffect(() => {
    if (chunks.length === 0) setFilter('all')
  }, [chunks.length])

  const filteredChunks = filter === 'all'
    ? chunks
    : chunks.filter(c => (filter === 'cited' ? c.cited : c.verified))

  return (
    <>
      {/* Below the desktop breakpoint this panel slides over the content
          instead of squeezing it — 380px pushed against a phone viewport
          would leave no room for the chat underneath it. */}
      {overlay && !collapsed && (
        <div
          className="fixed inset-0 z-30"
          style={{ background: 'var(--overlay-scrim)' }}
          onClick={onRequestClose}
        />
      )}
      <aside
        className="flex flex-col overflow-hidden flex-shrink-0"
        style={{
          // The viewport cap is a separate, non-animated maxWidth rather
          // than folded into the transitioning width itself — animating
          // width to/from a min()-computed value renders as 1px in some
          // engines, since it can't resolve the function mid-interpolation.
          width: collapsed ? '0' : '380px',
          maxWidth: overlay ? '88vw' : undefined,
          minWidth: 0,
          transition: 'width 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
          willChange: 'width',
          borderLeft: collapsed ? 'none' : '1px solid var(--border-default)',
          background: 'var(--bg-soft)',
          backdropFilter: 'blur(24px) saturate(160%)',
          WebkitBackdropFilter: 'blur(24px) saturate(160%)',
          ...(overlay ? { position: 'fixed', insetBlock: 0, right: 0, zIndex: 35, boxShadow: collapsed ? 'none' : 'var(--shadow-panel)' } : {}),
        }}
      >
      {/* Panel header */}
      <div className="flex items-center gap-2.5 px-3.5 h-[52px] flex-shrink-0" style={{ borderBottom: '1px solid var(--border-default)', background: 'var(--bg-card)' }}>
        <ScrollText size={15} style={{ color: 'var(--gold)' }} />
        <span className="text-[13px] font-semibold" style={{ color: 'var(--text-primary)' }}>
          Evidence
        </span>
        {chunks.length > 0 && (
          <span
            className="ml-auto text-[10px] font-bold px-1.5 py-0.5 rounded-[4px] tabular-nums"
            style={{ color: 'var(--gold)', background: 'var(--gold-light)', border: '1px solid var(--gold-border)', fontFamily: 'var(--font-mono)' }}
          >
            {filteredChunks.length}/{chunks.length} passages
          </span>
        )}
        {chunks.length > 0 && (
          <div className="flex items-center gap-1">
            {FILTERS.map(f => (
              <button
                key={f.id}
                type="button"
                onClick={() => setFilter(f.id)}
                className="px-2 py-1 rounded-[5px] text-[10.5px] font-medium transition-colors duration-150"
                style={{
                  background: filter === f.id ? 'var(--bg-soft)' : 'transparent',
                  color: filter === f.id ? 'var(--text-primary)' : 'var(--text-muted)',
                  border: filter === f.id ? '1px solid var(--border-default)' : '1px solid transparent',
                  cursor: 'pointer',
                }}
              >
                {f.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Content */}
      <div ref={containerRef} className="flex-1 overflow-y-auto p-3">
        {isLoading && (
          <div className="flex flex-col gap-2.5">
            {[1, 2, 3].map(i => (
              <div
                key={i}
                className="rounded-[2px]"
                style={{
                  height: '96px',
                  background: 'var(--border-default)',
                  animation: `pulse-opacity ${1.3 + i * 0.1}s cubic-bezier(0.45, 0, 0.55, 1) infinite`,
                }}
              />
            ))}
          </div>
        )}

        {!isLoading && chunks.length === 0 && (
          <div className="flex flex-col items-center justify-center h-64 gap-3">
            <ScrollText size={26} style={{ color: 'var(--border-input)' }} />
            <p className="text-[12px] text-center m-0 leading-relaxed" style={{ color: 'var(--text-muted)' }}>
              Retrieved passages appear here,<br />ranked by relevance
            </p>
          </div>
        )}

        {!isLoading && chunks.length > 0 && (
          <div>
            <RetrievalSummary chunks={chunks} verification={verification} />
            <div className="flex flex-col gap-2">
              {filteredChunks.map((chunk, i) => (
                <SourceCard
                  key={`${chunk.source}-${chunk.page}-${i}`}
                  chunk={chunk}
                  question={question}
                  rank={chunk.index ? chunk.index - 1 : i}
                />
              ))}
            </div>
            {filteredChunks.length === 0 && (
              <p className="text-[11.5px] text-center py-8 m-0" style={{ color: 'var(--text-muted)' }}>
                No passages match this filter.
              </p>
            )}
          </div>
        )}
      </div>
      </aside>
    </>
  )
}