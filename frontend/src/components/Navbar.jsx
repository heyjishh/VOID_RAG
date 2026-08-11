import { useRef, useEffect } from 'react'
import gsap from 'gsap'
import { prefersReducedMotion } from '../lib/motion.js'

function ScalesIcon({ size = 22, color = 'currentColor' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <line x1="12" y1="3" x2="12" y2="22" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="4" y1="7" x2="20" y2="7" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="4" y1="7" x2="2" y2="13" stroke={color} strokeWidth="1.2" strokeLinecap="round" />
      <line x1="20" y1="7" x2="22" y2="13" stroke={color} strokeWidth="1.2" strokeLinecap="round" />
      <path d="M1 13 Q4 17 7 13" stroke={color} strokeWidth="1.4" strokeLinecap="round" fill="none" />
      <path d="M17 13 Q20 17 23 13" stroke={color} strokeWidth="1.4" strokeLinecap="round" fill="none" />
      <path d="M9.5 22 Q12 20.5 14.5 22" stroke={color} strokeWidth="1.4" strokeLinecap="round" fill="none" />
    </svg>
  )
}

export default function Navbar({
  onSettingsClick,
  onToggleSources,
  sourcesCollapsed,
  sourcesCount,
  onToggleHistory,
  historyCollapsed,
}) {
  const wordmarkRef = useRef(null)
  const logoRef = useRef(null)

  useEffect(() => {
    if (prefersReducedMotion()) return
    // Entrance animation
    gsap.fromTo(logoRef.current,
      { opacity: 0, scale: 0.9, rotate: -8 },
      { opacity: 1, scale: 1, rotate: 0, duration: 0.6, ease: 'back.out(1.4)', delay: 0.1 }
    )
    gsap.fromTo(wordmarkRef.current,
      { opacity: 0, x: -8 },
      { opacity: 1, x: 0, duration: 0.45, ease: 'power2.out', delay: 0.25 }
    )
  }, [])

  return (
    <header
      className="sticky top-0 z-50 h-[52px] flex items-center justify-between px-6"
      style={{
        background: 'var(--bg-card)',
        borderBottom: '1px solid var(--border-default)',
        boxShadow: '0 1px 0 var(--border-default)',
      }}
    >
      {/* Brand mark */}
      <div className="flex items-center gap-3">
        <div
          ref={logoRef}
          className="w-[34px] h-[34px] rounded-[8px] flex items-center justify-center flex-shrink-0"
          style={{
            background: 'var(--primary)',
            boxShadow: 'var(--shadow-primary)',
          }}
        >
          <ScalesIcon size={18} color="var(--on-primary)" />
        </div>

        <div ref={wordmarkRef} className="flex items-baseline gap-1.5">
          <span
            className="font-display text-[20px] tracking-[0.04em] leading-none"
            style={{
              color: 'var(--text-primary)',
              fontStyle: 'italic',
              fontWeight: 600,
            }}
          >
            Jury
          </span>
          <span
            className="text-[13px] font-semibold tracking-tight leading-none"
            style={{ color: 'var(--ink)', letterSpacing: '-0.01em' }}
          >
            AI
          </span>
          <span
            className="text-[10px] font-medium px-1.5 py-[2px] rounded-[4px] ml-0.5"
            style={{
              color: 'var(--text-muted)',
              background: 'var(--bg-soft)',
              border: '1px solid var(--border-default)',
              letterSpacing: '0.03em',
            }}
          >
            Legal Research
          </span>
        </div>
      </div>

      {/* Right actions */}
      <div className="flex items-center gap-2">
        <NavButton
          onClick={onToggleHistory}
          active={!historyCollapsed}
          title={historyCollapsed ? 'Show conversation history' : 'Hide conversation history'}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="9" />
            <polyline points="12 7 12 12 15.5 14" />
          </svg>
          History
        </NavButton>

        <NavButton
          onClick={onToggleSources}
          active={!sourcesCollapsed}
          title={sourcesCollapsed ? 'Show sources panel' : 'Hide sources panel'}
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <line x1="15" y1="3" x2="15" y2="21" />
          </svg>
          Sources
          {sourcesCount > 0 && (
            <span
              className="text-[9px] font-bold px-1.5 py-0.5 rounded-full min-w-[17px] text-center leading-none"
              style={{
                background: 'var(--gold)',
                color: 'var(--on-primary)',
              }}
            >
              {sourcesCount}
            </span>
          )}
        </NavButton>

        <NavButton onClick={onSettingsClick} title="Settings">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="3" />
            <path d="M12 2v3M12 19v3M4.22 4.22l2.12 2.12M17.66 17.66l2.12 2.12M2 12h3M19 12h3M4.22 19.78l2.12-2.12M17.66 6.34l2.12-2.12" />
          </svg>
          Settings
        </NavButton>
      </div>
    </header>
  )
}

function NavButton({ children, onClick, active = false, title }) {
  const ref = useRef(null)

  function handleEnter() {
    if (prefersReducedMotion()) return
    gsap.to(ref.current, { y: -1, duration: 0.15, ease: 'power2.out' })
  }
  function handleLeave() {
    if (prefersReducedMotion()) return
    gsap.to(ref.current, { y: 0, duration: 0.15, ease: 'power2.out' })
  }

  return (
    <button
      ref={ref}
      onClick={onClick}
      title={title}
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
      className="flex items-center gap-1.5 px-3 py-1.5 rounded-[var(--radius-sm)] text-[12px] font-medium transition-colors duration-150"
      style={{
        border: active ? '1px solid var(--ink-border)' : '1px solid var(--border-default)',
        background: active ? 'var(--ink-light)' : 'transparent',
        color: active ? 'var(--ink)' : 'var(--text-secondary)',
        cursor: 'pointer',
      }}
    >
      {children}
    </button>
  )
}
