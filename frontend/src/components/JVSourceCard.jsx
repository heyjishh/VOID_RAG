import { useState } from 'react'
import { ChevronDown, ChevronUp, ExternalLink, CheckCircle, AlertTriangle, XCircle, Loader2, FileText, ScanLine, X } from 'lucide-react'

const UPLOAD_STATUS = {
  processing: { label: 'Processing…', color: 'var(--primary)', Icon: Loader2, spin: true },
  ocr: { label: 'OCR…', color: 'var(--primary)', Icon: ScanLine, spin: true },
  ready: { label: 'Ready', color: 'var(--accent-green, #16a34a)', Icon: CheckCircle },
  duplicate: { label: 'Already added', color: '#ca8a04', Icon: CheckCircle },
  error: { label: 'Failed', color: 'var(--color-error)', Icon: XCircle },
}

export { UPLOAD_STATUS }

export function UploadedFileChip({ file, onRemove }) {
  const style = UPLOAD_STATUS[file.status] || UPLOAD_STATUS.processing
  const Icon = style.Icon
  const busy = file.status === 'processing' || file.status === 'ocr'
  const detail =
    file.status === 'ready'
      ? file.ocrPages
        ? `OCR · ${file.ocrPages}p`
        : `${file.chunks} chunk${file.chunks === 1 ? '' : 's'}`
      : file.status === 'error'
        ? file.error || style.label
        : style.label

  return (
    <span
      className="flex items-center gap-1.5 text-[10px] px-2 py-0.5 rounded-full"
      style={{ background: 'var(--bg-soft)', color: 'var(--text-secondary)', border: '1px solid var(--border-default)' }}
      title={file.error || file.name}
    >
      <FileText size={10} />
      <span className="max-w-[110px] truncate">{file.name}</span>
      <span className="flex items-center gap-1" style={{ color: style.color }}>
        <Icon size={10} className={style.spin ? 'animate-spin' : ''} />
        <span className="max-w-[90px] truncate">{detail}</span>
      </span>
      {onRemove && !busy && (
        <button
          type="button"
          onClick={() => onRemove(file)}
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: 'var(--text-muted)', display: 'flex' }}
        >
          <X size={10} />
        </button>
      )}
    </span>
  )
}

const VERDICT_STYLE = {
  grounded: { bg: 'var(--accent-green-bg, rgba(34,197,94,.1))', color: 'var(--accent-green, #16a34a)', label: 'Grounded', Icon: CheckCircle },
  partially_grounded: { bg: 'rgba(234,179,8,.1)', color: '#ca8a04', label: 'Partially Grounded', Icon: AlertTriangle },
  unsupported: { bg: 'var(--color-error-bg)', color: 'var(--color-error)', label: 'Unsupported', Icon: XCircle },
}

export { VERDICT_STYLE }

export default function SourceCard({ source, index }) {
  const [expanded, setExpanded] = useState(false)
  const domainColor = source.domain === 'web'
    ? { bg: 'rgba(59,130,246,.1)', color: '#3b82f6', label: 'Web' }
    : { bg: 'var(--accent-green-bg, rgba(34,197,94,.12))', color: 'var(--accent-green, #16a34a)', label: 'Corpus' }

  return (
    <div
      className="rounded-[6px] overflow-hidden transition-colors duration-150"
      style={{ border: '1px solid var(--border-default)', background: 'var(--bg-card)' }}
    >
      <button
        type="button"
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-start gap-2.5 p-3 text-left"
        style={{ background: 'transparent', border: 'none', cursor: 'pointer' }}
      >
        <span
          className="flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold"
          style={{ background: source.cited ? 'var(--primary)' : 'var(--bg-soft)', color: source.cited ? '#fff' : 'var(--text-muted)', border: source.cited ? 'none' : '1px solid var(--border-default)' }}
        >
          {source.index || index + 1}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-1">
            <span
              className="text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded-[3px]"
              style={{ background: domainColor.bg, color: domainColor.color, letterSpacing: '0.04em' }}
            >
              {domainColor.label}
            </span>
            {source.found_by && (
              <span
                className="text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded-[3px]"
                style={{ background: 'rgba(147,51,234,.1)', color: '#9333ea', letterSpacing: '0.04em' }}
              >
                {source.found_by === 'statute_researcher' ? 'Statute' :
                 source.found_by === 'case_analyst' ? 'Case Law' :
                 source.found_by === 'web_verifier' ? 'Web Check' :
                 source.found_by === 'synthesizer' ? 'Merged' : source.found_by}
              </span>
            )}
            {source.verified && (
              <span
                className="text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded-[3px]"
                style={{ background: 'var(--accent-green-bg, rgba(34,197,94,.1))', color: 'var(--accent-green, #16a34a)', letterSpacing: '0.04em' }}
              >
                Verified
              </span>
            )}
            {source.score > 0 && (
              <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
                {(source.score * 100).toFixed(0)}%
              </span>
            )}
          </div>
          <p className="m-0 text-[12.5px] font-semibold leading-snug line-clamp-2" style={{ color: 'var(--text-primary)' }}>
            {source.source || source.title || `Source ${index + 1}`}
          </p>
          {source.page > 0 && (
            <p className="m-0 mt-0.5 text-[11px]" style={{ color: 'var(--text-muted)' }}>Page {source.page}</p>
          )}
        </div>
        {expanded ? <ChevronUp size={14} style={{ color: 'var(--text-muted)', flexShrink: 0 }} /> : <ChevronDown size={14} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />}
      </button>
      {expanded && (
        <div className="px-3 pb-3" style={{ borderTop: '1px solid var(--border-default)' }}>
          <p className="m-0 mt-2 text-[11.5px] leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
            {source.preview || source.text || source.content || ''}
          </p>
          {source.citation_quote && (
            <div className="mt-2 px-2.5 py-2 rounded-[4px]" style={{ background: 'var(--bg-soft)', borderLeft: '2px solid var(--primary)' }}>
              <p className="m-0 text-[11px] italic" style={{ color: 'var(--text-muted)' }}>"{source.citation_quote}"</p>
            </div>
          )}
          {source.url && (
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 mt-2 text-[11px] font-medium"
              style={{ color: 'var(--primary)' }}
            >
              <ExternalLink size={11} /> Open source
            </a>
          )}
        </div>
      )}
    </div>
  )
}

export function VerificationBadge({ verification }) {
  if (!verification?.verdict) return null
  const style = VERDICT_STYLE[verification.verdict] || VERDICT_STYLE.unsupported
  const Icon = style.Icon
  const score = verification.groundedness_score

  return (
    <div
      className="flex items-center gap-2 px-3 py-2 rounded-[6px]"
      style={{ background: style.bg, border: `1px solid ${style.color}22` }}
    >
      <Icon size={14} style={{ color: style.color }} />
      <span className="text-[11.5px] font-semibold" style={{ color: style.color }}>
        {style.label}
      </span>
      {score != null && (
        <span className="text-[11px]" style={{ color: style.color, opacity: 0.8 }}>
          {(score * 100).toFixed(0)}%
        </span>
      )}
      {verification.summary && (
        <span className="text-[11px] ml-1 truncate" style={{ color: 'var(--text-muted)', maxWidth: 300 }}>
          {verification.summary}
        </span>
      )}
    </div>
  )
}
