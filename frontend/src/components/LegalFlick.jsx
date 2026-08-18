import { useEffect, useRef, useState } from 'react'
import gsap from 'gsap'
import { prefersReducedMotion } from '../lib/motion.js'

/* ────────────────────────────────────────────────────────────────────────────
   THE CONSTITUTION DESK — interactive. An open volume of the Constitution of
   India on a stand, and it turns when you ask it to:
   · click the book (or tap a pager segment) → the leaf turns to the next
     spread, the paper curl sweeps, the blood-red passage draws itself
   · spreads: I THE PREAMBLE · II FUNDAMENTAL RIGHTS · III THE RESEARCH DESK
     (what we do) · IV ASK THE DESK (tap a prompt to open a research matter)
   · the book leans toward the cursor; auto-turns while you watch, pauses
     when you hover; honors prefers-reduced-motion (instant turns only)
   Variants: 'full' (books + gavel + drifting citation sheets), 'compact'
   (book + wheel) for the chat empty state / mobile auth.
   ──────────────────────────────────────────────────────────────────────────── */

const BASE_W = 480
const BASE_H = 520

const SPREADS = [
  {
    n: 'I',
    name: 'THE PREAMBLE',
    kicker: 'CONSTITUTION OF INDIA',
    title: 'THE PREAMBLE',
    lines: [
      'WE, THE PEOPLE OF',
      'INDIA — SOVEREIGN',
      'SOCIALIST SECULAR',
      'DEMOCRATIC REPUBLIC,',
      'securing JUSTICE,',
      'LIBERTY, EQUALITY,',
      'FRATERNITY, and the',
      'dignity of all.',
    ],
    hl: 'DEMOCRATIC REPUBLIC',
    foot: ['ADOPTED 26 NOV 1949', 'IN FORCE 26 JAN 1950'],
    card: { kicker: 'SPREAD I · IV', title: 'PREAMBLE NOTE', lines: ['Adopted 26 Nov 1949,', 'in force since', '26 Jan 1950 —', 'Republic Day. Its', 'words govern every', 'law of India.'], foot: 'THE CONSTITUTION' },
  },
  {
    n: 'II',
    name: 'FUNDAMENTAL RIGHTS',
    kicker: 'PART III · ARTS. 12–35',
    title: 'FUNDAMENTAL RIGHTS',
    lines: [
      'Art. 14 — equality',
      'before the law.',
      'Art. 19 — six',
      'freedoms. Art. 21 —',
      'life and liberty,',
      'by a just procedure.',
      'ART. 32 — remedies',
      'are fundamental.',
    ],
    hl: 'ART. 32',
    foot: 'PART III · CONSTITUTION OF INDIA',
    card: { kicker: 'SPREAD II · IV', title: 'THE GUARANTEE', lines: ['Rights enforceable', 'against the State,', 'guarded by the', 'courts through', 'writs.'], foot: 'CONSTITUTION OF INDIA' },
  },
  {
    n: 'III',
    name: 'THE RESEARCH DESK',
    kicker: 'HOW JURYAI WORKS',
    title: 'ASK · RETRIEVE · CITE',
    lines: [
      'You ask in plain',
      'language. We open',
      'statutes, precedents,',
      'commentary — every',
      'source scored,',
      'reranked, cited.',
      'Claims stop at the',
      'groundedness gate.',
    ],
    hl: 'groundedness gate',
    foot: 'JURYAI · LEGAL RESEARCH',
    card: { kicker: 'SPREAD III · IV', title: 'THE PIPELINE', lines: ['Question → sources', '→ evidence rank', '→ citable answer', 'with verdict.'], foot: 'LEGAL RESEARCH SYSTEM' },
  },
  {
    n: 'IV',
    name: 'ASK THE DESK',
    kicker: 'TRY A MATTER',
    title: 'ASK THE DESK',
    asks: ['§ 302 IPC — punishment?', 'Bail under CrPC 439?', 'Art. 21 — key cases?'],
    foot: 'JURYAI · LEGAL RESEARCH',
    card: { kicker: 'SPREAD IV · IV', title: 'A MATTER', lines: ['Type a question or', 'tap a prompt — the', 'desk opens the law', 'with sources.'], foot: 'LEGAL RESEARCH SYSTEM' },
  },
]

