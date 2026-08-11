import { useState, useRef, useEffect } from 'react'
import gsap from 'gsap'
import { prefersReducedMotion } from '../lib/motion.js'

// Dual-tone: --ink owns the retrieval → generation pipeline (the AI's own
// work), --gold owns authority/ranking, --color-info owns external web
// evidence. --primary (brand crimson) is deliberately absent here — it is
// reserved for the user's own voice and the primary CTA, not AI activity.
const STEP_META = {
  retrieval: {
    label: 'Corpus Search',
    color: 'var(--ink)',
    bg: 'var(--ink-light)',
    icon: (
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
        <circle cx="11" cy="11" r="8" /><line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
    ),
  },
  web: {
    label: 'Web Search',
    color: 'var(--color-info)',
    bg: 'var(--color-info-bg)',
    icon: (
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
        <circle cx="12" cy="12" r="10" />
        <line x1="2" y1="12" x2="22" y2="12" />
        <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
      </svg>
    ),
  },
  merge: {
    label: 'Evidence Synthesis',
    color: 'var(--sage)',
    bg: 'var(--sage-light)',
    icon: (
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
        <polyline points="18 8 22 12 18 16" />
        <line x1="2" y1="12" x2="22" y2="12" />
        <polyline points="6 8 2 12 6 16" />
      </svg>
    ),
  },
  generate: {
    label: 'Drafting Opinion',
    color: 'var(--ink)',
    bg: 'var(--ink-light)',
    icon: (
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
        <line x1="17" y1="10" x2="3" y2="10" />
        <line x1="21" y1="6" x2="3" y2="6" />
        <line x1="21" y1="14" x2="3" y2="14" />
        <line x1="17" y1="18" x2="3" y2="18" />
      </svg>
    ),
  },
  filter: {
    label: 'Filtering Sources',
    color: 'var(--accent-yellow)',
    bg: 'var(--accent-yellow-bg)',
    icon: (
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
        <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
      </svg>
    ),
  },
  rank: {
    label: 'Authority Ranking',
    color: 'var(--gold)',
    bg: 'var(--gold-light)',
    icon: (
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
        <line x1="18" y1="20" x2="18" y2="10" /><line x1="12" y1="20" x2="12" y2="4" /><line x1="6" y1="20" x2="6" y2="14" />
      </svg>
    ),
  },
  verify: {
    label: 'Verifying Groundedness',
    color: 'var(--sage)',
    bg: 'var(--sage-light)',
    icon: (
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2 4 5v6c0 5 3.4 8.5 8 10 4.6-1.5 8-5 8-10V5l-8-3z" />
        <polyline points="9 12 11.5 14.5 15.5 9.5" />
      </svg>
    ),
  },
  default: {
    label: 'Processing',
    color: 'var(--text-muted)',
    bg: 'var(--bg-soft)',
    icon: (
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
        <circle cx="12" cy="12" r="3" />
        <path d="M12 2v3M12 19v3M4.22 4.22l2.12 2.12M17.66 17.66l2.12 2.12M2 12h3M19 12h3M4.22 19.78l2.12-2.12M17.66 6.34l2.12-2.12" />
      </svg>
    ),
  },
}

// Backend emits {step, detail}; map known step names to a meta entry so the
// verification step reads as a distinct shield rather than generic "Processing".
const STEP_NAME_META = {
  internal_retrieval_start: 'retrieval',
  internal_retrieval_done: 'retrieval',
  web_search_start: 'web',
  web_search_done: 'web',
  evidence_merged: 'merge',
  generating_answer: 'generate',
  verifying_answer: 'verify',
}

