// Client-side heuristic refinement — expands common Indian legal shorthand and
// nudges under-specified drafts toward a structured ask. This is an honest
// approximation, not an LLM call: a `/chat/refine` endpoint that rewrites the
// draft with real language understanding would produce meaningfully better
// results (see report). Registry-driven so new shorthand is a data row, not
// a new branch.
const EXPANSIONS = [
  [/\bu\/s\b/gi, 'under Section'],
  [/\bipc\b/gi, 'the Indian Penal Code (IPC)'],
  [/\bcrpc\b/gi, 'the Code of Criminal Procedure (CrPC)'],
  [/\bcpc\b/gi, 'the Code of Civil Procedure (CPC)'],
  [/\bfir\b/gi, 'a First Information Report (FIR)'],
  [/\bpil\b/gi, 'a Public Interest Litigation (PIL)'],
  [/\bslp\b/gi, 'a Special Leave Petition (SLP)'],
  [/\bsc\b/gi, 'the Supreme Court'],
  [/\bhc\b/gi, 'the High Court'],
  [/\bart\.?\s+(\d+[a-z]?)/gi, 'Article $1'],
  [/\bsec\.?\s+(\d+[a-z]?)/gi, 'Section $1'],
]

const STRUCTURE_HINT = ' Explain with the relevant statutory provisions and any leading case law.'

export function refineDraft(text) {
  const trimmed = (text || '').trim()
  if (!trimmed) return trimmed

  let refined = trimmed
  for (const [pattern, replacement] of EXPANSIONS) {
    refined = refined.replace(pattern, replacement)
  }

  if (!/[.?!]$/.test(refined)) refined += '?'
  if (refined.split(/\s+/).length < 8) refined += STRUCTURE_HINT

  return refined
}
