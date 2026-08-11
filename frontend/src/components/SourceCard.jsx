import { useRef, useState } from 'react'
import gsap from 'gsap'
import { prefersReducedMotion } from '../lib/motion.js'
import DocumentViewerModal from './DocumentViewerModal.jsx'

// Relevance tier is derived from `score` — the one ranking signal the backend
// actually sends per chunk (SourceChunkOut.score in app/api/schemas.py). The
// previous version branched on `domain` / `source_type` / `authority_score`,
// none of which exist on the wire for a source_chunk event — that silently
// always fell through to the same neutral tier no matter what was retrieved.
// Tiering by the real score keeps the badge honest about what it measures:
// retrieval relevance, not editorial authority (nothing in the payload
// asserts a document's legal authority, so this card doesn't claim to know it).
function relevanceTier(score) {
  if (score >= 0.75) {
    return { label: 'High relevance', bg: 'var(--gold-light)', border: 'var(--gold-border)', color: 'var(--gold)', bar: 'var(--gold)' }
  }
  if (score >= 0.45) {
    return { label: 'Moderate relevance', bg: 'var(--ink-light)', border: 'var(--ink-border)', color: 'var(--ink)', bar: 'var(--ink)' }
  }
  return { label: 'Low relevance', bg: 'var(--bg-soft)', border: 'var(--border-default)', color: 'var(--text-muted)', bar: 'var(--border-default)' }
}

// Text fragments (`#:~:text=`) need a short, exact-ish substring of the live
// page's visible text to match against — a full chunk is too long and too
// likely to have drifted from the page's actual wording.
function buildSnippet(text, maxLen = 120) {
  if (!text) return ''
  const trimmed = text.trim()
  if (trimmed.length <= maxLen) return trimmed
  const cut = trimmed.slice(0, maxLen)
  const lastSpace = cut.lastIndexOf(' ')
  return (lastSpace > 40 ? cut.slice(0, lastSpace) : cut).trim()
}

function buildWebHref(url, excerpt) {
  const snippet = buildSnippet(excerpt)
  return snippet ? `${url}#:~:text=${encodeURIComponent(snippet)}` : url
}

function highlightText(text, query) {
  if (!query || !text) return text
  const words = query.toLowerCase().split(/\s+/).filter(w => w.length > 3)
  if (words.length === 0) return text

  const pattern = new RegExp(
    `(${words.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`,
    'gi'
  )
  const parts = text.split(pattern)
  return parts.map((part, i) =>
    pattern.test(part) ? <mark key={i} className="source-highlight">{part}</mark> : part
  )
}

