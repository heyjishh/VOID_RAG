import { forwardRef } from 'react'

const CollapsedPanelPill = forwardRef(function CollapsedPanelPill({ side, label, onClick, title }, ref) {
  const isLeft = side === 'left'
  return (
    <div
      className={`absolute ${isLeft ? 'left-0' : 'right-0'} top-0 bottom-0 flex items-center z-20`}
      style={{ width: '28px' }}
    >
      <button
        ref={ref}
        onClick={onClick}
        title={title}
        style={{
          writingMode: 'vertical-lr',
          textOrientation: 'mixed',
          width: '28px',
          height: '110px',
          background: 'var(--bg-card)',
          borderRight: isLeft ? '1px solid var(--border-default)' : 'none',
          borderLeft: isLeft ? 'none' : '1px solid var(--border-default)',
          borderTop: '1px solid var(--border-default)',
          borderBottom: '1px solid var(--border-default)',
          borderRadius: isLeft ? '0 8px 8px 0' : '8px 0 0 8px',
          color: 'var(--text-muted)',
          fontSize: '10px',
          fontWeight: 600,
          cursor: 'pointer',
          letterSpacing: '0.04em',
          textTransform: 'uppercase',
          transition: 'background 0.15s, color 0.15s',
          fontFamily: "'DM Sans', sans-serif",
        }}
        onMouseEnter={e => {
          e.currentTarget.style.background = 'var(--ink-light)'
          e.currentTarget.style.color = 'var(--ink)'
          e.currentTarget.style.borderColor = 'var(--ink-border)'
        }}
        onMouseLeave={e => {
          e.currentTarget.style.background = 'var(--bg-card)'
          e.currentTarget.style.color = 'var(--text-muted)'
          e.currentTarget.style.borderColor = 'var(--border-default)'
        }}
      >
        {label}
      </button>
    </div>
  )
})

export default CollapsedPanelPill
