import { ChevronRight, Search, PanelLeft, PanelRight, Globe, CheckCircle2 } from 'lucide-react'

export default function TopHeader({
  matterLabel,
  activeTitle,
  onToggleMatters,
  mattersCollapsed,
  onToggleEvidence,
  evidenceCollapsed,
  evidenceCount,
  useWebSearch,
  onToggleWebSearch,
  user,
}) {
  return (
    <header
      className="flex items-center gap-3 px-4 flex-shrink-0"
      style={{
        height: 52,
        background: 'var(--bg-card)',
        backdropFilter: 'blur(24px) saturate(160%)',
        WebkitBackdropFilter: 'blur(24px) saturate(160%)',
        borderBottom: "1px solid var(--border-default)",
      }}
    >
      {/* Matters toggle */}
      <button
        type="button"
        onClick={onToggleMatters}
        title={mattersCollapsed ? 'Show matters' : 'Hide matters'}
        className="w-8 h-8 rounded-[2px] flex items-center justify-center transition-colors duration-150"
        style={{
          background: mattersCollapsed ? 'transparent' : 'var(--ink-light)',
          color: mattersCollapsed ? 'var(--text-secondary)' : 'var(--ink)',
          border: 'none',
          cursor: 'pointer',
        }}
        onMouseEnter={e => { if (mattersCollapsed) { e.currentTarget.style.background = 'var(--bg-soft)' } }}
        onMouseLeave={e => { if (mattersCollapsed) { e.currentTarget.style.background = 'transparent' } }}
      >
        <PanelLeft size={16} />
      </button>

      {/* Breadcrumb */}
      <div className="flex items-center gap-1.5 min-w-0">
        <span className="text-[12.5px] font-medium whitespace-nowrap" style={{ color: 'var(--text-muted)' }}>
          Workspace
        </span>
        <ChevronRight size={13} style={{ color: 'var(--border-input)' }} />
        <span className="text-[12.5px] font-semibold whitespace-nowrap" style={{ color: 'var(--text-primary)' }}>
          {matterLabel}
        </span>
        {activeTitle && (
          <>
            <ChevronRight size={13} style={{ color: 'var(--border-input)' }} />
            <span className="text-[12.5px] font-medium truncate" style={{ color: 'var(--text-secondary)' }}>
              {activeTitle}
            </span>
          </>
        )}
      </div>

      {/* Global search */}
      <div className="ml-4 flex-1 max-w-[340px]">
        <div
          className="flex items-center gap-2 px-3 h-8 rounded-[2px]"
          style={{ background: 'var(--bg-soft)', border: '1px solid var(--border-default)', color: 'var(--text-muted)' }}
        >
          <Search size={13} />
          <span className="text-[12px]">Search matters, sources, judgments…</span>
          <span
            className="ml-auto text-[10px] px-1.5 py-px rounded-[2px]"
            style={{ background: 'var(--bg-card)', border: '1px solid var(--border-default)', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}
          >
            ⌘K
          </span>
        </div>
      </div>

      <div className="flex-1" />

      {/* Web search toggle */}
      <button
        type="button"
        onClick={onToggleWebSearch}
        className="flex items-center gap-1.5 h-8 px-2.5 rounded-[2px] text-[11.5px] font-medium transition-colors duration-150"
        style={{
          background: useWebSearch ? 'var(--ink-light)' : 'transparent',
          color: useWebSearch ? 'var(--ink)' : 'var(--text-muted)',
          border: '1px solid transparent',
          cursor: 'pointer',
        }}
        onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--border-default)' }}
        onMouseLeave={e => { e.currentTarget.style.borderColor = 'transparent' }}
      >
        <Globe size={14} />
        {useWebSearch ? 'Web search on' : 'Web search'}
      </button>

      {/* Corpus status */}
      <div className="flex items-center gap-1.5 h-8 px-2.5 rounded-[2px]" style={{ background: 'var(--sage-light)', border: '1px solid var(--sage-border)' }}>
        <CheckCircle2 size={13} style={{ color: 'var(--sage)' }} />
        <span className="text-[11.5px] font-medium" style={{ color: 'var(--sage)' }}>Corpus connected</span>
      </div>

      {/* Evidence toggle */}
      <button
        type="button"
        onClick={onToggleEvidence}
        title={evidenceCollapsed ? 'Show evidence' : 'Hide evidence'}
        className="relative w-8 h-8 rounded-[2px] flex items-center justify-center transition-colors duration-150"
        style={{
          background: evidenceCollapsed ? 'transparent' : 'var(--ink-light)',
          color: evidenceCollapsed ? 'var(--text-secondary)' : 'var(--ink)',
          border: 'none',
          cursor: 'pointer',
        }}
        onMouseEnter={e => { if (evidenceCollapsed) { e.currentTarget.style.background = 'var(--bg-soft)' } }}
        onMouseLeave={e => { if (evidenceCollapsed) { e.currentTarget.style.background = 'transparent' } }}
      >
        <PanelRight size={16} />
        {evidenceCount > 0 && (
          <span
            className="absolute mt-[-14px] ml-[14px] min-w-[15px] h-[15px] px-1 rounded-full text-[9px] font-bold flex items-center justify-center"
            style={{ background: 'var(--primary)', color: 'var(--on-primary)', fontFamily: 'var(--font-mono)' }}
          >
            {evidenceCount}
          </span>
        )}
      </button>
    </header>
  )
}