import { useEffect, useState } from 'react'
import { History } from 'lucide-react'
import { getRecentDrafts } from '../lib/api.js'

function formatTimestamp(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  const now = new Date()
  const sameDay = date.toDateString() === now.toDateString()
  if (sameDay) return date.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
  const sameYear = date.getFullYear() === now.getFullYear()
  return date.toLocaleDateString([], sameYear ? { month: 'short', day: 'numeric' } : { year: 'numeric', month: 'short', day: 'numeric' })
}

const STATUS_STYLE = {
  completed: { label: 'Completed', bg: 'var(--sage-light)', color: 'var(--sage)', border: 'var(--sage-border)' },
  running: { label: 'Drafting…', bg: 'var(--gold-light)', color: 'var(--gold)', border: 'var(--gold-border)' },
  pending: { label: 'Queued', bg: 'var(--bg-soft)', color: 'var(--text-muted)', border: 'var(--border-default)' },
  failed: { label: 'Failed', bg: 'var(--color-error-bg)', color: 'var(--color-error)', border: 'var(--color-error)' },
}

function statusStyle(status) {
  return STATUS_STYLE[status] || STATUS_STYLE.pending
}

export default function DraftHistorySidebar({ refreshKey }) {
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getRecentDrafts()
      .then(data => { if (!cancelled) setRuns(data) })
      .catch(() => { if (!cancelled) setError('Could not load recent drafts.') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [refreshKey])

  return (
    <aside
      className="flex flex-col overflow-hidden flex-shrink-0"
      style={{
        width: '272px',
        minWidth: 0,
        borderRight: '1px solid var(--border-default)',
        background: 'var(--bg-soft)',
        backdropFilter: 'blur(24px) saturate(160%)',
        WebkitBackdropFilter: 'blur(24px) saturate(160%)',
      }}
    >
      <div className="px-3.5 pt-3.5 pb-2.5 flex-shrink-0" style={{ background: 'var(--bg-soft)' }}>
        <div className="flex items-center gap-2">
          <History size={14} style={{ color: 'var(--ink)' }} />
          <span className="text-[10.5px] font-bold uppercase" style={{ color: 'var(--text-muted)', letterSpacing: '0.1em' }}>
            Recent drafts
          </span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-3 pt-1 flex flex-col gap-1">
        {loading && (
          <p className="m-0 px-2.5 py-3 text-[11.5px]" style={{ color: 'var(--text-muted)' }}>
            Loading…
          </p>
        )}

        {!loading && error && (
          <p className="m-0 px-2.5 py-3 text-[11.5px]" style={{ color: 'var(--color-error)' }}>
            {error}
          </p>
        )}

        {!loading && !error && runs.length === 0 && (
          <div className="flex flex-col items-center gap-2 px-4 py-10 text-center">
            <History size={22} style={{ color: 'var(--border-input)' }} />
            <p className="m-0 text-[11.5px] leading-relaxed" style={{ color: 'var(--text-muted)' }}>
              Documents you draft appear here.
            </p>
          </div>
        )}

        {!loading && !error && runs.map(run => {
          const tier = statusStyle(run.status)
          return (
            <div
              key={run.id}
              className="flex items-start gap-2.5 px-2.5 py-2.5 rounded-[2px]"
              style={{ border: '1px solid transparent' }}
            >
              <div className="flex-1 min-w-0">
                <p className="m-0 text-[12.5px] font-medium truncate" style={{ color: 'var(--text-secondary)' }}>
                  {run.title || 'Untitled draft'}
                </p>
                <div className="flex items-center gap-1.5 mt-1">
                  <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                    {run.document_type || 'Document'}
                  </span>
                  <span className="text-[10px] tabular-nums" style={{ color: 'var(--text-muted)' }}>
                    · {formatTimestamp(run.created_at)}
                  </span>
                </div>
              </div>
              <span
                className="text-[9.5px] font-bold px-1.5 py-[2px] rounded-[3px] uppercase whitespace-nowrap flex-shrink-0"
                style={{ background: tier.bg, color: tier.color, border: `1px solid ${tier.border}`, letterSpacing: '0.03em' }}
              >
                {tier.label}
              </span>
            </div>
          )
        })}
      </div>
    </aside>
  )
}
