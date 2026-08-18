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

export default function SourceCard({ chunk, question, rank, onAction }) {
  const cardRef = useRef(null)
  const barRef = useRef(null)
  const [viewerOpen, setViewerOpen] = useState(false)
  const score = Math.max(0, Math.min(1, chunk.score ?? 0))
  const tier = relevanceTier(score)
  const scorePercent = Math.round(score * 100)
  const title = chunk.source?.split('/').pop() || chunk.source || 'Untitled passage'
  const excerpt = chunk.text || ''
  const isVerified = Boolean(chunk.verified)
  const isWeb = chunk.domain === 'web' && Boolean(chunk.url)
  const isInternal = chunk.domain === 'internal'
  const isClickable = isWeb || isInternal
  const viewSource = isInternal ? title : (chunk.source || title)

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
        data-source-index={rank}
        className={`doc-card block rounded-[2px] text-decoration-none p-3 ${isClickable ? 'cursor-pointer' : 'cursor-default'}`}
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
        {/* Row 1: rank · title · tier */}
        <div className="flex items-center gap-2.5">
          <div
            className="w-7 h-7 rounded-[6px] flex items-center justify-center flex-shrink-0 text-[11px] font-bold tabular-nums"
            style={{ background: tier.bg, border: `1px solid ${tier.border}`, color: tier.color, fontFamily: "var(--font-mono)" }}
          >
            {rank != null ? rank + 1 : '–'}
          </div>

          <p
            className="m-0 flex-1 min-w-0 text-[12.5px] font-semibold truncate leading-snug"
            style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-sans)' }}
            title={chunk.source || title}
          >
            {title}
          </p>

          <span
            className="text-[9.5px] font-bold px-1.5 py-[2px] rounded-[3px] uppercase whitespace-nowrap flex-shrink-0"
            style={{
              background: tier.bg,
              color: tier.color,
              border: `1px solid ${tier.border}`,
              letterSpacing: '0.03em',
            }}
          >
            {tier.label}
          </span>
        </div>

        {/* Row 2: metadata strip */}
        <div className="flex items-center gap-2 mt-1.5 pl-[26px]">
          {chunk.page != null && (
            <span className="text-[10px] tabular-nums" style={{ color: 'var(--text-muted)', fontFamily: "var(--font-mono)" }}>
              p.{chunk.page + 1}
            </span>
          )}
          <span className="text-[10px] tabular-nums" style={{ color: 'var(--text-muted)', fontFamily: "var(--font-mono)" }}>
            {scorePercent}% match
          </span>
          <div className="flex-1 h-[2px] rounded-full overflow-hidden" style={{ background: 'var(--border-default)' }}>
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
          {isVerified && (
            <span
              className="inline-flex items-center gap-[3px] text-[9.5px] font-semibold px-1.5 py-[1px] rounded-[3px] uppercase flex-shrink-0"
              style={{ background: 'var(--sage-light)', color: 'var(--sage)', letterSpacing: '0.04em' }}
              title="This passage's text was matched to a claim in the answer"
            >
              <svg width="7" height="7" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                <polyline points="20 6 9 17 4 12" />
              </svg>
              Verified
            </span>
          )}
          {!isVerified && chunk.cited && (
            <span
              className="inline-flex items-center gap-[3px] text-[9.5px] font-semibold px-1.5 py-[1px] rounded-[3px] uppercase flex-shrink-0"
              style={{ background: 'var(--gold-light)', color: 'var(--gold)', letterSpacing: '0.04em' }}
            >
              Cited
            </span>
          )}
        </div>

        {/* Excerpt - highlight using the citation quote if available, fallback to question */}
        <p
          className="m-0 mt-2 text-[12px] leading-relaxed pl-[26px]"
          style={{
            color: 'var(--text-secondary)',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}
        >
          {highlightText(excerpt, chunk.citation_quote || question)}
        </p>

        {onAction && (
          <div className="flex gap-2 mt-3 pl-[26px] flex-wrap">
            <button
              className="text-[10.5px] font-medium px-2 py-1 rounded-[3px] transition-colors"
              style={{ background: 'var(--bg-soft)', color: 'var(--text-secondary)', border: '1px solid var(--border-default)', cursor: 'pointer' }}
              onClick={() => onAction('copy_chunk')}
              onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-card)'; e.currentTarget.style.color = 'var(--text-primary)' }}
              onMouseLeave={e => { e.currentTarget.style.background = 'var(--bg-soft)'; e.currentTarget.style.color = 'var(--text-secondary)' }}
            >
              Copy chunk
            </button>
            <button
              className="text-[10.5px] font-medium px-2 py-1 rounded-[3px] transition-colors"
              style={{ background: 'var(--bg-soft)', color: 'var(--text-secondary)', border: '1px solid var(--border-default)', cursor: 'pointer' }}
              onClick={() => onAction('read_chunk')}
              onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-card)'; e.currentTarget.style.color = 'var(--text-primary)' }}
              onMouseLeave={e => { e.currentTarget.style.background = 'var(--bg-soft)'; e.currentTarget.style.color = 'var(--text-secondary)' }}
            >
              Read chunk
            </button>
            <button
              className="text-[10.5px] font-medium px-2 py-1 rounded-[3px] transition-colors"
              style={{ background: 'var(--bg-soft)', color: 'var(--text-secondary)', border: '1px solid var(--border-default)', cursor: 'pointer' }}
              onClick={() => onAction('open_window')}
              onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-card)'; e.currentTarget.style.color = 'var(--text-primary)' }}
              onMouseLeave={e => { e.currentTarget.style.background = 'var(--bg-soft)'; e.currentTarget.style.color = 'var(--text-secondary)' }}
            >
              Open in new window
            </button>
            <button
              className="text-[10.5px] font-medium px-2 py-1 rounded-[3px] transition-colors"
              style={{ background: 'var(--bg-soft)', color: 'var(--text-secondary)', border: '1px solid var(--border-default)', cursor: 'pointer' }}
              onClick={() => onAction('download')}
              onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-card)'; e.currentTarget.style.color = 'var(--text-primary)' }}
              onMouseLeave={e => { e.currentTarget.style.background = 'var(--bg-soft)'; e.currentTarget.style.color = 'var(--text-secondary)' }}
            >
              Download document
            </button>
          </div>
        )}
      </Wrapper>

      {viewerOpen && (
        <DocumentViewerModal
          source={viewSource}
          page={chunk.page}
          text={excerpt}
          onClose={() => setViewerOpen(false)}
        />
      )}
    </>
  )
}