export default function SourceCard({ chunk, question, rank }) {
  const cardRef = useRef(null)
  const barRef = useRef(null)
  const [viewerOpen, setViewerOpen] = useState(false)
  const score = Math.max(0, Math.min(1, chunk.score ?? 0))
  const tier = relevanceTier(score)
  const scorePercent = Math.round(score * 100)

  // `chunk.source` is the filename used as the display title — there's no
  // separate `title` field on the wire. `chunk.url` (web-domain only) is the
  // navigable identity for web sources; internal sources are opened via
  // `chunk.source` against the /documents/view endpoint instead.
  const title = chunk.source?.split('/').pop() || chunk.source || 'Untitled passage'
  const excerpt = chunk.text || ''
  const isVerified = Boolean(chunk.verified)
  const isWeb = chunk.domain === 'web' && Boolean(chunk.url)
  const isInternal = chunk.domain === 'internal'
  const isClickable = isWeb || isInternal

  function handleHover(enter) {
    if (!cardRef.current || prefersReducedMotion()) return
    gsap.to(cardRef.current, {
      y: enter ? -2 : 0,
      boxShadow: enter ? 'var(--shadow-card-hover)' : 'var(--shadow-card)',
      borderColor: enter ? tier.border : 'var(--border-default)',
      duration: 0.2,
      ease: 'power2.out',
    })
  }

  const Wrapper = isWeb ? 'a' : 'div'
  const interactionProps = isWeb
    ? { href: buildWebHref(chunk.url, excerpt), target: '_blank', rel: 'noopener noreferrer' }
    : isInternal
      ? {
          onClick: () => setViewerOpen(true),
          role: 'button',
          tabIndex: 0,
          onKeyDown: e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setViewerOpen(true) } },
        }
      : {}

  return (
    <>
      <Wrapper
        ref={cardRef}
        className={`doc-card block rounded-[var(--radius-md)] p-3.5 ${isClickable ? 'cursor-pointer' : 'cursor-default'}`}
        style={{
          background: 'var(--bg-card)',
          border: '1px solid var(--border-default)',
          boxShadow: 'var(--shadow-card)',
          textDecoration: 'none',
        }}
        onMouseEnter={() => handleHover(true)}
        onMouseLeave={() => handleHover(false)}
        {...interactionProps}
      >
        {/* Header */}
        <div className="flex items-start gap-2.5 mb-2">
          {/* Retrieval rank — array order from the backend IS the rank */}
          <div
            className="w-7 h-7 rounded-[6px] flex items-center justify-center flex-shrink-0 mt-0.5 text-[11px] font-bold tabular-nums"
            style={{ background: tier.bg, border: `1px solid ${tier.border}`, color: tier.color, fontFamily: "'JetBrains Mono', monospace" }}
          >
            {rank != null ? rank + 1 : '–'}
          </div>

          {/* Title and meta */}
          <div className="flex-1 min-w-0">
            <p
              className="m-0 text-[12.5px] font-semibold truncate leading-snug"
              style={{
                color: 'var(--text-primary)',
                fontFamily: "'Cormorant Garamond', Georgia, serif",
                fontWeight: 600,
              }}
              title={chunk.source || title}
            >
              {title}
            </p>
            <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
              {chunk.page != null && (
                <span className="text-[10px] tabular-nums" style={{ color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace" }}>
                  p.{chunk.page + 1}
                </span>
              )}
              {isVerified && (
                <span
                  className="inline-flex items-center gap-[3px] text-[9.5px] font-semibold px-1.5 py-[1px] rounded-[3px] uppercase"
                  style={{ background: 'var(--sage-light)', color: 'var(--sage)', letterSpacing: '0.04em' }}
                  title="This passage's text was matched to a claim in the answer"
                >
                  <svg width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                  Verified
                </span>
              )}
            </div>
          </div>

          {/* Relevance badge */}
          <div className="flex flex-col items-end gap-1 flex-shrink-0">
            <span
              className="text-[9.5px] font-bold px-1.5 py-[2px] rounded-[3px] uppercase tracking-wide whitespace-nowrap"
              style={{
                background: tier.bg,
                color: tier.color,
                border: `1px solid ${tier.border}`,
                letterSpacing: '0.03em',
              }}
            >
              {tier.label}
            </span>
            <span
              className="text-[10px] tabular-nums"
              style={{ color: 'var(--text-muted)', fontFamily: "'JetBrains Mono', monospace" }}
            >
              {scorePercent}% match
            </span>
          </div>
        </div>

        {/* Relevance score bar */}
        <div
          className="h-[2px] rounded-full mb-2.5 overflow-hidden"
          style={{ background: 'var(--border-default)' }}
        >
          <div
            ref={barRef}
            className="h-full rounded-full"
            style={{
              width: `${scorePercent}%`,
              background: tier.bar,
              animation: 'fillBar 0.6s cubic-bezier(0.16, 1, 0.3, 1)',
            }}
          />
        </div>

        {/* Excerpt */}
        <p
          className="m-0 text-[12px] leading-relaxed"
          style={{
            color: 'var(--text-secondary)',
            display: '-webkit-box',
            WebkitLineClamp: 3,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {highlightText(excerpt, question)}
        </p>
      </Wrapper>

      {viewerOpen && (
        <DocumentViewerModal
          source={chunk.source}
          page={chunk.page}
          text={excerpt}
          onClose={() => setViewerOpen(false)}
        />
      )}
    </>
  )
}
