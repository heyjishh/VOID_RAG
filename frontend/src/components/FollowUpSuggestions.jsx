import { useEffect, useRef } from 'react'
import gsap from 'gsap'
import { prefersReducedMotion } from '../lib/motion.js'

export default function FollowUpSuggestions({ questions, onSelect }) {
  const containerRef = useRef(null)

  useEffect(() => {
    if (!containerRef.current || prefersReducedMotion()) return
    const chips = containerRef.current.querySelectorAll('.followup-chip')
    if (chips.length === 0) return
    gsap.fromTo(
      chips,
      { opacity: 0, y: 6 },
      { opacity: 1, y: 0, duration: 0.25, stagger: 0.05, ease: 'power2.out', delay: 0.1 }
    )
  }, [questions])

  if (!questions || questions.length === 0) return null

  return (
    <div ref={containerRef} className="flex gap-2 flex-wrap mt-2 ml-[34px]">
      {questions.map(q => (
        <button
          key={q}
          className="followup-chip px-3 py-1.5 text-[11.5px] font-medium rounded-[var(--radius-sm)] cursor-pointer"
          onClick={() => onSelect(q)}
          style={{
            border: '1px solid var(--ink-border)',
            background: 'var(--ink-light)',
            color: 'var(--ink)',
            transition: 'border-color 0.15s, background 0.15s',
          }}
          onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-card)' }}
          onMouseLeave={e => { e.currentTarget.style.background = 'var(--ink-light)' }}
        >
          {q}
        </button>
      ))}
    </div>
  )
}
