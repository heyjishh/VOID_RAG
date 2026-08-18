import { useState, useEffect } from 'react'

// Tracks a CSS media query in React state — used to switch layout structure
// (push-panel vs. slide-over overlay) at breakpoints Tailwind's className
// system can't reach, because those panels animate via an inline `width`
// style, not a class.
export function useMediaQuery(query) {
  const [matches, setMatches] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia(query).matches : false
  )

  useEffect(() => {
    const mql = window.matchMedia(query)
    const handler = e => setMatches(e.matches)
    setMatches(mql.matches)
    mql.addEventListener('change', handler)
    return () => mql.removeEventListener('change', handler)
  }, [query])

  return matches
}
