import { useEffect, useRef } from 'react'
import gsap from 'gsap'
import { prefersReducedMotion } from '../lib/motion.js'

function formatTimestamp(ms) {
  const date = new Date(ms)
  const now = new Date()
  const sameDay = date.toDateString() === now.toDateString()
  if (sameDay) return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  const sameYear = date.getFullYear() === now.getFullYear()
  return date.toLocaleDateString([], sameYear ? { month: 'short', day: 'numeric' } : { year: 'numeric', month: 'short', day: 'numeric' })
}

export default function ConversationSidebar({ conversations, activeId, onSelect, onNew, onDelete, collapsed }) {
  const listRef = useRef(null)

  useEffect(() => {
    if (!listRef.current || prefersReducedMotion()) return
    const rows = listRef.current.querySelectorAll('.conv-row')
    if (rows.length === 0) return
    gsap.fromTo(rows, { opacity: 0, x: -6 }, { opacity: 1, x: 0, duration: 0.22, stagger: 0.03, ease: 'power2.out' })
  }, [conversations.length])

  return (
    <aside
      className="flex flex-col overflow-hidden flex-shrink-0"
      style={{
        width: collapsed ? '0' : '250px',
        minWidth: 0,
        transition: 'width 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
        willChange: 'width',
        borderRight: collapsed ? 'none' : '1px solid var(--border-default)',
        background: 'var(--bg-soft)',
      }}
    >
      <div className="p-3 flex-shrink-0">
        <button
          onClick={onNew}
          className="w-full flex items-center justify-center gap-1.5 py-2 rounded-[var(--radius-sm)] text-[12px] font-semibold"
          style={{
            border: '1px solid var(--border-default)',
            background: 'var(--bg-card)',
            color: 'var(--text-primary)',
            cursor: 'pointer',
            transition: 'border-color 0.15s, color 0.15s',
          }}
          onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--ink)'; e.currentTarget.style.color = 'var(--ink)' }}
          onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border-default)'; e.currentTarget.style.color = 'var(--text-primary)' }}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden>
            <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          New conversation
        </button>
      </div>

      <div ref={listRef} className="flex-1 overflow-y-auto px-2 pb-3 flex flex-col gap-1">
        {conversations.length === 0 && (
          <p className="m-0 px-2.5 py-4 text-[11.5px] text-center" style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>
            Your conversations will appear here
          </p>
        )}

        {conversations.map(conv => {
          const active = conv.id === activeId
          return (
            <div
              key={conv.id}
              className="conv-row group relative flex items-start gap-2 px-2.5 py-2 rounded-[var(--radius-sm)] cursor-pointer"
              onClick={() => onSelect(conv.id)}
              style={{
                background: active ? 'var(--ink-light)' : 'transparent',
                border: active ? '1px solid var(--ink-border)' : '1px solid transparent',
                transition: 'background 0.15s, border-color 0.15s',
              }}
              onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--bg-card)' }}
              onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent' }}
            >
              <div className="flex-1 min-w-0">
                <p
                  className="m-0 text-[12px] font-medium truncate"
                  style={{ color: active ? 'var(--ink)' : 'var(--text-primary)' }}
                >
                  {conv.title}
                </p>
                <p className="m-0 mt-0.5 text-[10px]" style={{ color: 'var(--text-muted)' }}>
                  {formatTimestamp(conv.updatedAt)}
                </p>
              </div>
              <button
                onClick={e => { e.stopPropagation(); onDelete(conv.id) }}
                title="Delete conversation"
                className="opacity-0 group-hover:opacity-100 flex-shrink-0 w-5 h-5 rounded-[4px] flex items-center justify-center"
                style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
                onMouseEnter={e => { e.currentTarget.style.color = 'var(--color-error)' }}
                onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-muted)' }}
              >
                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden>
                  <line x1="6" y1="6" x2="18" y2="18" /><line x1="18" y1="6" x2="6" y2="18" />
                </svg>
              </button>
            </div>
          )
        })}
      </div>
    </aside>
  )
}