function StepRow({ step, isLast, isActive }) {
  const meta = STEP_META[step.step_type] || STEP_META[STEP_NAME_META[step.step]] || STEP_META.default
  const rowRef = useRef(null)

  useEffect(() => {
    if (!rowRef.current || prefersReducedMotion()) return
    gsap.fromTo(
      rowRef.current,
      { opacity: 0, x: -10 },
      { opacity: 1, x: 0, duration: 0.3, ease: 'power2.out' }
    )
  }, [])

  return (
    <div ref={rowRef} className="flex items-start gap-2.5 relative" style={prefersReducedMotion() ? undefined : { opacity: 0 }}>
      {/* Timeline dot */}
      <div
        className="absolute left-[-20px] top-[3px] w-[9px] h-[9px] rounded-full flex-shrink-0"
        style={{
          background: meta.color,
          boxShadow: `0 0 0 2px var(--bg-soft), 0 0 0 3px ${meta.color}40`,
        }}
      />

      {/* Step icon badge */}
      <div
        className="w-5 h-5 rounded-[4px] flex items-center justify-center flex-shrink-0 mt-[1px]"
        style={{ background: meta.bg, color: meta.color }}
      >
        {meta.icon}
      </div>

      {/* Text */}
      <div className="min-w-0 flex-1 pt-[1px]">
        <p
          className="m-0 text-[11.5px] font-semibold leading-snug"
          style={{ color: 'var(--text-primary)' }}
        >
          {step.step_name || meta.label}
        </p>
        {step.detail && (
          <p
            className="m-0 mt-0.5 text-[11px] leading-snug line-clamp-2"
            style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}
          >
            {step.detail}
          </p>
        )}
      </div>

      {/* Spinner for the active (last) step */}
      {isActive && isLast && (
        <div
          className="flex-shrink-0 w-3.5 h-3.5 rounded-full mt-[1px]"
          style={{
            border: `2px solid ${meta.color}30`,
            borderTopColor: meta.color,
            animation: 'spin 0.75s linear infinite',
          }}
        />
      )}
    </div>
  )
}

export default function ReasoningTimeline({ steps = [], isActive = false, expanded: expandedProp }) {
  const [internalExpanded, setInternalExpanded] = useState(true)
  const expanded = expandedProp !== undefined ? expandedProp : internalExpanded
  const bodyRef = useRef(null)

  const toggleExpanded = () => {
    if (expandedProp === undefined) setInternalExpanded(v => !v)
  }

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

  if (steps.length === 0) return null

  return (
    <div
      className="my-2 overflow-hidden"
      style={{
        borderRadius: 'var(--radius-md)',
        border: '1px solid var(--border-default)',
        background: 'var(--bg-soft)',
      }}
    >
      {/* Header */}
      <button
        onClick={toggleExpanded}
        className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-left transition-colors"
        style={{ background: 'transparent', border: 'none', cursor: 'pointer' }}
        onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-card)' }}
        onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
      >
        {isActive ? (
          <span className="flex gap-1 mr-0.5" data-motion="feedback">
            {[0, 1, 2].map(i => (
              <span
                key={i}
                className="w-1.5 h-1.5 rounded-full inline-block"
                style={{
                  background: 'var(--ink)',
                  animation: 'inkPulse 1.4s ease-in-out infinite',
                  animationDelay: `${i * 0.2}s`,
                }}
              />
            ))}
          </span>
        ) : (
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--sage)" strokeWidth="2.5">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        )}

        <span
          className="flex-1 text-[11.5px] font-semibold tracking-wide uppercase"
          style={{ color: isActive ? 'var(--ink)' : 'var(--sage)', letterSpacing: '0.05em' }}
        >
          {isActive ? 'Researching…' : `Research complete · ${steps.length} step${steps.length !== 1 ? 's' : ''}`}
        </span>

        <svg
          width="11"
          height="11"
          viewBox="0 0 24 24"
          fill="none"
          stroke="var(--text-muted)"
          strokeWidth="2.5"
          style={{ transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}
        >
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>

      {/* Step list */}
      <div
        ref={bodyRef}
        style={{ overflow: 'hidden', height: expanded ? 'auto' : 0 }}
      >
        <div
          className="pb-3 px-3.5"
          style={{ marginLeft: '18px', borderLeft: `1.5px solid var(--border-default)`, paddingLeft: '20px' }}
        >
          <div className="flex flex-col gap-2.5 pt-1">
            {steps.map((step, i) => (
              <StepRow
                key={i}
                step={step}
                isLast={i === steps.length - 1}
                isActive={isActive}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
