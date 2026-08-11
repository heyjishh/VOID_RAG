// Honest connector registry — only sources that genuinely feed this session.
// Do not add a placeholder connector here without wiring it end to end.
export const CONNECTORS = [
  {
    id: 'corpus',
    name: 'Internal Legal Corpus',
    description: 'Statutes, judgments, and legal documents ingested from the synced corpus.',
    kind: 'corpus',
    alwaysOn: true,
  },
  {
    id: 'web',
    name: 'Web Search',
    description: 'Live web results for current events and recent developments.',
    kind: 'web',
    alwaysOn: false,
  },
]
