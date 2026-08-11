import { useEffect, useRef } from 'react'
import gsap from 'gsap'
import { PROMPT_LIBRARY } from '../lib/promptLibrary.js'
import { prefersReducedMotion } from '../lib/motion.js'

export default function PromptLibrary({ onSelect, onClose }) {
  const panelRef = useRef(null)

  useEffect(() => {
    function handleOutside(e) {
      if (panelRef.current && !panelRef.current.contains(e.target)) onClose()
    }
    function handleKey(e) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', handleOutside)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handleOutside)
      document.removeEventListener('keydown', handleKey)
    }
  }, [onClose])

  useEffect(() => {
    if (!panelRef.current || prefersReducedMotion()) return
    gsap.fromTo(
      panelRef.current,
      { opacity: 0, y: 8, scale: 0.98 },
      { opacity: 1, y: 0, scale: 1, duration: 0.18, ease: 'power2.out' }
    )
  }, [])

  return (
    <div
      ref={panelRef}
      className="absolute bottom-full left-0 mb-2 z-30 flex flex-col overflow-hidden"
      style={{
        width: '340px',
        maxHeight: '320px',
        borderRadius: 'var(--radius-md)',
        border: '1px solid var(--border-default)',
        background: 'var(--bg-card)',
        boxShadow: 'var(--shadow-panel)',
      }}
    >
      <div
        className="px-3.5 py-2.5 flex-shrink-0"
        style={{ borderBottom: '1px solid var(--border-default)' }}
      >
        <p className="m-0 text-[11.5px] font-semibold uppercase tracking-wide" style={{ color: 'var(--ink)', letterSpacing: '0.05em' }}>
          Skills · Prompt library
        </p>
        <p className="m-0 mt-0.5 text-[10.5px]" style={{ color: 'var(--text-muted)' }}>
          Insert a template, then edit the bracketed part
        </p>
      </div>

      <div className="flex-1 overflow-y-auto p-1.5">
        {PROMPT_LIBRARY.map(item => (
          <button
            key={item.id}
            onClick={() => onSelect(item.template)}
            className="w-full text-left px-2.5 py-2 rounded-[6px] transition-colors duration-150"
            style={{ background: 'transparent', border: 'none', cursor: 'pointer' }}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--ink-light)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
          >
            <span
              className="inline-block text-[9.5px] font-bold uppercase px-1.5 py-0.5 rounded-[3px] mb-1"
              style={{ color: 'var(--ink)', background: 'var(--ink-light)', letterSpacing: '0.04em' }}
            >
              {item.skill}
            </span>
            <p className="m-0 text-[12px] font-medium" style={{ color: 'var(--text-primary)' }}>
              {item.label}
            </p>
          </button>
        ))}
      </div>
    </div>
  )
}
