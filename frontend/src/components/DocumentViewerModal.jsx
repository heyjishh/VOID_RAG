import { useState, useRef, useEffect, useCallback } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/TextLayer.css'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import gsap from 'gsap'
import { API_BASE } from '../lib/api.js'
import { prefersReducedMotion } from '../lib/motion.js'

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  'pdfjs-dist/build/pdf.worker.min.mjs',
  import.meta.url,
).toString()

const ANCHOR_LENGTH = 120
const PAGE_WIDTH = 640
const FETCH_TIMEOUT_MS = 60000
const SLOW_FETCH_DELAY_MS = 7000

// Dedupes concurrent fetches for the same document. Without this, React
// StrictMode's dev-mode mount->cleanup->mount cycle fires two near-simultaneous
// requests to the same URL; Chrome's connection layer can coalesce them, so
// aborting the first (phantom) mount's controller collaterally aborts the
// second (surviving) mount's request too, leaving the viewer stuck loading.
const inflightDocumentFetches = new Map()

function fetchDocumentBlob(source) {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS)
  const promise = fetch(
    `${API_BASE}/documents/view?source=${encodeURIComponent(source)}`,
    { signal: controller.signal }
  )
    .then(res => {
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return res.blob()
    })
    .finally(() => {
      clearTimeout(timeoutId)
      inflightDocumentFetches.delete(source)
    })
  inflightDocumentFetches.set(source, promise)
  return promise
}

// Collapses whitespace runs to a single space and lowercases, while keeping
// a map back to the original string's indices — needed because the match
// index has to be projected back onto the un-collapsed span offsets below.
function collapseWs(str) {
  let out = ''
  const map = []
  let inWs = false
  for (let i = 0; i < str.length; i++) {
    const ch = str[i]
    if (/\s/.test(ch)) {
      if (!inWs) { out += ' '; map.push(i) }
      inWs = true
    } else {
      out += ch.toLowerCase()
      map.push(i)
      inWs = false
    }
  }
  return { normalized: out, map }
}

// pdf.js's text layer renders one span per extracted text run — concatenate
// them (with a joining space so run boundaries don't glue words together)
// while recording each span's [start, end) range in the joined string, so a
// match found in the joined string can be traced back to the spans it covers.
function buildTextMap(spans) {
  let full = ''
  const spanRanges = []
  spans.forEach((el) => {
    const spanText = el.textContent || ''
    const start = full.length
    full += spanText
    spanRanges.push({ el, start, end: full.length })
    full += ' '
  })
  return { full, spanRanges }
}

function MutedNote({ children }) {
  return (
    <p
      className="m-0 text-[11.5px] text-center leading-relaxed font-display"
      style={{ color: 'var(--text-muted)' }}
    >
      {children}
    </p>
  )
}

function NavButton({ children, onClick, disabled }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className="text-[12px] font-semibold px-3 py-1.5 rounded-[var(--radius-sm)] transition-colors"
      style={{
        background: disabled ? 'var(--bg-soft)' : 'var(--ink-light)',
        color: disabled ? 'var(--text-muted)' : 'var(--ink)',
        border: `1px solid ${disabled ? 'var(--border-default)' : 'var(--ink-border)'}`,
        cursor: disabled ? 'not-allowed' : 'pointer',
        fontFamily: "var(--font-sans)",
      }}
    >
      {children}
    </button>
  )
}

