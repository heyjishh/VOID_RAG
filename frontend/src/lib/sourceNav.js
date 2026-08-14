import { prefersReducedMotion } from './motion.js'

// Bridge between a citation marker (in a chat answer or the CitationStrip) and
// the matching SourceCard in the SourcePanel. Both live in far-apart component
// trees around a single shared panel, so we address the card by DOM rather than
// threading a callback through App — the card is tagged with data-source-index
// (= its retrieval rank, the same 0-based index citations[] uses).
//
// ponytail: DOM-addressed, single-panel scope. The panel shows only the latest
// turn's sources, so clicking a citation in an older message scrolls the current
// panel — inherent to the one-panel design, not handled here.
export function scrollToSource(index) {
  const card = document.querySelector(`[data-source-index="${index}"]`)
  if (!card) return

  card.scrollIntoView({
    behavior: prefersReducedMotion() ? 'auto' : 'smooth',
    block: 'center',
  })

  // Brief flash so the eye lands on the right card after the scroll.
  card.classList.remove('source-card-flash')
  // Force reflow so re-adding the class restarts the animation on repeat clicks.
  void card.offsetWidth
  card.classList.add('source-card-flash')
  card.addEventListener(
    'animationend',
    () => card.classList.remove('source-card-flash'),
    { once: true },
  )
}
