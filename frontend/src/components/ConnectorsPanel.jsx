import { CONNECTORS } from '../lib/connectors.js'

function ConnectorIcon({ kind }) {
  if (kind === 'web') {
    return (
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--color-info)" strokeWidth="2">
        <circle cx="12" cy="12" r="10" />
        <line x1="2" y1="12" x2="22" y2="12" />
        <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
      </svg>
    )
  }
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="var(--sage)" strokeWidth="2">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14,2 14,8 20,8" />
    </svg>
  )
}

export default function ConnectorsPanel({ useWebSearch, onToggleWebSearch }) {
  return (
    <div className="flex flex-col gap-2">
      {CONNECTORS.map(connector => {
        const isWeb = connector.kind === 'web'
        const connected = connector.alwaysOn || (isWeb && useWebSearch)
        return (
          <div
            key={connector.id}
            className="flex items-center gap-2.5 p-2.5 rounded-[var(--radius-sm)]"
            style={{ background: 'var(--bg-soft)', border: '1px solid var(--border-default)' }}
          >
            <div
              className="w-7 h-7 rounded-[6px] flex items-center justify-center flex-shrink-0"
              style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)' }}
            >
              <ConnectorIcon kind={connector.kind} />
            </div>
            <div className="flex-1 min-w-0">
              <p className="m-0 text-[12.5px] font-semibold" style={{ color: 'var(--text-primary)' }}>
                {connector.name}
              </p>
              <p className="m-0 mt-0.5 text-[10.5px] leading-snug" style={{ color: 'var(--text-muted)' }}>
                {connector.description}
              </p>
            </div>

            {connector.alwaysOn ? (
              <span
                className="text-[9.5px] font-bold uppercase px-1.5 py-0.5 rounded-[3px] flex-shrink-0"
                style={{ color: 'var(--sage)', background: 'var(--sage-light)', border: '1px solid var(--sage-border)', letterSpacing: '0.04em' }}
              >
                Always on
              </span>
            ) : (
              <label className="flex items-center cursor-pointer flex-shrink-0">
                <input type="checkbox" className="sr-only" checked={Boolean(useWebSearch)} onChange={onToggleWebSearch} />
                <div
                  className="w-8 h-[18px] rounded-full transition-colors duration-200"
                  style={{ background: connected ? 'var(--ink)' : 'var(--border-input)' }}
                >
                  <div
                    className="w-[14px] h-[14px] rounded-full bg-white shadow-sm transition-transform duration-200"
                    style={{ margin: '2px', transform: connected ? 'translateX(14px)' : 'translateX(0)' }}
                  />
                </div>
              </label>
            )}
          </div>
        )
      })}
    </div>
  )
}
