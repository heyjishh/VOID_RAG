import { useState, useRef, useEffect } from 'react'
import gsap from 'gsap'
import { prefersReducedMotion } from '../lib/motion.js'
import { VERDICT_META as VERDICT_TOKENS } from '../lib/verdictMeta.js'

// Icons are presentation-only, layered on top of the shared color/label
// tokens (lib/verdictMeta.js) so SourcePanel's retrieval summary and this
// badge never drift into two different palettes for the same verdict.
const VERDICT_ICONS = {
  grounded: (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 2 4 5v6c0 5 3.4 8.5 8 10 4.6-1.5 8-5 8-10V5l-8-3z" />
      <polyline points="9 12 11.5 14.5 15.5 9.5" />
    </svg>
  ),
  partially_grounded: (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 2 4 5v6c0 5 3.4 8.5 8 10 4.6-1.5 8-5 8-10V5l-8-3z" />
      <line x1="12" y1="8" x2="12" y2="12.5" />
      <line x1="12" y1="15.5" x2="12" y2="15.6" />
    </svg>
  ),
  unsupported: (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d="M12 2 4 5v6c0 5 3.4 8.5 8 10 4.6-1.5 8-5 8-10V5l-8-3z" />
      <line x1="9.5" y1="9.5" x2="14.5" y2="14.5" />
      <line x1="14.5" y1="9.5" x2="9.5" y2="14.5" />
    </svg>
  ),
}

const VERDICT_META = Object.fromEntries(
  Object.entries(VERDICT_TOKENS).map(([key, tokens]) => [key, { ...tokens, icon: VERDICT_ICONS[key] }])
)
VERDICT_META.unsupported.label = 'Limited evidence'