export default function DocumentViewerModal({ source, page, text, onClose }) {
  const [fileUrl, setFileUrl] = useState(null)
  const [loadError, setLoadError] = useState(null)
  const [timedOut, setTimedOut] = useState(false)
  const [slowFetch, setSlowFetch] = useState(false)
  const [retryKey, setRetryKey] = useState(0)
  const [numPages, setNumPages] = useState(null)
  const [pageNumber, setPageNumber] = useState((page ?? 0) + 1)
  const [notFound, setNotFound] = useState(false)
  const modalRef = useRef(null)
  const pageWrapRef = useRef(null)

  useEffect(() => {
    let objectUrl
    let cancelled = false

    setFileUrl(null)
    setLoadError(null)
    setTimedOut(false)
    setSlowFetch(false)

    const slowFetchId = setTimeout(() => {
      if (!cancelled) setSlowFetch(true)
    }, SLOW_FETCH_DELAY_MS)

    const promise = inflightDocumentFetches.get(source) ?? fetchDocumentBlob(source)

    promise.then(blob => {
      if (cancelled) return
      objectUrl = URL.createObjectURL(blob)
      setFileUrl(objectUrl)
    }).catch(e => {
      if (cancelled) return
      if (e.name === 'AbortError') setTimedOut(true)
      else setLoadError(e.message)
    })

    return () => {
      cancelled = true
      clearTimeout(slowFetchId)
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [source, retryKey])

  const handleRetry = useCallback(() => {
    inflightDocumentFetches.delete(source)
    setRetryKey(k => k + 1)
  }, [source])

  const handleClose = useCallback(() => {
    if (!modalRef.current || prefersReducedMotion()) { onClose(); return }
    gsap.to(modalRef.current, {
      opacity: 0, y: 10, scale: 0.98, duration: 0.16, ease: 'power2.in',
      onComplete: onClose,
    })
  }, [onClose])

  useEffect(() => {
    function handleKey(e) {
      if (e.key === 'Escape') handleClose()
      else if (e.key === 'ArrowRight') setPageNumber(p => (numPages ? Math.min(numPages, p + 1) : p + 1))
      else if (e.key === 'ArrowLeft') setPageNumber(p => Math.max(1, p - 1))
    }
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [handleClose, numPages])

  useEffect(() => {
    if (!modalRef.current || prefersReducedMotion()) return
    gsap.fromTo(
      modalRef.current,
      { opacity: 0, y: 12, scale: 0.98 },
      { opacity: 1, y: 0, scale: 1, duration: 0.22, ease: 'power2.out' }
    )
  }, [])

  const highlightAnchor = (text || '').slice(0, ANCHOR_LENGTH)

  const handleTextLayerRendered = useCallback(() => {
    setNotFound(false)
    if (!pageWrapRef.current || !highlightAnchor.trim()) return

    const spans = Array.from(
      pageWrapRef.current.querySelectorAll('.react-pdf__Page__textContent [role="presentation"]')
    )
    if (spans.length === 0) return

    const { full, spanRanges } = buildTextMap(spans)
    const { normalized: fullNorm, map } = collapseWs(full)
    const anchorNorm = collapseWs(highlightAnchor).normalized.trim()
    if (!anchorNorm) return

    const idx = fullNorm.indexOf(anchorNorm)
    if (idx === -1) { setNotFound(true); return }

    const origStart = map[idx]
    const origEnd = map[Math.min(idx + anchorNorm.length - 1, map.length - 1)] + 1
    const matched = spanRanges.filter(r => r.end > origStart && r.start < origEnd).map(r => r.el)

    matched.forEach(el => {
      el.style.background = 'var(--gold-light)'
      el.style.borderRadius = '2px'
    })
    matched[0]?.scrollIntoView({ block: 'center', behavior: prefersReducedMotion() ? 'auto' : 'smooth' })
  }, [highlightAnchor])

  const title = source?.split('/').pop() || source || 'Untitled document'

  return (
    <div
      className="fixed inset-0 z-[100] flex items-center justify-center p-6"
      style={{ background: 'var(--overlay-scrim)' }}
      onClick={handleClose}
    >
      <div
        ref={modalRef}
        className="flex flex-col overflow-hidden rounded-[var(--radius-md)]"
        style={{
          width: 'min(720px, 100%)',
          height: 'min(88vh, 920px)',
          background: 'var(--bg-card)',
          border: '1px solid var(--border-default)',
          boxShadow: 'var(--shadow-panel)',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div
          className="flex items-center gap-2.5 px-4 py-3 flex-shrink-0"
          style={{ borderBottom: '1px solid var(--border-default)', background: 'var(--bg-soft)' }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--gold)" strokeWidth="2" className="flex-shrink-0">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14,2 14,8 20,8" />
            <line x1="16" y1="13" x2="8" y2="13" />
            <line x1="16" y1="17" x2="8" y2="17" />
          </svg>
          <p
            className="m-0 flex-1 min-w-0 truncate text-[13px] font-semibold"
            style={{ fontFamily: 'var(--font-sans)', color: 'var(--text-primary)' }}
            title={source}
          >
            {title}
          </p>
          <span
            className="text-[10px] tabular-nums flex-shrink-0"
            style={{ color: 'var(--text-muted)', fontFamily: "var(--font-mono)" }}
          >
            Page {pageNumber}{numPages ? ` of ${numPages}` : ''}
          </span>
          <button
            onClick={handleClose}
            className="flex items-center justify-center w-7 h-7 rounded-[5px] transition-colors flex-shrink-0"
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

        {/* Content */}
        <div className="flex-1 overflow-auto flex flex-col items-center p-4 gap-2" style={{ background: 'var(--bg-soft)' }}>
          {(loadError || timedOut) && (
            <div className="flex-1 flex flex-col items-center justify-center gap-3">
              <MutedNote>
                {timedOut
                  ? 'This is taking longer than expected.'
                  : `Could not load this document (${loadError}).`}
              </MutedNote>
              <NavButton onClick={handleRetry}>Retry</NavButton>
            </div>
          )}
          {!loadError && !timedOut && fileUrl && (
            <div ref={pageWrapRef}>
              <Document
                file={fileUrl}
                onLoadSuccess={({ numPages: total }) => setNumPages(total)}
                loading={<MutedNote>Loading document…</MutedNote>}
                error={<MutedNote>This document could not be rendered.</MutedNote>}
              >
                <Page
                  pageNumber={pageNumber}
                  width={PAGE_WIDTH}
                  renderAnnotationLayer={false}
                  onRenderTextLayerSuccess={handleTextLayerRendered}
                  loading={<MutedNote>Rendering page…</MutedNote>}
                />
              </Document>
              {notFound && <MutedNote>Passage not found on this page.</MutedNote>}
            </div>
          )}
          {!loadError && !timedOut && !fileUrl && (
            <MutedNote>
              {slowFetch ? 'Still fetching — large documents can take a while to load.' : 'Fetching document…'}
            </MutedNote>
          )}
        </div>

        {/* Page navigation */}
        <div
          className="flex items-center justify-center gap-2.5 px-4 py-2.5 flex-shrink-0"
          style={{ borderTop: '1px solid var(--border-default)', background: 'var(--bg-card)' }}
        >
          <NavButton disabled={pageNumber <= 1} onClick={() => setPageNumber(p => p - 1)}>‹ Prev</NavButton>
          <NavButton disabled={numPages != null && pageNumber >= numPages} onClick={() => setPageNumber(p => p + 1)}>Next ›</NavButton>
        </div>
      </div>
    </div>
  )
}
