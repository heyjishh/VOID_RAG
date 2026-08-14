import { useTheme } from '../lib/theme.js'

const OPTIONS = [
  { id: 'light', label: 'Light' },
  { id: 'dark', label: 'Dark' },
  { id: 'system', label: 'System' },
]

export default function ThemeToggle() {
  const [theme, setTheme] = useTheme()

  return (
    <div
      role="radiogroup"
      aria-label="Theme"
      className="flex rounded-[var(--radius-sm)] p-[3px] gap-1"
      style={{ background: 'var(--bg-soft)', border: '1px solid var(--border-default)' }}
    >
      {OPTIONS.map(opt => {
        const active = theme === opt.id
        return (
          <button
            key={opt.id}
            role="radio"
            aria-checked={active}
            onClick={() => setTheme(opt.id)}
            className="flex-1 text-[12px] font-medium py-1.5 rounded-[4px] transition-colors duration-150"
            style={{
              background: active ? 'var(--ink)' : 'transparent',
              color: active ? 'var(--on-primary)' : 'var(--text-secondary)',
              border: 'none',
              cursor: 'pointer',
              fontFamily: "var(--font-sans)",
            }}
          >
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}