export default function VerificationBadge({ verification, question, onRefine }) {
  const [expanded, setExpanded] = useState(false)
  const bodyRef = useRef(null)

  const verdict = verification?.verdict || 'unsupported'
  const meta = VERDICT_META[verdict] || VERDICT_META.unsupported

  const supported = Array.isArray(verification?.supported_claims) ? verification.supported_claims : []
  const unsupported = Array.isArray(verification?.unsupported_claims) ? verification.unsupported_claims : []
  const total = supported.length + unsupported.length
  const pct = Math.round((Number(verification?.groundedness_score) || 0) * 100)

  const claimsLabel = verdict === 'unsupported'
    ? meta.label
    : `${meta.label} · ${supported.length}/${total || supported.length} claim${(total || supported.length) !== 1 ? 's' : ''} verified`

  // Only the summary and any unsupported claims are worth expanding to.
  const hasDetail = Boolean(verification?.summary) || unsupported.length > 0
  const wasRegenerated = Boolean(verification?.regenerated)
  const wasBlocked = Boolean(verification?.blocked)

  useEffect(() => {
    if (!bodyRef.current) return
    if (prefersReducedMotion()) {
      bodyRef.current.style.height = expanded ? 'auto' : '0px'
      bodyRef.current.style.opacity = expanded ? '1' : '0'
      return
    }
    if (expanded) {
      gsap.fromTo(bodyRef.current, { height: 0, opacity: 0 }, { height: 'auto', opacity: 1, duration: 0.2, ease: 'power2.out' })
    } else {
      gsap.to(bodyRef.current, { height: 0, opacity: 0, duration: 0.18, ease: 'power2.in' })
    }
  }, [expanded])

  return (
    <div
      className="overflow-hidden"
      style={{
        borderRadius: 'var(--radius-md)',
        border: `1px solid ${meta.border}`,
        background: meta.bg,
      }}
    >
      {/* Gate banner — the answer shown is a safe refusal, not the model's draft */}
      {wasBlocked && (
        <div
          className="flex items-start gap-2 px-2.5 py-2 text-[11px] leading-snug"
          style={{
            color: 'var(--color-error)',
            background: 'var(--color-error-bg)',
            borderBottom: `1px solid var(--color-error-border)`,
          }}
        >
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" className="flex-shrink-0 mt-[2px]" aria-hidden>
            <path d="M12 9v4M12 17h.01" />
            <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          </svg>
          <span>Low evidence match — this answer could not be fully grounded in the retrieved sources. Verify independently.</span>
        </div>
      )}

      {/* Header pill */}
      <button
        onClick={() => hasDetail && setExpanded(v => !v)}
        className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left"
        style={{
          background: 'transparent',
          border: 'none',
          cursor: hasDetail ? 'pointer' : 'default',
        }}
      >
        <span className="flex-shrink-0 flex items-center" style={{ color: meta.color }}>
          {meta.icon}
        </span>

        <span
          className="flex-1 text-[11.5px] font-semibold leading-snug"
          style={{ color: meta.color }}
        >
          {claimsLabel}
        </span>

        <span
          className="text-[10.5px] font-bold tabular-nums px-1.5 py-0.5 rounded-[4px] flex-shrink-0"
          style={{ color: meta.color, background: 'var(--bg-card)', border: `1px solid ${meta.border}` }}
        >
          {pct}%
        </span>

        {wasRegenerated && !wasBlocked && (
          <span
            className="text-[9.5px] font-semibold uppercase px-1.5 py-0.5 rounded-[4px] flex-shrink-0"
            style={{ color: 'var(--text-muted)', background: 'var(--bg-card)', border: '1px solid var(--border-default)', letterSpacing: '0.03em' }}
            title="The first draft failed grounding and was rewritten once using only the retrieved evidence"
          >
            Rewritten
          </span>
        )}

        {hasDetail && (
          <svg
            width="11" height="11" viewBox="0 0 24 24" fill="none"
            stroke={meta.color} strokeWidth="2.5"
            className="flex-shrink-0"
            style={{ transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}
            aria-hidden
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        )}
      </button>

      {/* Expandable detail */}
      {hasDetail && (
        <div ref={bodyRef} style={{ overflow: 'hidden', height: expanded ? 'auto' : 0 }}>
          <div
            className="px-2.5 pb-2.5 pt-0.5 flex flex-col gap-2"
            style={{ borderTop: `1px solid ${meta.border}` }}
          >
            {verification?.summary && (
              <p
                className="m-0 mt-2 text-[11px] leading-snug"
                style={{ color: 'var(--text-secondary)', fontStyle: 'italic' }}
              >
                {verification.summary}
              </p>
            )}

            {unsupported.length > 0 && (
              <div className="flex flex-col gap-1">
                <p
                  className="m-0 text-[10.5px] font-semibold uppercase tracking-wide"
                  style={{ color: 'var(--accent-red)', letterSpacing: '0.04em' }}
                >
                  Claims not found in sources
                </p>
                {unsupported.map((claim, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-1.5 text-[11px] leading-snug px-2 py-1 rounded-[4px]"
                    style={{ color: 'var(--text-primary)', background: 'var(--accent-red-bg)', border: '1px solid var(--accent-red-border)' }}
                  >
                    <span className="flex-shrink-0 mt-[3px]" style={{ color: 'var(--accent-red)' }}>
                      <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" aria-hidden>
                        <line x1="6" y1="6" x2="18" y2="18" /><line x1="18" y1="6" x2="6" y2="18" />
                      </svg>
                    </span>
                    <span>{claim}</span>
                  </div>
                ))}
              </div>
            )}

            {(verdict === 'partially_grounded' || verdict === 'unsupported') && onRefine && question && (
              <button
                onClick={() => onRefine(question)}
                className="self-start text-[11px] font-semibold"
                style={{
                  color: meta.color,
                  background: 'transparent',
                  border: 'none',
                  padding: 0,
                  cursor: 'pointer',
                  textDecoration: 'underline',
                  textUnderlineOffset: '2px',
                }}
              >
                Refine this question →
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