const CHIPS = ['THE PREAMBLE', 'ART. 21 · RIGHTS', 'THE RESEARCH DESK', 'ASK THE DESK', 'PREAMBLE II', 'RIGHTS III']

const faceBase = {
  position: 'absolute',
  inset: 0,
  background: 'var(--page)',
  color: 'var(--page-ink)',
  backfaceVisibility: 'hidden',
  WebkitBackfaceVisibility: 'hidden',
  display: 'flex',
  flexDirection: 'column',
  padding: '10px 9px',
  boxSizing: 'border-box',
  border: '1px solid rgba(22,19,13,0.4)',
  overflow: 'hidden',
}

const paperGrain = {
  backgroundImage:
    'repeating-linear-gradient(90deg, rgba(22,19,13,0.035) 0 2px, transparent 2px 3px), linear-gradient(90deg, rgba(22,19,13,0.22) 0%, transparent 26%)',
}

const hlStyle = { position: 'relative', fontWeight: 700, color: 'var(--blood, #c1121f)' }

const underlineStyle = {
  position: 'absolute',
  left: 0,
  right: 0,
  bottom: 0,
  height: 2,
  background: 'var(--blood, #c1121f)',
  transform: 'scaleX(0)',
  transformOrigin: 'left center',
  willChange: 'transform',
}

const L = { fontFamily: 'var(--font-mono)', fontSize: 8.2, lineHeight: 1.4, opacity: 0.94 }

function Line({ text, hl, i }) {
  const parts = hl ? text.split(hl) : [text]
  if (!hl || parts.length < 2) return <div key={i} style={L}>{text}</div>
  return (
    <div key={i} style={L}>
      {parts[0]}
      <span style={hlStyle}>
        {hl}
        <i data-hl="true" style={underlineStyle} />
      </span>
      {parts[1]}
    </div>
  )
}

function PageFace({ data, onPrompt, back }) {
  const foots = Array.isArray(data.foot) ? data.foot : [data.foot]
  return (
    <div style={{ ...faceBase, ...(back ? { transform: 'rotateY(180deg)' } : {}) }} aria-hidden="true">
      <div style={paperGrain} className="face-grain" />
      {data.kicker && (
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 7.5, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--blood, #c1121f)' }}>
          {data.kicker}
        </span>
      )}
      {data.title && (
        <span style={{ fontFamily: 'var(--font-display)', fontSize: 12, fontWeight: 700, letterSpacing: '-0.01em', marginTop: 2, lineHeight: 1.15 }}>
          {data.title}
        </span>
      )}
      <div style={{ marginTop: 4, display: 'flex', flexDirection: 'column' }}>
        {data.lines && data.lines.map((t, i) => <Line key={i} text={t} hl={data.hl} i={i} />)}
        {data.asks && (
          <div style={{ marginTop: 2, display: 'flex', flexDirection: 'column', gap: 4 }}>
            {data.asks.map((q, i) => (
              <button
                key={i}
                type="button"
                data-ask="true"
                onClick={e => { e.stopPropagation(); onPrompt && onPrompt(q) }}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 8,
                  lineHeight: 1.4,
                  textAlign: 'left',
                  color: 'var(--page-ink)',
                  background: 'rgba(193,18,31,0.08)',
                  border: '1px solid rgba(193,18,31,0.55)',
                  borderRadius: 2,
                  padding: '4px 6px',
                  cursor: onPrompt ? 'pointer' : 'default',
                  transition: 'background var(--dur-fast) var(--ease-out)',
                }}
                onMouseEnter={e => { e.currentTarget.style.background = 'rgba(193,18,31,0.18)' }}
                onMouseLeave={e => { e.currentTarget.style.background = 'rgba(193,18,31,0.08)' }}
              >
                {onPrompt ? '→ ' : '§ '} {q}
              </button>
            ))}
          </div>
        )}
      </div>
      {data.foot && (
        <div style={{ marginTop: 'auto', paddingTop: 3, borderTop: '1px solid rgba(22,19,13,0.25)', fontFamily: 'var(--font-mono)', fontSize: 6.5, lineHeight: 1.4, letterSpacing: '0.08em', color: 'var(--text-muted)', opacity: 0.9 }}>
          {foots.map((f, i) => <div key={i}>{f}</div>)}
        </div>
      )}
    </div>
  )
}

