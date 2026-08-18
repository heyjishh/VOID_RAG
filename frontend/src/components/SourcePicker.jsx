import { useState, useEffect, useRef } from 'react'
import { Database, ChevronRight, ChevronDown } from 'lucide-react'
import { listDocuments, listDocumentFolders } from '../lib/api.js'

// Corpus source filter for the composer — mirrors whatever folder structure
// actually exists in the configured S3 bucket(s), derived live from object
// keys (see GET /documents/folders), not a hardcoded taxonomy. Whatever the
// user puts in the bucket shows up here without a code change.
export default function SourcePicker({ selected, onChange }) {
  const [open, setOpen] = useState(false)
  const [folders, setFolders] = useState(null) // null = not loaded yet
  const [loadingFolders, setLoadingFolders] = useState(false)
  const [expanded, setExpanded] = useState(() => new Set())
  const [folderFiles, setFolderFiles] = useState(() => new Map())
  const [loadingPrefix, setLoadingPrefix] = useState(null)
  const [query, setQuery] = useState('')
  const [allSources, setAllSources] = useState(null) // lazy full flat list, only for search
  const [loadingAll, setLoadingAll] = useState(false)
  const rootRef = useRef(null)

  useEffect(() => {
    function handleClickOutside(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false)
    }
    if (open) document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [open])

  // /documents caps a page at 500 — pull a second page when a prefix (or
  // the whole corpus) has more than that, instead of silently truncating.
  async function fetchAllFilenames(prefix) {
    const first = await listDocuments(prefix, 500, 0)
    let docs = first.documents || []
    if ((first.total || 0) > docs.length) {
      const rest = await listDocuments(prefix, 500, docs.length)
      docs = docs.concat(rest.documents || [])
    }
    return docs.map(d => d.filename)
  }

  async function ensureFolders() {
    if (folders !== null || loadingFolders) return
    setLoadingFolders(true)
    try {
      const res = await listDocumentFolders()
      setFolders(res.folders || [])
    } catch {
      setFolders([])
    } finally {
      setLoadingFolders(false)
    }
  }

  async function ensureAllSources() {
    if (allSources !== null || loadingAll) return
    setLoadingAll(true)
    try {
      setAllSources(await fetchAllFilenames(''))
    } catch {
      setAllSources([])
    } finally {
      setLoadingAll(false)
    }
  }

  async function loadFolderFiles(prefix) {
    if (folderFiles.has(prefix) || loadingPrefix === prefix) return folderFiles.get(prefix) || []
    setLoadingPrefix(prefix)
    try {
      const files = await fetchAllFilenames(prefix)
      setFolderFiles(prev => new Map(prev).set(prefix, files))
      return files
    } catch {
      return []
    } finally {
      setLoadingPrefix(null)
    }
  }

  function toggleOpen() {
    setOpen(v => {
      const next = !v
      if (next) ensureFolders()
      return next
    })
  }

  function toggleExpand(prefix) {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(prefix)) next.delete(prefix)
      else { next.add(prefix); loadFolderFiles(prefix) }
      return next
    })
  }

  function toggleFile(name) {
    onChange(selected.includes(name) ? selected.filter(s => s !== name) : [...selected, name])
  }

  async function toggleFolder(folder) {
    const files = folderFiles.get(folder.prefix) || await loadFolderFiles(folder.prefix)
    const allSelected = files.length > 0 && files.every(f => selected.includes(f))
    if (allSelected) {
      onChange(selected.filter(s => !files.includes(s)))
    } else {
      onChange([...new Set([...selected, ...files])])
    }
  }

  useEffect(() => {
    if (query.trim()) ensureAllSources()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query])

  const label = selected.length === 0 ? 'All sources' : `${selected.length} selected`
  const searching = query.trim().length > 0
  const searchMatches = searching ? (allSources || []).filter(s => s.toLowerCase().includes(query.toLowerCase())) : []

  return (
    <div className="relative flex-shrink-0" ref={rootRef}>
      <button
        type="button"
        onClick={toggleOpen}
        title="Choose which folders/documents the answer is grounded in"
        className="h-9 flex items-center gap-1.5 px-3 rounded-[var(--radius-sm)] text-[12px] font-medium transition-colors duration-150"
        style={{
          border: `1px solid ${selected.length ? 'var(--ink-border)' : 'var(--border-default)'}`,
          background: selected.length ? 'var(--ink-light)' : 'transparent',
          color: selected.length ? 'var(--ink)' : 'var(--text-secondary)',
          cursor: 'pointer',
          whiteSpace: 'nowrap',
        }}
      >
        <Database size={13} />
        Sources · {label}
      </button>

      {open && (
        <div
          className="absolute bottom-full mb-2 left-0 flex flex-col rounded-[var(--radius-md)] overflow-hidden z-20"
          style={{
            width: 'min(340px, calc(100vw - 32px))',
            maxHeight: 'min(400px, 70vh)',
            background: 'var(--bg-card)',
            border: '1px solid var(--border-default)',
            boxShadow: 'var(--shadow-panel)',
          }}
        >
          <div className="p-2.5" style={{ borderBottom: '1px solid var(--border-default)' }}>
            <input
              autoFocus
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search documents…"
              className="w-full text-[12.5px] px-2.5 py-1.5 rounded-[var(--radius-sm)] outline-none"
              style={{ border: '1px solid var(--border-input)', background: 'var(--bg-main)', color: 'var(--text-primary)' }}
            />
            {selected.length > 0 && (
              <div className="flex justify-end mt-1.5">
                <button
                  type="button"
                  onClick={() => onChange([])}
                  className="text-[10.5px] font-semibold"
                  style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}
                >
                  Clear ({selected.length})
                </button>
              </div>
            )}
          </div>

          <div className="flex-1 overflow-y-auto py-1">
            {searching ? (
              <>
                {loadingAll && (
                  <p className="text-[11.5px] px-3 py-4" style={{ color: 'var(--text-muted)' }}>Searching corpus…</p>
                )}
                {!loadingAll && searchMatches.length === 0 && (
                  <p className="text-[11.5px] px-3 py-4" style={{ color: 'var(--text-muted)' }}>No matching documents.</p>
                )}
                {!loadingAll && searchMatches.map(name => (
                  <FileRow key={name} name={name} checked={selected.includes(name)} onToggle={() => toggleFile(name)} />
                ))}
              </>
            ) : (
              <>
                {loadingFolders && (
                  <p className="text-[11.5px] px-3 py-4" style={{ color: 'var(--text-muted)' }}>Loading bucket…</p>
                )}
                {!loadingFolders && (folders || []).length === 0 && (
                  <p className="text-[11.5px] px-3 py-4" style={{ color: 'var(--text-muted)' }}>No documents ingested yet.</p>
                )}
                {!loadingFolders && (folders || []).map(f => (
                  <FolderRow
                    key={`${f.bucket}::${f.prefix}`}
                    folder={f}
                    multiBucket={new Set((folders || []).map(x => x.bucket)).size > 1}
                    isExpanded={expanded.has(f.prefix)}
                    isLoading={loadingPrefix === f.prefix}
                    files={folderFiles.get(f.prefix) || null}
                    selected={selected}
                    onToggleExpand={() => toggleExpand(f.prefix)}
                    onToggleFolder={() => toggleFolder(f)}
                    onToggleFile={toggleFile}
                  />
                ))}
              </>
            )}
          </div>

          <div className="p-2 flex justify-end" style={{ borderTop: '1px solid var(--border-default)' }}>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="text-[11.5px] font-semibold px-3 py-1.5 rounded-[6px]"
              style={{ background: 'var(--primary)', color: 'var(--on-primary)', border: 'none', cursor: 'pointer' }}
            >
              Done
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function FolderRow({ folder, multiBucket, isExpanded, isLoading, files, selected, onToggleExpand, onToggleFolder, onToggleFile }) {
  const allSelected = files !== null && files.length > 0 && files.every(f => selected.includes(f))
  const someSelected = files !== null && !allSelected && files.some(f => selected.includes(f))
  const displayName = folder.folder || '(bucket root)'

  return (
    <div>
      <div
        className="flex items-center gap-1.5 px-2 py-1.5 cursor-pointer"
        onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-soft)' }}
        onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
      >
        <button
          type="button"
          onClick={onToggleExpand}
          className="flex items-center justify-center w-5 h-5 flex-shrink-0"
          style={{ background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}
        >
          {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        </button>
        <input
          type="checkbox"
          checked={allSelected}
          ref={el => { if (el) el.indeterminate = someSelected }}
          onChange={onToggleFolder}
          style={{ accentColor: 'var(--ink)', flexShrink: 0 }}
        />
        <span
          className="flex-1 truncate text-[12px] font-medium"
          style={{ color: 'var(--text-primary)' }}
          onClick={onToggleExpand}
        >
          {multiBucket ? `${folder.bucket} / ${displayName}` : displayName}
        </span>
        <span className="text-[10.5px] flex-shrink-0" style={{ color: 'var(--text-muted)' }}>{folder.count}</span>
      </div>
      {isExpanded && (
        <div className="pl-7">
          {isLoading && (
            <p className="text-[11px] px-2 py-1.5" style={{ color: 'var(--text-muted)' }}>Loading…</p>
          )}
          {!isLoading && files && files.map(name => (
            <FileRow key={name} name={name} checked={selected.includes(name)} onToggle={() => onToggleFile(name)} />
          ))}
        </div>
      )}
    </div>
  )
}

function FileRow({ name, checked, onToggle }) {
  return (
    <label
      className="flex items-center gap-2 px-3 py-1.5 cursor-pointer"
      style={{ fontSize: '11.5px', color: 'var(--text-primary)' }}
      onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-soft)' }}
      onMouseLeave={e => { e.currentTarget.style.background = 'transparent' }}
    >
      <input
        type="checkbox"
        checked={checked}
        onChange={onToggle}
        style={{ accentColor: 'var(--ink)', flexShrink: 0 }}
      />
      <span className="truncate">{name}</span>
    </label>
  )
}
