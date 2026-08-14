import { useEffect, useRef, useState } from 'react'
import gsap from 'gsap'
import { Plus, Search, Trash2, FolderOpen, Scale } from 'lucide-react'
import { prefersReducedMotion } from '../lib/motion.js'

function formatTimestamp(ms) {
  const date = new Date(ms)
  const now = new Date()
  const sameDay = date.toDateString() === now.toDateString()
  if (sameDay) return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  const sameYear = date.getFullYear() === now.getFullYear()
  return date.toLocaleDateString([], sameYear ? { month: 'short', day: 'numeric' } : { year: 'numeric', month: 'short', day: 'numeric' })
}

export default function MatterSidebar({ conversations, activeId, onSelect, onNew, onDelete, collapsed }) {
  const listRef = useRef(null)
  const [query, setQuery] = useState('')

  useEffect(() => {
    if (!listRef.current || prefersReducedMotion()) return
    const rows = listRef.current.querySelectorAll('.matter-row')
    if (rows.length === 0) return
    gsap.fromTo(rows, { opacity: 0, x: -8 }, { opacity: 1, x: 0, duration: 0.24, stagger: 0.035, ease: 'power2.out' })
  }, [conversations.length])

  const filtered = query.trim()
    ? conversations.filter(c => (c.title || '').toLowerCase().includes(query.trim().toLowerCase()))
    : conversations

  return (
    <aside
      className="flex flex-col overflow-hidden flex-shrink-0"
      style={{
        width: collapsed ? '0' : '272px',
        minWidth: 0,
        transition: 'width 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
        willChange: 'width',
        borderRight: collapsed ? 'none' : '1px solid var(--border-default)',
        background: 'var(--bg-soft)',
        backdropFilter: 'blur(24px) saturate(160%)',
        WebkitBackdropFilter: 'blur(24px) saturate(160%)',
      }}
    >
      {/* Panel header */}
      <div className="px-3.5 pt-3.5 pb-2.5 flex-shrink-0" style={{ background: 'var(--bg-soft)' }}>
        <div className="flex items-center gap-2 mb-2.5">
          <FolderOpen size={14} style={{ color: 'var(--ink)' }} />
          <span className="text-[10.5px] font-bold uppercase" style={{ color: 'var(--text-muted)', letterSpacing: '0.1em' }}>
            Matters
          </span>
          <span
            className="text-[10px] font-semibold tabular-nums"
            style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
          >
            {conversations.length}
          </span>
          <button
            type="button"
            onClick={onNew}
            title="New matter / research"
            className="ml-auto w-7 h-7 rounded-[6px] flex items-center justify-center transition-colors duration-150"
            style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', color: 'var(--ink)', cursor: 'pointer' }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--ink)'; e.currentTarget.style.background = 'var(--ink-light)' }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border-default)'; e.currentTarget.style.background = 'var(--bg-card)' }}
          >
            <Plus size={14} />
          </button>
        </div>

        <div className="flex items-center gap-2 px-2.5 h-8 rounded-[7px]" style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)' }}>
          <Search size={12} style={{ color: 'var(--text-muted)' }} />
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="Filter matters…"
            className="flex-1 bg-transparent outline-none text-[12px] min-w-0"
            style={{ color: 'var(--text-primary)', border: 'none', fontFamily: 'var(--font-sans)' }}
          />
        </div>
      </div>

      {/* Matter list */}
      <div ref={listRef} className="flex-1 overflow-y-auto px-2 pb-3 pt-1 flex flex-col gap-1">
        {filtered.length === 0 && (
          <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
            <Scale size={22} style={{ color: 'var(--border-input)' }} />
            <p className="m-0 text-[11.5px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
              {query.trim() ? 'No matters match your filter.' : 'Matters you work on appear here. Start one with New matter.'}
            </p>
            {!query.trim() && (
              <button
                type="button"
                onClick={onNew}
                className="mt-1 px-3 py-1.5 rounded-[6px] text-[11.5px] font-semibold"
                style={{ background: 'var(--primary)', color: 'var(--on-primary)', border: 'none', cursor: 'pointer' }}
              >
                New matter
              </button>
            )}
          </div>
        )}

        {filtered.map(conv => {
          const active = conv.id === activeId
          return (
            <div
              key={conv.id}
              className="matter-row group relative flex items-start gap-2.5 px-2.5 py-2.5 rounded-[2px] cursor-pointer"
              onClick={() => onSelect(conv.id)}
              style={{
                background: active ? 'var(--bg-card)' : 'transparent',
                border: active ? '1px solid var(--ink-border)' : '1px solid transparent',
                boxShadow: active ? 'var(--shadow-card)' : 'none',
                transition: 'background 0.15s, border-color 0.15s',
              }}
              onMouseEnter={e => { if (!active) { e.currentTarget.style.background = 'var(--bg-card)' } }}
              onMouseLeave={e => { if (!active) { e.currentTarget.style.background = 'transparent' } }}
            >
              <span
                className="mt-[1px] w-6 h-6 rounded-[6px] flex items-center justify-center flex-shrink-0"
                style={{ background: active ? 'var(--ink)' : 'var(--bg-main)', boxShadow: `inset 0 0 0 1px ${active ? 'transparent' : 'var(--border-default)'}` }}
              >
                <Scale size={12} style={{ color: active ? 'var(--on-ink)' : 'var(--text-muted)' }} />
              </span>

              <div className="flex-1 min-w-0">
                <p
                  className="m-0 text-[12.5px] font-medium truncate"
                  style={{ color: active ? 'var(--text-primary)' : 'var(--text-secondary)' }}
                >
                  {conv.title || 'Untitled matter'}
                </p>
                <p className="m-0 mt-0.5 text-[10px] tabular-nums" style={{ color: 'var(--text-muted)' }}>
                  {formatTimestamp(conv.updatedAt)}
                </p>
              </div>

              <button
                onClick={e => { e.stopPropagation(); onDelete(conv.id) }}
                title="Delete matter"
                className="opacity-0 group-hover:opacity-100 flex-shrink-0 w-6 h-6 rounded-[5px] flex items-center justify-center transition-colors"
                style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
                onMouseEnter={e => { e.currentTarget.style.background = 'var(--color-error-bg)'; e.currentTarget.style.color = 'var(--color-error)' }}
                onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-muted)' }}
              >
                <Trash2 size={12} />
              </button>
            </div>
          )
        })}
      </div>
    </aside>
  )
}