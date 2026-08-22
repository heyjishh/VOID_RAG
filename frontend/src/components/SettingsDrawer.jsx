import { useState, useEffect, useRef } from 'react'
import gsap from 'gsap'
import { triggerIngest, getSyncStatus, getLlmStatus, getAvailableModels, setJurisVoidModel } from '../lib/api.js'
import { PROMPT_LIBRARY } from '../lib/promptLibrary.js'
import { prefersReducedMotion } from '../lib/motion.js'
import ThemeToggle from './ThemeToggle.jsx'
import ConnectorsPanel from './ConnectorsPanel.jsx'

export default function SettingsDrawer({ onClose, useWebSearch, onToggleWebSearch, user, onLogout }) {
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState(false)
  const [syncInfo, setSyncInfo] = useState(null)
  const [llmStatus, setLlmStatus] = useState(null)
  const [modelInfo, setModelInfo] = useState(null)
  const [jvSaving, setJvSaving] = useState(false)
  const drawerRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    getLlmStatus().then(info => { if (!cancelled) setLlmStatus(info) }).catch(() => {})
    getAvailableModels().then(info => { if (!cancelled) setModelInfo(info) }).catch(() => {})
    return () => { cancelled = true }
  }, [])

  // Fixed 10s cadence regardless of run state — the backend caches the
  // expensive S3-listing part of /ingest/status, so polling on a flat
  // interval no longer hammers S3 the way a sub-second "while running"
  // interval used to (that was the actual cause of ingestion failures).
  useEffect(() => {
    let cancelled = false

    async function refresh() {
      try {
        const info = await getSyncStatus()
        if (cancelled) return
        setSyncInfo(info)
        setBusy(Boolean(info.running))
      } catch { /* backend not reachable — keep last state */ }
    }

    refresh()
    const interval = setInterval(refresh, 10000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [])

  // Slide in from right
  useEffect(() => {
    if (prefersReducedMotion()) return
    gsap.fromTo(
      drawerRef.current,
      { x: 60, opacity: 0 },
      { x: 0, opacity: 1, duration: 0.28, ease: 'power3.out' }
    )
  }, [])

  function handleClose() {
    if (prefersReducedMotion()) { onClose(); return }
    gsap.to(drawerRef.current, {
      x: 60, opacity: 0, duration: 0.2, ease: 'power2.in',
      onComplete: onClose,
    })
  }

  async function ingest() {
    setBusy(true); setStatus(null)
    try {
      await triggerIngest('', true)
      setStatus({ ok: true, msg: 'Sync started in background — progress below.' })
    } catch (e) {
      setStatus({ ok: false, msg: 'Error: ' + e.message })
      setBusy(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-[100] flex justify-end"
      style={{ background: 'var(--overlay-scrim)' }}
      onClick={handleClose}
    >
      <div
        ref={drawerRef}
        className="flex flex-col gap-6 overflow-y-auto"
        style={{
          width: 'min(380px, 100vw)',
          height: '100%',
          background: 'var(--bg-card)',
          backdropFilter: 'blur(28px) saturate(180%)',
          WebkitBackdropFilter: 'blur(28px) saturate(180%)',
          borderLeft: '1px solid var(--border-default)',
          boxShadow: 'var(--shadow-panel)',
          padding: '24px',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex justify-between items-center">
          <h2
            className="font-display m-0"
            style={{ fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)' }}
          >
            Settings
          </h2>
          <button
            onClick={handleClose}
            className="flex items-center justify-center w-7 h-7 rounded-[5px] transition-colors"
            style={{
              border: '1px solid var(--border-default)',
              background: 'transparent',
              color: 'var(--text-muted)',
              cursor: 'pointer',
              fontSize: '14px',
            }}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--ink-light)'; e.currentTarget.style.color = 'var(--ink)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.color = 'var(--text-muted)' }}
          >
            ✕
          </button>
        </div>

        <div style={{ width: '100%', height: '1px', background: 'var(--border-default)' }} />

        {/* Account */}
        {user && (
          <section>
            <SectionTitle>Account</SectionTitle>
            <div
              className="flex items-center gap-3 rounded-[var(--radius-sm)] p-3"
              style={{ background: 'var(--bg-soft)', border: '1px solid var(--border-default)' }}
            >
              <span
                className="w-9 h-9 rounded-full flex items-center justify-center text-[12px] font-bold flex-shrink-0"
                style={{ background: 'var(--ink)', color: 'var(--on-ink)' }}
              >
                {(user.name || user.email || 'R').split(/\s+/).map(w => w[0]).join('').slice(0, 2).toUpperCase()}
              </span>
              <div className="flex-1 min-w-0">
                <p className="m-0 text-[12.5px] font-semibold truncate" style={{ color: 'var(--text-primary)' }}>{user.name}</p>
                <p className="m-0 mt-0.5 text-[11px] truncate" style={{ color: 'var(--text-muted)' }}>{user.email}</p>
              </div>
              <button
                onClick={onLogout}
                className="text-[11.5px] font-semibold px-2.5 py-1.5 rounded-[6px] transition-colors"
                style={{ border: '1px solid var(--color-error-border)', background: 'transparent', color: 'var(--color-error)', cursor: 'pointer' }}
                onMouseEnter={e => { e.currentTarget.style.background = 'var(--color-error-bg)' }}
                onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
              >
                Sign out
              </button>
            </div>
          </section>
        )}

        {/* Preferences */}
        <section>
          <SectionTitle>Appearance</SectionTitle>
          <ThemeToggle />
        </section>

        {/* Connectors */}
        <section>
          <SectionTitle>Connectors</SectionTitle>
          <ConnectorsPanel useWebSearch={useWebSearch} onToggleWebSearch={onToggleWebSearch} />
        </section>

        {/* Skills — read-only view of the same registry the composer's Prompt Library draws from */}
        <section>
          <SectionTitle>Skills</SectionTitle>
          <div className="flex flex-col gap-1.5">
            {PROMPT_LIBRARY.map(item => (
              <div
                key={item.id}
                className="flex items-center gap-2 px-2.5 py-2 rounded-[var(--radius-sm)]"
                style={{ background: 'var(--bg-soft)', border: '1px solid var(--border-default)' }}
              >
                <span
                  className="text-[9.5px] font-bold uppercase px-1.5 py-0.5 rounded-[3px] flex-shrink-0"
                  style={{ color: 'var(--ink)', background: 'var(--ink-light)', letterSpacing: '0.04em' }}
                >
                  {item.skill}
                </span>
                <span className="text-[11.5px] truncate" style={{ color: 'var(--text-secondary)' }}>
                  {item.label}
                </span>
              </div>
            ))}
          </div>
        </section>

        {/* Sync Status */}
        {syncInfo && (
          <section>
            <SectionTitle>Corpus Sync Status</SectionTitle>
            <div className="rounded-[var(--radius-sm)] p-3 text-[12px]" style={{ background: 'var(--bg-soft)', border: '1px solid var(--border-default)', lineHeight: 2 }}>
              <SyncRow label="Total documents" value={syncInfo.total_on_s3} />
              <SyncRow label="Ingested" value={syncInfo.ingested} valueColor="var(--sage)" />
              <SyncRow
                label="Pending"
                value={syncInfo.pending ?? '—'}
                valueColor={syncInfo.pending > 0 ? 'var(--accent-yellow)' : 'var(--text-muted)'}
              />
            </div>
          </section>
        )}

        {/* Live Sync Progress */}
        {syncInfo?.running && (
          <section>
            <SectionTitle>Sync Progress</SectionTitle>
            <div className="rounded-[var(--radius-sm)] p-3" style={{ background: 'var(--bg-soft)', border: '1px solid var(--border-default)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', marginBottom: '8px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>
                  {syncInfo.processed} / {syncInfo.total} processed
                </span>
                <span style={{ color: 'var(--ink)', fontWeight: 700, fontFamily: "var(--font-mono)" }}>
                  {syncInfo.total ? Math.round((syncInfo.processed / syncInfo.total) * 100) : 0}%
                </span>
              </div>
              <div style={{ height: '6px', borderRadius: '3px', background: 'var(--border-default)', overflow: 'hidden' }}>
                <div style={{
                  height: '100%',
                  width: `${syncInfo.total ? Math.min(100, (syncInfo.processed / syncInfo.total) * 100) : 0}%`,
                  background: 'var(--ink)',
                  borderRadius: '3px',
                  transition: 'width 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
                }} />
              </div>
              {syncInfo.current_key && (
                <p style={{
                  margin: '8px 0 0',
                  fontSize: '11px',
                  color: 'var(--text-muted)',
                  fontFamily: "var(--font-mono)",
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}>
                  {syncInfo.current_key.split('/').pop()}
                </p>
              )}
              <p style={{ margin: '6px 0 0', fontSize: '11px', color: 'var(--text-secondary)' }}>
                ✓ {syncInfo.ingested} ingested · ⚠ {syncInfo.failed} failed · – {syncInfo.skipped} skipped
              </p>
              <p style={{ margin: '4px 0 0', fontSize: '11px', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                {syncInfo.concurrency ?? '—'} workers · {syncInfo.cpu_percent != null ? `${Math.round(syncInfo.cpu_percent)}% cpu` : '—'}
              </p>
            </div>
          </section>
        )}

        {/* Last Sync — persists across app restarts/reopens, so if the user
            closed the tab (or the server bounced) mid-run or after one
            finished, reopening Settings still shows what happened last. */}
        {!syncInfo?.running && syncInfo?.last_sync && (
          <section>
            <SectionTitle>Last Sync</SectionTitle>
            <div className="rounded-[var(--radius-sm)] p-3" style={{ background: 'var(--bg-soft)', border: '1px solid var(--border-default)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px' }}>
                <span style={{ color: 'var(--text-secondary)' }}>
                  {syncInfo.last_sync.error ? 'Stopped with an error' : 'Finished'}
                </span>
                <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: '11px' }}>
                  {syncInfo.last_sync.finished_at ? new Date(syncInfo.last_sync.finished_at * 1000).toLocaleString() : '—'}
                </span>
              </div>
              <p style={{ margin: '6px 0 0', fontSize: '11px', color: 'var(--text-secondary)' }}>
                ✓ {syncInfo.last_sync.ingested} ingested · ⚠ {syncInfo.last_sync.failed} failed · – {syncInfo.last_sync.skipped} skipped
                {syncInfo.last_sync.total ? ` (of ${syncInfo.last_sync.total})` : ''}
              </p>
              {syncInfo.last_sync.error && (
                <p style={{ margin: '6px 0 0', fontSize: '11px', color: 'var(--color-error)' }}>
                  {syncInfo.last_sync.error}
                </p>
              )}
            </div>
          </section>
        )}

        {/* Sync Data */}
        <section>
          <SectionTitle>Sync Data</SectionTitle>
          <ActionButton
            onClick={ingest}
            disabled={busy}
            primary
          >
            {busy ? 'Syncing…' : '⟳ Sync Data'}
          </ActionButton>
          {status && (
            <p style={{
              margin: '10px 0 0',
              fontSize: '12px',
              color: status.ok ? 'var(--sage)' : 'var(--color-error)',
              background: status.ok ? 'var(--sage-light)' : 'var(--color-error-bg)',
              border: `1px solid ${status.ok ? 'var(--sage-border)' : 'var(--color-error-border)'}`,
              borderRadius: 'var(--radius-sm)',
              padding: '8px 12px',
              fontStyle: 'italic',
            }}>
              {status.msg}
            </p>
          )}
        </section>

        {/* LLM Provider — live, not a static description: reflects whichever
            provider settings.llm_provider_chain actually resolves to first. */}
        <section>
          <SectionTitle>LLM Provider</SectionTitle>
          <div style={{
            background: 'var(--bg-soft)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-sm)',
            padding: '12px',
            fontSize: '12px',
            color: 'var(--text-secondary)',
            lineHeight: 1.8,
          }}>
            {!llmStatus ? (
              <p style={{ margin: 0, color: 'var(--text-muted)' }}>Checking connection…</p>
            ) : !llmStatus.configured ? (
              <p style={{ margin: 0, color: 'var(--color-error)' }}>No provider configured — set an API key or GATEWAY_KEY.</p>
            ) : (
              <>
                <div className="flex items-center gap-2" style={{ margin: '0 0 6px' }}>
                  <span
                    className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                    style={{ background: 'var(--sage)' }}
                  />
                  <p style={{ margin: 0, color: 'var(--text-primary)', fontWeight: 500, textTransform: 'capitalize' }}>
                    {llmStatus.provider} · connected
                  </p>
                </div>
                <p style={{ margin: 0, color: 'var(--text-muted)', fontFamily: "var(--font-mono)", fontSize: '11px', wordBreak: 'break-all' }}>
                  model={llmStatus.model}
                  {llmStatus.base_url && <><br />{llmStatus.base_url}</>}
                </p>
              </>
            )}
          </div>
        </section>

        {/* Model Selection */}
        {modelInfo && modelInfo.providers?.length > 0 && (
          <section>
            <SectionTitle>Model Selection</SectionTitle>
            <div className="flex flex-col gap-3">
              <div>
                <label
                  className="block text-[11px] font-semibold uppercase mb-1.5"
                  style={{ color: 'var(--text-muted)', letterSpacing: '0.04em' }}
                >
                  Global LLM
                </label>
                <div
                  className="flex items-center gap-2 px-3 py-2.5 rounded-[var(--radius-sm)]"
                  style={{ background: 'var(--bg-soft)', border: '1px solid var(--border-default)' }}
                >
                  <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: 'var(--sage)' }} />
                  <span className="text-[12px] font-medium" style={{ color: 'var(--text-primary)', textTransform: 'capitalize' }}>
                    {modelInfo.global?.id || 'none'}
                  </span>
                  <span className="text-[11px]" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                    {modelInfo.global?.model || ''}
                  </span>
                </div>
                <p className="m-0 mt-1 text-[10px]" style={{ color: 'var(--text-muted)' }}>
                  Set via env var priority — first available key wins
                </p>
              </div>
              <div>
                <label
                  className="block text-[11px] font-semibold uppercase mb-1.5"
                  style={{ color: 'var(--text-muted)', letterSpacing: '0.04em' }}
                >
                  Juris-VOID LLM
                </label>
                <select
                  value={modelInfo.juris_void?.id || ''}
                  onChange={async e => {
                    const pid = e.target.value
                    const prov = modelInfo.providers.find(p => p.id === pid)
                    setJvSaving(true)
                    try {
                      const res = await setJurisVoidModel(pid, prov?.model || null)
                      setModelInfo(prev => ({
                        ...prev,
                        juris_void: { id: res.provider, model: res.model },
                      }))
                    } catch {}
                    setJvSaving(false)
                  }}
                  disabled={jvSaving}
                  className="w-full text-[12px] px-3 py-2.5 rounded-[var(--radius-sm)]"
                  style={{
                    background: 'var(--bg-soft)',
                    border: '1px solid var(--border-default)',
                    color: 'var(--text-primary)',
                    fontFamily: 'var(--font-sans)',
                    cursor: 'pointer',
                    outline: 'none',
                    appearance: 'none',
                    WebkitAppearance: 'none',
                    backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%23888' stroke-width='2'%3E%3Cpath d='M6 9l6 6 6-6'/%3E%3C/svg%3E")`,
                    backgroundRepeat: 'no-repeat',
                    backgroundPosition: 'right 10px center',
                    paddingRight: '28px',
                  }}
                >
                  {modelInfo.providers.map(p => (
                    <option key={p.id} value={p.id}>{p.label}</option>
                  ))}
                </select>
                {modelInfo.juris_void?.model && (
                  <p className="m-0 mt-1 text-[10px]" style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                    model={modelInfo.juris_void.model}
                  </p>
                )}
              </div>
            </div>
          </section>
        )}

        {/* Web Search */}
        <section>
          <SectionTitle>Web Search</SectionTitle>
          <div style={{
            background: 'var(--bg-soft)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-sm)',
            padding: '12px',
            fontSize: '12px',
            color: 'var(--text-secondary)',
            lineHeight: 1.8,
          }}>
            {llmStatus?.web_search_provider ? (
              <div className="flex items-center gap-2">
                <span
                  className="w-1.5 h-1.5 rounded-full flex-shrink-0"
                  style={{ background: 'var(--sage)' }}
                />
                <p style={{ margin: 0, color: 'var(--text-primary)', fontWeight: 500, textTransform: 'capitalize' }}>
                  {llmStatus.web_search_provider}
                </p>
                <span style={{ color: 'var(--text-muted)', fontSize: '11px' }}>active</span>
              </div>
            ) : (
              <p style={{ margin: 0, color: 'var(--text-muted)' }}>Checking…</p>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}

function SectionTitle({ children }) {
  return (
    <h3
      className="uppercase tracking-widest"
      style={{
        margin: '0 0 10px',
        fontSize: '10px',
        fontWeight: 700,
        color: 'var(--text-muted)',
        letterSpacing: '0.08em',
      }}
    >
      {children}
    </h3>
  )
}

function SyncRow({ label, value, valueColor }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
      <span style={{ color: 'var(--text-secondary)' }}>{label}</span>
      <span style={{ fontWeight: 600, color: valueColor || 'var(--text-primary)', fontFamily: "var(--font-mono)" }}>
        {value ?? '—'}
      </span>
    </div>
  )
}

function ActionButton({ children, onClick, disabled, primary = false }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        flex: 1,
        padding: '9px',
        background: disabled
          ? 'var(--border-default)'
          : primary ? 'var(--primary)' : 'var(--bg-soft)',
        color: disabled
          ? 'var(--text-muted)'
          : primary ? 'var(--on-primary)' : 'var(--text-primary)',
        border: primary ? 'none' : `1px solid var(--border-default)`,
        borderRadius: 'var(--radius-sm)',
        fontSize: '13px',
        fontWeight: 600,
        cursor: disabled ? 'not-allowed' : 'pointer',
        transition: 'all 0.15s',
        fontFamily: "var(--font-sans)",
        boxShadow: primary && !disabled ? 'var(--shadow-primary-sm)' : 'none',
      }}
    >
      {children}
    </button>
  )
}
