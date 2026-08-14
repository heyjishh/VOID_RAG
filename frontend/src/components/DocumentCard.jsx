import { useRef } from 'react'
import gsap from 'gsap'

function highlightText(text, query) {
  if (!query) return text
  const words = query
    .toLowerCase()
    .split(/\s+/)
    .filter(w => w.length > 3)
  if (words.length === 0) return text

  const pattern = new RegExp(`(${words.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'gi')
  const parts = text.split(pattern)
  return parts.map((part, i) =>
    pattern.test(part)
      ? <mark key={i} className="source-highlight">{part}</mark>
      : part
  )
}

export default function DocumentCard({ chunk, question }) {
  const cardRef = useRef(null)

  function handleHover(enter) {
    if (!cardRef.current) return
    gsap.to(cardRef.current, {
      y: enter ? -2 : 0,
      boxShadow: enter
        ? '0 0 0 1px var(--sage-border)'
        : 'var(--shadow-card)',
      duration: 0.2,
      ease: 'power2.out',
    })
  }

  const scorePercent = Math.round(chunk.score * 100)
  const filename = chunk.source.split('/').pop()

  return (
    <div
      ref={cardRef}
      className="doc-card"
      onMouseEnter={() => handleHover(true)}
      onMouseLeave={() => handleHover(false)}
      style={{
        background: 'var(--bg-main)',
        border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-md)',
        padding: '14px 16px',
        boxShadow: 'var(--shadow-card)',
        cursor: 'default',
        transition: 'border-color 0.15s',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', marginBottom: '10px' }}>
        {/* PDF icon */}
        <div style={{
          width: '32px',
          height: '32px',
          borderRadius: '6px',
          background: chunk.verified ? 'var(--sage-light)' : 'var(--bg-soft)',
          border: `1px solid ${chunk.verified ? 'var(--sage-border)' : 'var(--border-default)'}`,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
            stroke={chunk.verified ? 'var(--color-primary)' : 'var(--text-muted)'} strokeWidth="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14,2 14,8 20,8" />
          </svg>
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{
            margin: 0,
            fontWeight: 600,
            fontSize: '12px',
            color: 'var(--text-primary)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {filename}
          </p>
          <p style={{ margin: '2px 0 0', fontSize: '11px', color: 'var(--text-muted)' }}>
            Page {chunk.page + 1}
          </p>
        </div>

        {/* Score badge */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '4px' }}>
          {chunk.verified && (
            <span style={{
              fontSize: '10px',
              fontWeight: 600,
              color: 'var(--color-primary)',
              background: 'var(--sage-light)',
              border: '1px solid var(--sage-border)',
              borderRadius: '4px',
              padding: '1px 6px',
              letterSpacing: '0.2px',
            }}>
              ✓ cited
            </span>
          )}
          <span style={{
            fontSize: '10px',
            color: 'var(--text-muted)',
            background: 'var(--bg-soft)',
            borderRadius: '4px',
            padding: '1px 5px',
          }}>
            {scorePercent}%
          </span>
        </div>
      </div>

      {/* Score bar */}
      <div style={{
        height: '3px',
        background: 'var(--border-default)',
        borderRadius: '2px',
        marginBottom: '10px',
        overflow: 'hidden',
      }}>
        <div style={{
          height: '100%',
          width: `${scorePercent}%`,
          background: chunk.verified ? 'var(--color-primary)' : 'var(--text-muted)',
          borderRadius: '2px',
          transition: 'width 0.6s ease',
        }} />
      </div>

      {/* Text excerpt with highlighting */}
      <p style={{
        margin: 0,
        fontSize: '12px',
        color: 'var(--text-secondary)',
        lineHeight: 1.65,
        display: '-webkit-box',
        WebkitLineClamp: 5,
        WebkitBoxOrient: 'vertical',
        overflow: 'hidden',
      }}>
        {highlightText(chunk.text, question)}
      </p>
    </div>
  )
}
