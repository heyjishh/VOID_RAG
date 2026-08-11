// Heuristic follow-up generator — derives suggestions from the response's own
// metadata (intent, cited sources, verification) rather than a static list.
// A `/chat/followups` endpoint that asks the model directly would read the
// answer itself and produce sharper, less templated suggestions (see report).
const INTENT_TEMPLATES = {
  legal: [
    'Are there any exceptions to this?',
    'Have there been recent amendments affecting this?',
  ],
  web: [
    'What are the most recent developments on this?',
    'Has this changed since the last update?',
  ],
  both: [
    'How does this compare with the current legal position?',
    'Are there any recent amendments affecting this?',
  ],
}

export function deriveFollowups(message) {
  const intent = message?.intent && INTENT_TEMPLATES[message.intent] ? message.intent : 'legal'
  const suggestions = [...INTENT_TEMPLATES[intent]]

  const sources = message?.source_chunks || []
  const titles = [...new Set(
    sources.map(s => s.title || s.source?.split('/').pop()).filter(Boolean)
  )].slice(0, 1)
  titles.forEach(title => suggestions.push(`What else does ${title} say on this?`))

  const unsupported = message?.verification?.unsupported_claims || []
  if (unsupported.length > 0) {
    suggestions.push(`Can you verify: "${unsupported[0]}"?`)
  }

  return [...new Set(suggestions)].slice(0, 4)
}
