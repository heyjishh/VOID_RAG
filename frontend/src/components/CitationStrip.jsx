import * as Tooltip from '@radix-ui/react-tooltip'

function VerifiedMark({ verified }) {
  if (verified) {
    return (
      <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="var(--sage)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <polyline points="20 6 9 17 4 12" />
      </svg>
    )
  }
  return (
    <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="var(--text-muted)" strokeWidth="2.5" strokeLinecap="round" aria-hidden>
      <circle cx="12" cy="12" r="9" strokeDasharray="2.5 2.5" />
    </svg>
  )
}

export default function CitationStrip({ citations }) {
  if (!citations || citations.length === 0) return null

  return (
    <Tooltip.Provider delayDuration={150}>
      <div className="flex gap-1.5 flex-wrap mt-2">
        {citations.map((c, i) => (
          <Tooltip.Root key={i}>
            <Tooltip.Trigger asChild>
              <span
                className="inline-flex items-center gap-1 px-1.5 py-[3px] text-[10px] font-medium rounded-[4px] cursor-default"
                style={{
                  color: c.verified ? 'var(--sage)' : 'var(--text-muted)',
                  background: c.verified ? 'var(--sage-light)' : 'var(--bg-soft)',
                  border: `1px solid ${c.verified ? 'var(--sage-border)' : 'var(--border-default)'}`,
                }}
              >
                <VerifiedMark verified={c.verified} />
                {c.source?.split('/').pop() || 'source'}{c.page != null ? ` · p.${c.page + 1}` : ''}
              </span>
            </Tooltip.Trigger>
            <Tooltip.Portal>
              <Tooltip.Content
                side="top"
                sideOffset={6}
                className="max-w-[280px] text-[11px] leading-snug px-3 py-2 rounded-[var(--radius-sm)] z-50"
                style={{
                  background: 'var(--text-primary)',
                  color: 'var(--bg-card)',
                  boxShadow: 'var(--shadow-panel)',
                }}
              >
                <span style={{ fontStyle: 'italic' }}>&ldquo;{c.quote}&rdquo;</span>
                <p className="m-0 mt-1 text-[10px] opacity-70">
                  {c.verified ? 'Matched to source text' : 'Not directly matched to source text — verify manually'}
                </p>
                <Tooltip.Arrow style={{ fill: 'var(--text-primary)' }} />
              </Tooltip.Content>
            </Tooltip.Portal>
          </Tooltip.Root>
        ))}
      </div>
    </Tooltip.Provider>
  )
}
