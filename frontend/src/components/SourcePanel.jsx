import { useEffect, useRef } from 'react'
import gsap from 'gsap'
import SourceCard from './SourceCard.jsx'
import { prefersReducedMotion } from '../lib/motion.js'
import { verdictMeta } from '../lib/verdictMeta.js'

function SectionHeader({ title, count }) {
  return (
    <div className="flex items-center gap-2 mb-2 mt-1">
      <span
        className="text-[10px] font-bold uppercase tracking-widest"
        style={{ color: 'var(--text-muted)', letterSpacing: '0.08em' }}
      >
        {title}
      </span>
      <span
        className="text-[9.5px] font-semibold px-1.5 py-0.5 rounded-[3px]"
        style={{
          background: 'var(--border-default)',
          color: 'var(--text-muted)',
          fontFamily: "'JetBrains Mono', monospace",
        }}
      >
        {count}
      </span>
      <div className="flex-1 h-px" style={{ background: 'var(--border-default)' }} />
    </div>
  )
}

// Aggregate stats computed purely from the real per-chunk fields the backend
// sends (score, verified) plus the turn's verification object — an "industry
// RAG" retrieval summary, not decorative chrome. No field here is invented.
function RetrievalSummary({ chunks, verification }) {
  if (chunks.length === 0) return null
  const verifiedCount = chunks.filter(c => c.verified).length
  const avgScore = Math.round((chunks.reduce((sum, c) => sum + (c.score ?? 0), 0) / chunks.length) * 100)
  const verdict = verification?.verdict
  const meta = verdict ? verdictMeta(verdict) : null
  const groundedPct = verification ? Math.round((Number(verification.groundedness_score) || 0) * 100) : null

  return (
    <div
      className="flex items-center gap-x-3 gap-y-1.5 flex-wrap px-3 py-2 mb-3 rounded-[var(--radius-sm)]"
      style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)' }}
    >
      <Stat label="Retrieved" value={chunks.length} />
      <Divider />
      <Stat label="Verified" value={verifiedCount} valueColor={verifiedCount > 0 ? 'var(--sage)' : undefined} />
      <Divider />
      <Stat label="Avg. match" value={`${avgScore}%`} />
      {meta && (
        <>
          <Divider />
          <span
            className="text-[10px] font-bold px-1.5 py-[1px] rounded-[3px] uppercase tabular-nums"
            style={{ background: meta.bg, color: meta.color, border: `1px solid ${meta.border}`, letterSpacing: '0.03em' }}
            title="Groundedness verdict for this turn's answer"
          >
            {meta.label}{groundedPct != null ? ` · ${groundedPct}%` : ''}
          </span>
        </>
      )}
    </div>
  )
}

function Stat({ label, value, valueColor }) {
  return (
    <span className="flex items-baseline gap-1 text-[11px]">
      <span className="font-bold tabular-nums" style={{ color: valueColor || 'var(--text-primary)', fontFamily: "'JetBrains Mono', monospace" }}>
        {value}
      </span>
      <span style={{ color: 'var(--text-muted)' }}>{label}</span>
    </span>
  )
}

function Divider() {
  return <span className="w-px h-3" style={{ background: 'var(--border-default)' }} />
}

export default function SourcePanel({ chunks = [], question = '', isLoading = false, collapsed = false, verification = null }) {
  const containerRef = useRef(null)
  const prevChunksRef = useRef([])

  useEffect(() => {
    if (!containerRef.current) return
    if (chunks.length === 0 || chunks === prevChunksRef.current) return
    prevChunksRef.current = chunks
    if (prefersReducedMotion()) return

    const cards = containerRef.current.querySelectorAll('.doc-card')
    if (cards.length === 0) return
    gsap.fromTo(
      cards,
      { opacity: 0, y: 10 },
      { opacity: 1, y: 0, duration: 0.35, stagger: 0.06, ease: 'power3.out' }
    )
  }, [chunks])

  return (
    <aside
      className="flex flex-col overflow-hidden flex-shrink-0"
      style={{
        width: collapsed ? '0' : '360px',
        minWidth: 0,
        transition: 'width 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
        willChange: 'width',
        borderLeft: collapsed ? 'none' : '1px solid var(--border-default)',
        background: 'var(--bg-soft)',
      }}
    >
      {/* Panel header */}
      <div
        className="flex items-center gap-2.5 px-4 py-3 flex-shrink-0"
        style={{
          borderBottom: '1px solid var(--border-default)',
          background: 'var(--bg-card)',
        }}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--gold)" strokeWidth="2">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14,2 14,8 20,8" />
          <line x1="16" y1="13" x2="8" y2="13" />
          <line x1="16" y1="17" x2="8" y2="17" />
        </svg>

        <span
          className="font-display text-[14px] italic"
          style={{ color: 'var(--text-primary)', fontWeight: 500 }}
        >
          Retrieved Evidence
        </span>

        {chunks.length > 0 && (
          <span
            className="ml-auto text-[10px] font-bold px-2 py-0.5 rounded-[4px]"
            style={{
              color: 'var(--gold)',
              background: 'var(--gold-light)',
              border: '1px solid var(--gold-border)',
              fontFamily: "'JetBrains Mono', monospace",
            }}
          >
            {chunks.length} cited
          </span>
        )}
      </div>

      {/* Content */}
      <div ref={containerRef} className="flex-1 overflow-y-auto p-3.5">

        {/* Loading skeleton */}
        {isLoading && (
          <div className="flex flex-col gap-3">
            {[1, 2, 3].map(i => (
              <div
                key={i}
                className="rounded-[var(--radius-md)]"
                style={{
                  height: '120px',
                  background: 'var(--border-default)',
                  animation: `pulse-opacity ${1.3 + i * 0.1}s cubic-bezier(0.45, 0, 0.55, 1) infinite`,
                }}
              />
            ))}
          </div>
        )}

        {/* Empty state */}
        {!isLoading && chunks.length === 0 && (
          <div className="flex flex-col items-center justify-center h-64 gap-3">
            <svg
              width="38"
              height="38"
              viewBox="0 0 24 24"
              fill="none"
              stroke="var(--border-default)"
              strokeWidth="1"
            >
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14,2 14,8 20,8" />
              <line x1="16" y1="13" x2="8" y2="13" />
              <line x1="16" y1="17" x2="8" y2="17" />
            </svg>
            <p
              className="text-[12px] text-center m-0 leading-relaxed font-display italic"
              style={{ color: 'var(--text-muted)' }}
            >
              Retrieved passages<br />will appear here, ranked by relevance
            </p>
          </div>
        )}

        {/* Retrieved evidence, ranked in retrieval order */}
        {!isLoading && chunks.length > 0 && (
          <div>
            <RetrievalSummary chunks={chunks} verification={verification} />
            <SectionHeader title="Passages" count={chunks.length} />
            <div className="flex flex-col gap-2.5">
              {chunks.map((chunk, i) => (
                <SourceCard
                  key={`${chunk.source}-${chunk.page}-${i}`}
                  chunk={chunk}
                  question={question}
                  rank={i}
                />
              ))}
            </div>
          </div>
        )}
      </div>
    </aside>
  )
}