function Leaf({ front, back, onPrompt }) {
  return (
    <div
      data-leaf="true"
      style={{
        position: 'absolute',
        left: 158,
        top: 5,
        width: 154,
        height: 192,
        transformStyle: 'preserve-3d',
        transformOrigin: 'left center',
        zIndex: 10,
      }}
      aria-hidden="true"
    >
      <div
        data-curl="true"
        style={{
          position: 'absolute',
          inset: 0,
          background: 'linear-gradient(90deg, transparent 20%, rgba(22,19,13,0.28) 55%, rgba(22,19,13,0.5) 100%)',
          transform: 'translateX(60%)',
          zIndex: 5,
          pointerEvents: 'none',
          willChange: 'transform',
        }}
      />
      <PageFace data={front} onPrompt={onPrompt} />
      <PageFace data={back} back />
    </div>
  )
}

function Book({ spreads, onPrompt, rests }) {
  return (
    <div
      data-book="true"
      style={{ position: 'absolute', left: 82, top: 128, width: 316, height: 202, cursor: 'pointer' }}
      aria-hidden="true"
    >
      <div style={{ position: 'absolute', inset: 0, background: 'var(--primary)', border: '1px solid var(--ink)', borderRadius: 2 }} />
      <div style={{ position: 'absolute', left: '50%', top: 0, width: 8, marginLeft: -4, height: '100%', background: 'var(--gold)', opacity: 0.9, borderLeft: '1px solid var(--ink)', boxSizing: 'border-box' }} />
      <div data-page-l="true" style={{ ...faceBase, left: 4, top: 4, width: 150, height: 194, borderRadius: '2px 0 0 2px', paddingRight: 8, boxShadow: 'inset -14px 0 18px -18px rgba(22,19,13,0.5)' }}>
        <div style={paperGrain} className="face-grain" />
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 7.5, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--blood, #c1121f)' }}>THE CONSTITUTION</span>
        <span style={{ fontFamily: 'var(--font-display)', fontSize: 12, fontWeight: 700, marginTop: 2 }}>What it is</span>
        <div style={{ marginTop: 4, display: 'flex', flexDirection: 'column', gap: 0 }}>
          {['The supreme law of', 'India — 395 articles,', '12 schedules, 105+', 'amendments: the', 'longest written', 'constitution of any', 'sovereign nation.'] .map((t, i) => (
            <div key={i} style={L}>{t}</div>
          ))}
        </div>
        <div style={{ marginTop: 'auto', fontFamily: 'var(--font-mono)', fontSize: 6.5, letterSpacing: '0.08em', opacity: 0.9, paddingTop: 3, borderTop: '1px solid rgba(22,19,13,0.25)' }}>
          भारत का संविधान
        </div>
      </div>
      <div data-page-r="true" style={{ ...faceBase, left: 158, top: 4, width: 154, height: 194, borderRadius: '0 2px 2px 0', paddingLeft: 10, boxShadow: 'inset 14px 0 18px -18px rgba(22,19,13,0.5)' }}>
        <div style={paperGrain} className="face-grain" />
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 8, fontWeight: 700, letterSpacing: '0.14em', textTransform: 'uppercase', color: 'var(--blood, #c1121f)' }}>RESEARCHING</span>
        <span style={{ fontFamily: 'var(--font-display)', fontSize: 12, fontWeight: 700, marginTop: 3 }}>The Constitution desk</span>
        {Array.from({ length: 7 }, (_, k) => (
          <div key={k} style={{ height: 2, background: 'rgba(22,19,13,0.35)', marginTop: 8, width: `${96 - (k % 3) * 16}%` }} />
        ))}
      </div>
      {spreads.map((s, i) => (
        <Leaf key={s.n} front={rests[i] ? s.card : s} back={rests[i] ? s : s.card} onPrompt={onPrompt} />
      ))}
      {spreads.map((s, i) => (
        <div
          key={`rest-${s.n}`}
          data-rest="true"
          style={{
            position: 'absolute', left: 4, top: 5, width: 154, height: 192, zIndex: 9,
            visibility: rests[i] ? 'visible' : 'hidden',
            borderRadius: '2px 0 0 2px',
          }}
        >
          <PageFace data={s.card} />
        </div>
      ))}
    </div>
  )
}

