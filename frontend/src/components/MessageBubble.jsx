import { useRef, useEffect, useMemo } from 'react'
import gsap from 'gsap'
import { marked } from 'marked'
import VerificationBadge from './VerificationBadge.jsx'
import CitationStrip from './CitationStrip.jsx'
import { prefersReducedMotion } from '../lib/motion.js'
import { scrollToSource } from '../lib/sourceNav.js'
import { answerToMarkdown, downloadTextFile } from '../lib/exportAnswer.js'

marked.setOptions({ gfm: true, breaks: true })

function escapeAttr(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

// Turn [N] markers the model emitted into clickable citation badges, reusing
// CitationStrip's verified/unverified pill language. N maps directly to
// citations[N-1] (the backend numbers evidence in the same order), so no new
// backend field is invented. The alternation consumes whole HTML tags first and
// only rewrites [N] found in text — a [N] inside an attribute (e.g. a URL) is
// swallowed by the tag branch and left intact. Markers outside the citation
// range stay as literal text.
function injectCitations(html, citations) {
  if (!citations || citations.length === 0) return html
  return html.replace(/(<[^>]+>)|\[(\d{1,3})\]/g, (match, tag, num) => {
    if (tag) return tag
    const cite = citations[Number(num) - 1]
    if (!cite) return match
    const tip = cite.quote
      ? `“${cite.quote}” — ${cite.verified ? 'matched to source' : 'not directly matched, verify manually'}`
      : (cite.verified ? 'Matched to source text' : 'Not directly matched to source text — verify manually')
    const color = cite.verified ? 'var(--sage)' : 'var(--text-secondary)'
    const bg = cite.verified ? 'var(--sage-light)' : 'var(--bg-soft)'
    const border = cite.verified ? 'var(--sage-border)' : 'var(--border-default)'
    return (
      `<button type="button" class="citation-ref" data-cite="${num}" ` +
      `title="${escapeAttr(tip)}" ` +
      `style="color:${color};background:${bg};border:1px solid ${border}">${num}</button>`
    )
  })
}

function ScalesIcon({ size = 13, color = 'currentColor' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <line x1="12" y1="3" x2="12" y2="22" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="4" y1="7" x2="20" y2="7" stroke={color} strokeWidth="1.5" strokeLinecap="round" />
      <line x1="4" y1="7" x2="2" y2="13" stroke={color} strokeWidth="1.2" strokeLinecap="round" />
      <line x1="20" y1="7" x2="22" y2="13" stroke={color} strokeWidth="1.2" strokeLinecap="round" />
      <path d="M1 13 Q4 17 7 13" stroke={color} strokeWidth="1.4" strokeLinecap="round" fill="none" />
      <path d="M17 13 Q20 17 23 13" stroke={color} strokeWidth="1.4" strokeLinecap="round" fill="none" />
      <path d="M9.5 22 Q12 20.5 14.5 22" stroke={color} strokeWidth="1.4" strokeLinecap="round" fill="none" />
    </svg>
  )
}

function DownloadIcon({ size = 12, color = 'currentColor' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
      <path d="M12 3v12" stroke={color} strokeWidth="1.6" strokeLinecap="round" />
      <path d="M7 11l5 5 5-5" stroke={color} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      <path d="M4 20h16" stroke={color} strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  )
}

export default function MessageBubble({ message, onRefine }) {
  const bubbleRef = useRef(null)
  const isUser = message.role === 'user'

  useEffect(() => {
    if (!bubbleRef.current || prefersReducedMotion()) return
    gsap.fromTo(
      bubbleRef.current,
      { opacity: 0, y: 12, scale: 0.98 },
      { opacity: 1, y: 0, scale: 1, duration: 0.28, ease: 'power3.out' }
    )
  }, [])

  const text = message.content || message.answer || ''

  const htmlContent = useMemo(() => {
    if (isUser || !text) return null
    try { return injectCitations(marked.parse(text), message.citations) } catch { return null }
  }, [isUser, text, message.citations])

  // Event delegation: one handler for every [N] badge in the rendered answer.
  function handleCitationClick(e) {
    const badge = e.target.closest('.citation-ref')
    if (!badge) return
    const n = Number(badge.dataset.cite)
    if (n >= 1) scrollToSource(n - 1)
  }

  // Export the answer as a Markdown file, with or without inline [N] markers +
  // a Sources list. Plain-text Markdown via a client-side Blob — no server, no
  // dependency. PDF export would be a follow-up (see note in exportAnswer.js).
  function handleDownload(withCitations) {
    const md = answerToMarkdown(text, message.citations, { withCitations })
    const suffix = withCitations ? 'cited' : 'clean'
    downloadTextFile(`juryai-answer-${suffix}.md`, md)
  }

  return (
    <div
      ref={bubbleRef}
      className={`flex group ${isUser ? 'justify-end' : 'justify-start'}`}
      style={prefersReducedMotion() ? undefined : { opacity: 0 }}
    >
      {/* Assistant avatar — ink, not brand crimson: this is the AI's presence, not the user's */}
      {!isUser && (
        <div
          className="w-[26px] h-[26px] rounded-[7px] flex items-center justify-center flex-shrink-0 mr-2.5 mt-0.5"
          style={{
            background: 'var(--ink)',
            boxShadow: 'var(--shadow-ink-sm)',
          }}
        >
          <ScalesIcon size={12} color="var(--on-ink)" />
        </div>
      )}

      {/* Bubble — the user speaks in a compact quote; the assistant answers as a
          document, so it gets the wider measure and roomier margins of a brief. */}
      <div
        className={`text-sm leading-relaxed ${isUser ? 'max-w-[78%]' : 'max-w-[88%]'}`}
        style={{
          padding: isUser ? '10px 14px' : '14px 16px',
          borderRadius: isUser ? '10px 10px 2px 10px' : '2px 10px 10px 10px',
          background: isUser ? 'var(--primary)' : 'var(--bg-card)',
          border: isUser ? 'none' : '1px solid var(--border-default)',
          color: isUser ? 'var(--on-primary)' : 'var(--text-primary)',
          boxShadow: 'var(--shadow-card)',
        }}
      >
        {/* Streaming indicator */}
        {message.streaming && (
          <div className="flex items-center gap-2 mb-1.5">
            <span className="flex gap-1">
              {[0, 1, 2].map(i => (
                <span
                  key={i}
                  className="w-1.5 h-1.5 rounded-full inline-block"
                  style={{
                    background: 'var(--gold)',
                    animation: 'chat-bounce 1.3s ease-in-out infinite',
                    animationDelay: `${i * 0.18}s`,
                  }}
                />
              ))}
            </span>
            <span
              className="text-[11px]"
              style={{ color: 'var(--text-muted)' }}
            >
              Drafting response…
            </span>
          </div>
        )}

        {/* Content */}
        {isUser ? (
          <p className="m-0 whitespace-pre-wrap">{text}</p>
        ) : htmlContent ? (
          <div className="prose-md" onClick={handleCitationClick} dangerouslySetInnerHTML={{ __html: htmlContent }} />
        ) : (
          <p className="m-0 whitespace-pre-wrap">{text}</p>
        )}

        {/* Answer dossier — the trust apparatus below the prose, ordered by
            weight: the groundedness seal leads, the cited evidence trail
            follows, and the quiet provenance line closes it out. One divider
            separates argument from apparatus instead of three loose strips. */}
        {!isUser && !message.streaming &&
          (message.verification || message.citations?.length > 0 || message.intent || message.sources_used > 0) && (
          <div
            className="mt-3.5 pt-3.5 flex flex-col gap-2.5"
            style={{ borderTop: '1px solid var(--border-default)' }}
          >
            {/* Groundedness verdict — the trust seal */}
            {message.verification && (
              <VerificationBadge
                verification={message.verification}
                question={message.question}
                onRefine={onRefine}
              />
            )}

            {/* Citations — claim-level grounding, hover for the matched quote */}
            <CitationStrip citations={message.citations} />

            {/* Provenance — quietest line: how the answer was classified and
                how many passages it drew on. */}
            {(message.intent || message.sources_used > 0) && (
              <div
                className="flex items-center gap-1.5 text-[10.5px] leading-none"
                style={{ color: 'var(--text-muted)' }}
              >
                {message.intent && (
                  <span className="italic">{message.intent.replace(/_/g, ' ')}</span>
                )}
                {message.intent && message.sources_used > 0 && (
                  <span aria-hidden style={{ opacity: 0.5 }}>·</span>
                )}
                {message.sources_used > 0 && (
                  <span className="tabular-nums" style={{ fontFamily: "var(--font-mono)" }}>
                    {message.sources_used} passage{message.sources_used !== 1 ? 's' : ''} drawn on
                  </span>
                )}
              </div>
            )}
          </div>
        )}

        {/* Export — quiet hover/focus-revealed actions: take the answer as a
            Markdown file, with the [N] markers + a Sources list, or clean prose. */}
        {!isUser && !message.streaming && text && (
          <div className="mt-3 flex items-center gap-1.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
            <DownloadIcon size={11} color="var(--text-muted)" />
            {[
              { label: 'with citations', cited: true },
              { label: 'plain', cited: false },
            ].map(({ label, cited }) => (
              <button
                key={label}
                type="button"
                onClick={() => handleDownload(cited)}
                className="text-[10.5px] leading-none px-2 py-1 rounded-md transition-colors"
                style={{
                  color: 'var(--text-secondary)',
                  border: '1px solid var(--border-default)',
                  background: 'var(--bg-soft)',
                }}
                title={cited
                  ? 'Download answer with [N] citation markers and a sources list'
                  : 'Download answer as clean prose, citation markers stripped'}
              >
                {label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
