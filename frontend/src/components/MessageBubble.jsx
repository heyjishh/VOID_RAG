import { useRef, useEffect, useMemo } from 'react'
import gsap from 'gsap'
import { marked } from 'marked'
import VerificationBadge from './VerificationBadge.jsx'
import CitationStrip from './CitationStrip.jsx'
import { prefersReducedMotion } from '../lib/motion.js'

marked.setOptions({ gfm: true, breaks: true })

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
    try { return marked.parse(text) } catch { return null }
  }, [isUser, text])

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

      {/* Bubble */}
      <div
        className="max-w-[78%] text-sm leading-relaxed"
        style={{
          padding: '11px 15px',
          borderRadius: isUser ? '13px 13px 4px 13px' : '4px 13px 13px 13px',
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
              style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}
            >
              Drafting response…
            </span>
          </div>
        )}

        {/* Content */}
        {isUser ? (
          <p className="m-0 whitespace-pre-wrap">{text}</p>
        ) : htmlContent ? (
          <div className="prose-md" dangerouslySetInnerHTML={{ __html: htmlContent }} />
        ) : (
          <p className="m-0 whitespace-pre-wrap">{text}</p>
        )}

        {/* Metadata footer */}
        {!isUser && !message.streaming && (message.intent || message.sources_used > 0) && (
          <div
            className="flex gap-2 flex-wrap mt-2.5 pt-2.5"
            style={{ borderTop: '1px solid var(--border-default)' }}
          >
            {message.intent && (
              <span
                className="text-[11px] px-2 py-0.5 rounded-[4px]"
                style={{
                  color: 'var(--text-muted)',
                  background: 'var(--bg-soft)',
                  border: '1px solid var(--border-default)',
                  fontStyle: 'italic',
                }}
              >
                {message.intent}
              </span>
            )}
            {message.sources_used > 0 && (
              <span
                className="text-[11px] font-medium px-2 py-0.5 rounded-[4px]"
                style={{
                  color: 'var(--gold)',
                  background: 'var(--gold-light)',
                  border: '1px solid var(--gold-border)',
                }}
              >
                {message.sources_used} source{message.sources_used !== 1 ? 's' : ''} cited
              </span>
            )}
          </div>
        )}

        {/* Citations — claim-level grounding, hover for the matched quote */}
        {!isUser && !message.streaming && (
          <CitationStrip citations={message.citations} />
        )}

        {/* Groundedness verdict — the trust seal, rendered once verification lands */}
        {!isUser && !message.streaming && message.verification && (
          <VerificationBadge
            verification={message.verification}
            question={message.question}
            onRefine={onRefine}
          />
        )}
      </div>
    </div>
  )
}