function ClosedBook() {
  return (
    <div
      data-book="true"
      style={{ position: 'absolute', left: '50%', top: 220, width: 250, height: 158, marginLeft: -125, cursor: 'default' }}
      aria-hidden="true"
    >
      <div style={{ position: 'absolute', inset: 0, background: 'var(--primary)', border: '1px solid var(--ink)', borderRadius: 3, boxShadow: '0 12px 26px -16px rgba(0,0,0,0.55)' }} />
      <div style={{ position: 'absolute', left: '50%', top: 0, width: 10, marginLeft: -5, height: '100%', background: 'var(--gold)', opacity: 0.9, borderLeft: '1px solid var(--ink)', borderRight: '1px solid var(--ink)', boxSizing: 'border-box' }} />
      <div style={{ position: 'absolute', left: '50%', top: '38%', width: 36, height: 36, marginLeft: -18, borderRadius: '50%', border: '3px solid var(--gold)' }} />
    </div>
  )
}

function BookStack() {
  const spines = [
    { t: 'IPC', h: 96, c: 'var(--bg-plan)' },
    { t: 'CrPC', h: 120, c: 'var(--bg-plan)' },
    { t: 'EVID.', h: 78, c: 'var(--bg-plan-deep)' },
  ]
  return (
    <div data-stack="true" style={{ position: 'absolute', left: 8, top: 208, width: 72, display: 'flex', alignItems: 'flex-end', gap: 4 }} aria-hidden="true">
      {spines.map((s, i) => (
        <div
          key={s.t}
          data-bob="true"
          style={{
            width: i === 2 ? 30 : 22,
            height: s.h,
            background: s.c,
            border: '1px solid var(--border-strong)',
            borderRadius: 2,
            display: 'flex',
            alignItems: 'flex-end',
            justifyContent: 'center',
            paddingBottom: 8,
            boxSizing: 'border-box',
          }}
        >
          <span style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)', fontFamily: 'var(--font-mono)', fontSize: 8, letterSpacing: '0.14em', color: 'var(--gold)' }}>
            {s.t}
          </span>
        </div>
      ))}
    </div>
  )
}

function Gavel() {
  return (
    <div data-gavel-box="true" style={{ position: 'absolute', right: 12, top: 196, width: 84, height: 140 }} aria-hidden="true">
      <div style={{ position: 'absolute', left: 0, bottom: 0, width: 84, height: 12, background: 'var(--bg-plan-deep)', border: '1px solid var(--border-strong)' }} />
      <div style={{ position: 'absolute', left: -6, bottom: 12, width: 96, height: 3, background: 'var(--sage)' }} />
      <div data-gavel="true" style={{ position: 'absolute', left: 32, bottom: 34, width: 18, height: 84, background: 'var(--bg-plan)', border: '1px solid var(--border-strong)', transformOrigin: 'bottom center' }} />
      <div data-gavel="true" style={{ position: 'absolute', left: 12, bottom: 104, width: 56, height: 44, background: 'var(--ink)', border: '1px solid var(--border-strong)', borderRadius: 3, transformOrigin: 'bottom center' }} />
    </div>
  )
}

