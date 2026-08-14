import * as Tooltip from '@radix-ui/react-tooltip'
import { scrollToSource } from '../lib/sourceNav.js'

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

  const verifiedCount = citations.filter(c => c.verified).length

  return (
    <Tooltip.Provider delayDuration={150}>
      <div>
        {/* Eyebrow — names the strip as the evidence trail, echoing the
            SectionHeader idiom used in the retrieved-evidence panel. */}
        <div className="flex items-center gap-2 mb-2">
          <span
            className="text-[9.5px] font-bold uppercase whitespace-nowrap"
            style={{ color: 'var(--text-muted)', letterSpacing: '0.09em' }}
          >
            Cited sources
          </span>
          {verifiedCount > 0 && (
            <span
              className="inline-flex items-center gap-1 text-[9.5px] font-semibold tabular-nums"
              style={{ color: 'var(--sage)' }}
              title="Citations whose quote was matched back to the source text"
            >
              <VerifiedMark verified />
              {verifiedCount}/{citations.length} matched
            </span>
          )}
          <div className="flex-1 h-px" style={{ background: 'var(--border-default)' }} />
        </div>

        <div className="flex gap-1.5 flex-wrap">
        {citations.map((c, i) => (
          <Tooltip.Root key={i}>
            <Tooltip.Trigger asChild>
              <span
                role="button"
                tabIndex={0}
                onClick={() => scrollToSource(c.index ? c.index - 1 : i)}
                onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); scrollToSource(c.index ? c.index - 1 : i) } }}
                className="inline-flex items-center gap-1.5 pl-1.5 pr-2 py-[3.5px] text-[10.5px] font-medium rounded-[5px] cursor-pointer max-w-[220px]"
                style={{
                  color: c.verified ? 'var(--sage)' : 'var(--text-secondary)',
                  background: c.verified ? 'var(--sage-light)' : 'var(--bg-soft)',
                  border: `1px solid ${c.verified ? 'var(--sage-border)' : 'var(--border-default)'}`,
                }}
              >
                <VerifiedMark verified={c.verified} />
                <span className="truncate">{c.source?.split('/').pop() || 'source'}</span>
                {c.page != null && (
                  <span
                    className="tabular-nums flex-shrink-0"
                    style={{ fontFamily: "var(--font-mono)", opacity: 0.7 }}
                  >
                    p.{c.page + 1}
                  </span>
                )}
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
      </div>
    </Tooltip.Provider>
  )
}
