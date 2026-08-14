// Client-side export of an assistant answer to a Markdown/plain-text file.
// Two modes: keep the inline [N] citation markers and append a numbered
// sources list, or strip the markers for clean prose. The pure string
// functions are kept separate from the Blob download so they stay testable
// without a DOM (see exportAnswer.selfcheck.mjs).

// Matches an inline [N] marker plus the single optional space in front of it,
// so "held X [1]." collapses to "held X." instead of leaving "held X .".
const CITATION_MARKER = /\s?\[\d{1,3}\]/g

export function stripCitations(text) {
  return String(text || '').replace(CITATION_MARKER, '')
}

// One "[N] filename — p.X" line per citation, in the same 1-based order the
// [N] markers reference (citations[N-1]). Falls back to array position when a
// citation predates the backend `index` field (legacy answers leave index 0).
// Page is 0-based on the wire, +1 for display — matching CitationStrip/SourceCard.
export function buildSourcesList(citations) {
  if (!citations || citations.length === 0) return ''
  return citations
    .map((c, i) => {
      const n = c.index > 0 ? c.index : i + 1
      const file = c.source?.split('/').pop() || c.source || 'source'
      const page = c.page != null ? ` — p.${c.page + 1}` : ''
      return `[${n}] ${file}${page}`
    })
    .join('\n')
}

// Compose the full Markdown document. withCitations keeps the [N] markers and
// appends a Sources section; otherwise the prose is stripped clean.
export function answerToMarkdown(text, citations, { withCitations } = {}) {
  const body = (withCitations ? String(text || '') : stripCitations(text)).trim()
  if (!withCitations) return body + '\n'
  const sources = buildSourcesList(citations)
  return sources ? `${body}\n\n---\n\n## Sources\n\n${sources}\n` : body + '\n'
}

// Trigger a client-side download of `content` as `filename` — no server round
// trip, no dependency: a Blob + object URL + synthetic anchor click.
export function downloadTextFile(filename, content, mime = 'text/markdown') {
  const blob = new Blob([content], { type: `${mime};charset=utf-8` })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