export default function LegalFlick({ variant = 'full', className, style, onPrompt }) {
  const hostRef = useRef(null)
  const sceneRef = useRef(null)
  const idxRef = useRef(0)
  const total = variant === 'compact' ? 2 : SPREADS.length
  const spreads = SPREADS.slice(0, total)
  const [rests, setRests] = useState(Array.from({ length: total }, () => false))
  const markRest = i => setRests(prev => { if (prev[i]) return prev; const n = [...prev]; n[i] = true; return n })
  const clearRest = i => setRests(prev => { if (!prev[i]) return prev; const n = [...prev]; n[i] = false; return n })

  useEffect(() => {
    const host = hostRef.current
    const scene = sceneRef.current
    if (!host || !scene) return

    const scale = () => {
      const w = host.clientWidth || BASE_W
      const h = host.clientHeight || BASE_H
      const s = Math.min(w / BASE_W, h / BASE_H)
      scene.style.transform = `translate(-50%, -50%) scale(${s})`
    }
    scale()
    const ro = new ResizeObserver(scale)
    ro.observe(host)

    const reduced = prefersReducedMotion()

    /* ---- compact: the desk is CLOSED — a sealed volume, no text faces.
       Nothing 3D, nothing scaled-down to illegibility; the wheel turns and
       the book breathes. ---- */
    if (variant === 'compact') {
      const wheelC = scene.querySelector('[data-wheel]')
      const bookC = scene.querySelector('[data-book]')
      if (reduced || !wheelC || !bookC) return () => ro.disconnect()
      const spinC = gsap.to(wheelC, { rotation: 360, duration: 24, repeat: -1, ease: 'none' })
      const bobC = gsap.to(bookC, { y: -5, duration: 1.8, repeat: -1, yoyo: true, ease: 'sine.inOut' })
      return () => { ro.disconnect(); spinC.kill(); bobC.kill() }
    }

    const book = scene.querySelector('[data-book]')
    const leaves = [...scene.querySelectorAll('[data-leaf]')]
    const curls = [...scene.querySelectorAll('[data-curl]')]
    const wheel = scene.querySelector('[data-wheel]')
    const chips = [...scene.querySelectorAll('[data-chip]')]
    const bobs = [...scene.querySelectorAll('[data-bob]')]
    const gavels = [...scene.querySelectorAll('[data-gavel]')]
    const dots = [...scene.querySelectorAll('[data-pager-dot]')]
    const label = scene.querySelector('[data-pager-label]')
    const hint = scene.querySelector('[data-hint]')
    if (!book || !leaves.length) return () => ro.disconnect()

    gsap.set(leaves, { rotationY: 0, z: 0 })

    /* ---- pager state ---- */
    const paint = () => {
      const s = spreads[idxRef.current]
      dots.forEach((d, i) => {
        const on = i === idxRef.current
        d.style.background = on ? 'var(--primary)' : 'transparent'
        d.style.color = on ? 'var(--on-primary)' : 'var(--text-secondary)'
      })
      if (label) label.textContent = `SPREAD ${s.n} · ${total} — ${s.name}`
    }

    /* ---- At rest NOTHING is 3D: a flipped leaf is hidden and its flat
       "rest" page (data-rest, no transform at all) takes its place — text
       is re-rasterized natively, always crisp. 3D (perspective on the book)
       exists only for the ~1s of an actual turn. ---- */
    let flipCount = 0
    const ensure3D = () => {
      flipCount += 1
      gsap.set(book, { perspective: 1400 })
    }
    const settle3D = () => {
      flipCount = Math.max(0, flipCount - 1)
      if (flipCount === 0) gsap.set(book, { perspective: 'none' })
    }

    /* ---- one leaf turning forward (0 → -180): at completion the leaf
       disappears and its flat card page takes over the left half. ---- */
    const flipForward = (i, delay = 0) => {
      const leaf = leaves[i]
      const curl = curls[i]
      const nextFace = leaves[i + 1] ? leaves[i + 1].querySelector('[data-hl]') : null
      ensure3D()
      gsap.set(leaf, { zIndex: 30, visibility: 'visible' })
      gsap.to(leaf, {
        rotationY: -180, z: 8, duration: 1.05, delay, ease: 'power2.inOut',
        onComplete: () => {
          gsap.set(leaf, { z: 0, zIndex: 10, visibility: 'hidden' })
          markRest(i)
          settle3D()
        },
      })
      if (curl) {
        gsap.fromTo(curl, { xPercent: 60, opacity: 0 }, { xPercent: -130, opacity: 0.9, duration: 0.85, delay, ease: 'power1.in' })
        gsap.to(curl, { opacity: 0, duration: 0.35, delay: delay + 0.75 })
      }
      if (nextFace) gsap.fromTo(nextFace, { scaleX: 0 }, { scaleX: 1, duration: 0.55, delay: delay + 0.95, ease: 'power2.out' })
      return leaf
    }

    /* ---- one leaf turning back: the leaf is re-shown mid-state (card on
       the left, at -180, seamless with the flat page) and turns to 0,
       where its own crisp front face takes over. ---- */
    const flipBackward = (i, delay = 0) => {
      const leaf = leaves[i]
      const curl = curls[i]
      ensure3D()
      gsap.set(leaf, { zIndex: 30, rotationY: -180, z: 8, visibility: 'visible' })
      clearRest(i)
      gsap.to(leaf, {
        rotationY: 0, z: 8, duration: 0.85, delay, ease: 'power2.inOut',
        onComplete: () => { gsap.set(leaf, { z: 0, zIndex: 10 }); settle3D() },
      })
      if (curl) gsap.fromTo(curl, { xPercent: -130, opacity: 0.6 }, { xPercent: 60, opacity: 0, duration: 0.7, delay, ease: 'power1.out' })
      return leaf
    }

    /* ---- instant (reduced-motion / jump) paths, same rest-state rules ---- */
    const collapseLeaf = i => {
      gsap.set(leaves[i], { rotationY: -180, z: 0, zIndex: 10, visibility: 'hidden' })
      markRest(i)
    }
    const restoreLeaf = i => {
      gsap.set(leaves[i], { rotationY: 0, z: 0, zIndex: 10, visibility: 'visible' })
      clearRest(i)
    }

    /* ---- go to a spread ---- */
    const goTo = (target, instant = false) => {
      const cur = idxRef.current
      if (target === cur) return
      idxRef.current = target
      const fwd = target > cur
      const step = fwd ? 0.16 : 0.1

      // Self-heal every leaf NOT part of this transition to its correct
      // rest state, instantly. A prior flip's GSAP tween can fail to reach
      // onComplete (a backgrounded tab throttles requestAnimationFrame, or
      // two auto-turn ticks land close together) — without this, a leaf
      // stuck mid-flip keeps showing stale content forever while the pager
      // silently keeps moving on.
      for (let k = 0; k < total; k++) {
        if (fwd ? (k >= cur && k < target) : (k >= target && k < cur)) continue
        if (k < target) collapseLeaf(k)
        else restoreLeaf(k)
      }

      if (fwd) {
        for (let k = cur; k < target; k++) {
          if (instant) collapseLeaf(k)
          else flipForward(k, (k - cur) * step)
        }
      } else {
        for (let k = cur - 1; k >= target; k--) {
          if (instant) restoreLeaf(k)
          else flipBackward(k, (cur - 1 - k) * step)
        }
      }
      paint()
      if (!instant && hint) {
        hint.style.opacity = 0
        hint.style.transition = 'opacity 0.6s var(--ease-out, ease-out)'
      }
    }

    // Ping-pong the auto-turn: forward (left-to-right) to the last spread,
    // then backward (right-to-left) to the first, repeat — rather than
    // always advancing and snapping back on wrap.
    let dir = 1
    const next = () => {
      const cur = idxRef.current
      if (dir === 1 && cur >= total - 1) dir = -1
      else if (dir === -1 && cur <= 0) dir = 1
      goTo(cur + dir)
    }

    /* ---- auto-turn, paused while you look at it; stopped once you engage ---- */
    let timer = null
    let engaged = false
    const fadeHint = () => {
      if (hint) {
        hint.style.opacity = 0
        hint.style.transition = 'opacity 0.6s var(--ease-out, ease-out)'
      }
    }
    const stopAuto = () => { if (timer) { clearInterval(timer); timer = null } }
    const startAuto = () => {
      if (reduced || engaged) return
      stopAuto()
      timer = setInterval(next, 7000)
    }
    const engage = () => {
      engaged = true
      stopAuto()
      fadeHint()
    }

    book.addEventListener('click', () => { engage(); next(); startAtomics() })
    dots.forEach((d, i) => d.addEventListener('click', () => { engage(); goTo(i); startAtomics() }))
    chips.forEach((c, i) => c.addEventListener('click', () => { engage(); goTo(i % total); startAtomics() }))

    let entered = false
    host.addEventListener('mouseenter', () => { entered = true; stopAuto() })
    host.addEventListener('mouseleave', () => { entered = false; startAuto() })
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) stopAuto()
      else if (!entered) startAuto()
    })

    /* per-interaction gavel tap (engaging beat) */
    let tapOnce = null
    const startAtomics = () => {
      if (reduced || !gavels.length) return
      if (tapOnce) tapOnce.kill()
      tapOnce = gsap.timeline()
        .to(gavels, { rotate: -7, duration: 0.12, ease: 'power2.in' })
        .to(gavels, { rotate: 0, duration: 0.3, ease: 'power2.out' })
    }

    /* ---- ambient: wheel, shelf, drifting sheets, breathing book (2D only,
       so rest text stays crisp) ---- */
    const spin = gsap.to(wheel, { rotation: 360, duration: 24, repeat: -1, ease: 'none' })
    const bob = gsap.timeline({ repeat: -1, defaults: { ease: 'sine.inOut' } })
    if (bobs.length) bob.to(bobs, { y: -6, duration: 2.2, stagger: 0.2 }).to(bobs, { y: 0, duration: 2.2, stagger: 0.2 })
    const drift = gsap.to(chips, {
      y: -90, opacity: 0.35, duration: 3.6, repeat: -1, yoyo: true, ease: 'sine.inOut', stagger: 0.55,
    })
    const lift = reduced ? null : gsap.to(book, { y: -4, duration: 1.7, repeat: -1, yoyo: true, ease: 'sine.inOut' })

    paint()
    startAuto()

    return () => {
      ro.disconnect()
      stopAuto()
      book.removeEventListener('click', next)
      gsap.set(book, { perspective: 'none' })
      if (tapOnce) tapOnce.kill()
      spin.kill(); bob.kill(); drift.kill(); if (lift) lift.kill()
      gsap.killTweensOf([leaves, curls, book, dots, chips])
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div
      ref={hostRef}
      className={className}
      style={{
        // The caller sizes this host — 'absolute inset-0' to fill a
        // positioned parent, or a fixed height for the compact variant.
        // Hardcoding position here would always beat that className
        // (inline styles outrank classes), collapsing 'absolute inset-0'
        // back to 'relative' and, with no in-flow content (the scene is
        // itself absolutely positioned), the host to zero height —
        // clipped invisible by overflow:hidden below.
        position: className?.includes('absolute') ? undefined : 'relative',
        overflow: 'hidden',
        ...style,
      }}
    >
      <div
        ref={sceneRef}
        style={{ position: 'absolute', left: '50%', top: '50%', width: BASE_W, height: BASE_H, transformOrigin: 'center center', willChange: 'transform' }}
      >
        {/* Ashoka wheel + constitution plaque */}
        <div style={{ position: 'absolute', left: '50%', top: 18, transform: 'translateX(-50%)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6 }} aria-hidden="true">
          <div data-wheel="true" style={{ willChange: 'transform' }}>
            <Chakra />
          </div>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 7.5, letterSpacing: '0.22em', color: 'var(--text-muted)', textTransform: 'uppercase', whiteSpace: 'nowrap' }}>
            The Constitution of India · भारत का संविधान
          </span>
        </div>

        {variant === 'compact' ? (
          <>
            <ClosedBook />
            <span style={{ position: 'absolute', left: '50%', top: 402, transform: 'translateX(-50%)', fontFamily: 'var(--font-mono)', fontSize: 7, letterSpacing: '0.16em', color: 'var(--text-muted)', textTransform: 'uppercase', whiteSpace: 'nowrap', pointerEvents: 'none' }}>
              Ask a question to open the desk
            </span>
          </>
        ) : (
          <>
            <Book spreads={spreads} onPrompt={onPrompt} rests={rests} />

        {/* spread pager */}
        <div style={{ position: 'absolute', left: '50%', top: 344, transform: 'translateX(-50%)', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 5, cursor: 'default', userSelect: 'none' }} aria-hidden="true">
          <div style={{ display: 'flex', gap: 4 }}>
            {spreads.map((s, i) => (
              <button
                key={s.n}
                type="button"
                data-pager-dot="true"
                style={{
                  width: 26, height: 18, fontFamily: 'var(--font-mono)', fontSize: 8, fontWeight: 700,
                  letterSpacing: '0.06em', border: '1px solid var(--border-strong)', borderRadius: 2,
                  background: 'transparent', color: 'var(--text-secondary)', cursor: 'pointer',
                  transition: 'background var(--dur-fast) var(--ease-out), color var(--dur-fast) var(--ease-out)',
                }}
              >
                {s.n}
              </button>
            ))}
          </div>
          <span data-pager-label="true" style={{ fontFamily: 'var(--font-mono)', fontSize: 8, letterSpacing: '0.16em', color: 'var(--text-muted)', whiteSpace: 'nowrap' }} />
        </div>

        {/* turn hint */}
        <div data-hint="true" data-turn="true" style={{ position: 'absolute', left: '50%', top: 390, transform: 'translateX(-50%)', fontFamily: 'var(--font-mono)', fontSize: 7.5, letterSpacing: '0.18em', color: 'var(--gold)', whiteSpace: 'nowrap', textTransform: 'uppercase', opacity: 0.85, pointerEvents: 'none' }}>
          ◂ click the desk to turn the spread ▸
        </div>
        <div data-hint="true" style={{ position: 'absolute', left: '50%', top: 406, transform: 'translateX(-50%)', fontFamily: 'var(--font-mono)', fontSize: 7, letterSpacing: '0.14em', color: 'var(--text-muted)', whiteSpace: 'nowrap', pointerEvents: 'none' }}>
          Preamble · Fundamental rights · The desk · Try a matter
        </div>

        <BookStack />
        <Gavel />
        {CHIPS.map((c, i) => (
              <button
                key={c}
                type="button"
                data-chip="true"
                style={{
                  position: 'absolute',
                  left: [16, 236, 396, 54, 402, 172][i],
                  top: [392, 398, 370, 62, 288, 294][i],
                  fontFamily: 'var(--font-mono)',
                  fontSize: 8,
                  letterSpacing: '0.12em',
                  border: '1px dashed var(--border-strong)',
                  borderRadius: 2,
                  padding: '4px 7px',
                  color: 'var(--text-secondary)',
                  background: 'var(--bg-card)',
                  cursor: 'pointer',
                  willChange: 'transform',
                  transition: 'color var(--dur-fast) var(--ease-out), border-color var(--dur-fast) var(--ease-out)',
                }}
                onMouseEnter={e => { e.currentTarget.style.color = 'var(--primary)'; e.currentTarget.style.borderColor = 'var(--primary)' }}
                onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-secondary)'; e.currentTarget.style.borderColor = 'var(--border-strong)' }}
              >
                {c}
              </button>
            ))}
          </>
        )}
      </div>
    </div>
  )
}

function Chakra() {
  const spokes = Array.from({ length: 24 }, (_, k) =>
    <line key={k} x1="30" y1="30" x2="30" y2="4" transform={`rotate(${k * 15} 30 30)`} stroke="var(--gold)" strokeWidth="2" />
  )
  return (
    <svg width="40" height="40" viewBox="0 0 60 60" fill="none" aria-hidden="true">
      <circle cx="30" cy="30" r="26" stroke="var(--gold)" strokeWidth="2" />
      <circle cx="30" cy="30" r="20" stroke="var(--gold)" strokeWidth="1" opacity="0.6" />
      <circle cx="30" cy="30" r="3.5" fill="var(--gold)" />
      {spokes}
    </svg>
  )
}