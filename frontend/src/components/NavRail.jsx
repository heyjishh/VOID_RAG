import { useState } from 'react'
import { MessagesSquare, FilePen, Paperclip, Settings, LogOut, ChevronDown } from 'lucide-react'
import { logout, getDisplayName } from '../lib/session.js'

const NAV_ITEMS = [
  { id: 'ask', label: 'Research', icon: <MessagesSquare size={19} /> },
  { id: 'interact', label: 'Interact', icon: <Paperclip size={19} /> },
  { id: 'draft', label: 'Drafts', icon: <FilePen size={19} /> },
]

export default function NavRail({ mode, onModeChange, onSettingsClick, user, onLogout, horizontal = false }) {
  const [menuOpen, setMenuOpen] = useState(false)
  const initials = (getDisplayName(user) || 'R').split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase()

  if (horizontal) {
    return (
      <nav
        className="flex items-center justify-around flex-shrink-0 relative z-40"
        style={{
          height: 56,
          background: 'var(--bg-card)',
          borderTop: '1px solid var(--border-default)',
          paddingBottom: 'env(safe-area-inset-bottom, 0px)',
        }}
      >
        {NAV_ITEMS.map(item => {
          const active = mode === item.id
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onModeChange(item.id)}
              className="flex flex-col items-center justify-center gap-0.5 h-full px-4 transition-colors duration-150"
              style={{
                background: 'transparent',
                border: 'none',
                color: active ? 'var(--ink)' : 'var(--text-muted)',
                cursor: 'pointer',
              }}
            >
              {item.icon}
              <span className="text-[9px] font-semibold uppercase" style={{ letterSpacing: '0.04em' }}>
                {item.label}
              </span>
            </button>
          )
        })}

        <button
          type="button"
          onClick={onSettingsClick}
          className="flex flex-col items-center justify-center gap-0.5 h-full px-4 transition-colors duration-150"
          style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
        >
          <Settings size={19} />
          <span className="text-[9px] font-semibold uppercase" style={{ letterSpacing: '0.04em' }}>Settings</span>
        </button>

        <div className="relative">
          <button
            type="button"
            onClick={() => setMenuOpen(v => !v)}
            title={getDisplayName(user)}
            className="flex flex-col items-center justify-center gap-0.5 h-full px-4"
            style={{ background: 'transparent', border: 'none', cursor: 'pointer' }}
          >
            <span
              className="w-7 h-7 rounded-full flex items-center justify-center text-[10.5px] font-bold"
              style={{ background: 'var(--primary-light)', color: 'var(--primary)', boxShadow: 'var(--shadow-primary-sm)' }}
            >
              {initials}
            </span>
          </button>

          {menuOpen && (
            <>
              <div className="fixed inset-0" style={{ zIndex: 45 }} onClick={() => setMenuOpen(false)} />
              <div
                className="absolute bottom-full mb-2 right-0 w-[220px] rounded-[2px] p-1.5"
                style={{
                  background: 'var(--bg-soft)',
                  backdropFilter: 'blur(28px) saturate(180%)',
                  WebkitBackdropFilter: 'blur(28px) saturate(180%)',
                  border: '1px solid var(--border-default)',
                  boxShadow: 'var(--shadow-panel)',
                  zIndex: 46,
                }}
              >
                <div className="px-2.5 py-2">
                  <p className="m-0 text-[12.5px] font-semibold truncate" style={{ color: 'var(--text-primary)' }}>{getDisplayName(user)}</p>
                  <p className="m-0 mt-0.5 text-[11px] truncate" style={{ color: 'var(--text-muted)' }}>{user?.email}</p>
                </div>
                <div className="h-px my-1" style={{ background: 'var(--border-default)' }} />
                <button
                  type="button"
                  onClick={() => { setMenuOpen(false); onLogout() }}
                  className="w-full flex items-center gap-2 px-2.5 py-2 rounded-[2px] text-[12.5px] font-medium transition-colors"
                  style={{ background: 'transparent', color: 'var(--text-secondary)', cursor: 'pointer', border: 'none', textAlign: 'left' }}
                  onMouseEnter={e => { e.currentTarget.style.background = 'var(--color-error-bg)'; e.currentTarget.style.color = 'var(--color-error)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-secondary)' }}
                >
                  <LogOut size={14} />
                  Sign out
                </button>
              </div>
            </>
          )}
        </div>
      </nav>
    )
  }

  return (
    <nav
      className="hidden sm:flex flex-col items-center flex-shrink-0 relative z-40"
      style={{
        width: 64,
        background: 'var(--bg-card)',
        backdropFilter: 'blur(24px) saturate(160%)',
        WebkitBackdropFilter: 'blur(24px) saturate(160%)',
        borderRight: "1px solid var(--border-default)",
      }}
    >
      <div
        className="w-full h-[52px] flex items-center justify-center"
        style={{ borderBottom: '1px solid var(--border-default)' }}
      >
        <a
          href={import.meta.env.VITE_LANDING_URL || 'http://localhost:5173'}
          target="_blank"
          rel="noopener noreferrer"
          className="w-9 h-9 rounded-[2px] flex items-center justify-center transition-transform duration-150 hover:scale-[1.06]"
          style={{ background: 'var(--primary)', boxShadow: 'var(--shadow-primary-sm)' }}
          title="Juris AI — back to our site"
          aria-label="Juris AI home"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2">
            <path d="M12 3v18M5 7l7-4 7 4M5 17l7 4 7-4" strokeLinecap="round" strokeLinejoin="round" />
            <circle cx="12" cy="12" r="2.5" fill="#fff" stroke="none" />
          </svg>
        </a>
      </div>

      <div className="flex flex-col items-center gap-1.5 mt-4 w-full px-2">
        {NAV_ITEMS.map(item => {
          const active = mode === item.id
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onModeChange(item.id)}
              title={item.label}
              className="w-[44px] h-[40px] rounded-[2px] flex items-center justify-center transition-colors duration-150"
              style={{
                background: active ? 'var(--ink-light)' : 'transparent',
                color: active ? 'var(--ink)' : 'var(--text-muted)',
                boxShadow: active ? 'inset 0 0 0 1px var(--ink-border)' : 'none',
                cursor: 'pointer',
              }}
              onMouseEnter={e => { if (!active) { e.currentTarget.style.background = 'var(--bg-soft)'; e.currentTarget.style.color = 'var(--text-primary)' } }}
              onMouseLeave={e => { if (!active) { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-muted)' } }}
            >
              {item.icon}
            </button>
          )
        })}
      </div>

      <div className="mt-auto flex flex-col items-center gap-1.5 w-full px-2 pb-3">
        <button
          type="button"
          onClick={onSettingsClick}
          title="Workspace settings"
          className="w-[44px] h-[40px] rounded-[2px] flex items-center justify-center transition-colors duration-150"
          style={{ background: 'transparent', color: 'var(--text-muted)', cursor: 'pointer' }}
          onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-soft)'; e.currentTarget.style.color = 'var(--text-primary)' }}
          onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-muted)' }}
        >
          <Settings size={19} />
        </button>

        <div className="relative">
          <button
            type="button"
            onClick={() => setMenuOpen(v => !v)}
            title={getDisplayName(user)}
            className="w-[44px] h-[40px] rounded-[2px] flex items-center justify-center transition-colors duration-150"
            style={{ background: menuOpen ? 'rgba(255,255,255,.12)' : 'transparent', cursor: 'pointer' }}
          >
            <span
              className="w-7 h-7 rounded-full flex items-center justify-center text-[10.5px] font-bold"
              style={{ background: 'var(--primary-light)', color: 'var(--primary)', boxShadow: 'var(--shadow-primary-sm)' }}
            >
              {initials}
            </span>
          </button>

          {menuOpen && (
            <>
              <div className="fixed inset-0" style={{ zIndex: 45 }} onClick={() => setMenuOpen(false)} />
              <div
                className="absolute left-[52px] bottom-0 w-[220px] rounded-[2px] p-1.5"
                style={{
                  background: 'var(--bg-soft)',
                  backdropFilter: 'blur(28px) saturate(180%)',
                  WebkitBackdropFilter: 'blur(28px) saturate(180%)',
                  border: '1px solid var(--border-default)',
                  boxShadow: 'var(--shadow-panel)',
                  zIndex: 46,
                }}
              >
                <div className="px-2.5 py-2">
                  <p className="m-0 text-[12.5px] font-semibold truncate" style={{ color: 'var(--text-primary)' }}>{getDisplayName(user)}</p>
                  <p className="m-0 mt-0.5 text-[11px] truncate" style={{ color: 'var(--text-muted)' }}>{user?.email}</p>
                </div>
                <div className="h-px my-1" style={{ background: 'var(--border-default)' }} />
                <button
                  type="button"
                  onClick={() => { setMenuOpen(false); onLogout() }}
                  className="w-full flex items-center gap-2 px-2.5 py-2 rounded-[2px] text-[12.5px] font-medium transition-colors"
                  style={{ background: 'transparent', color: 'var(--text-secondary)', cursor: 'pointer', border: 'none', textAlign: 'left' }}
                  onMouseEnter={e => { e.currentTarget.style.background = 'var(--color-error-bg)'; e.currentTarget.style.color = 'var(--color-error)' }}
                  onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-secondary)' }}
                >
                  <LogOut size={14} />
                  Sign out
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </nav>
  )
}
