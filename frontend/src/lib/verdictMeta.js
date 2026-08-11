// Single source of truth for the backend's three verdict strings
// (app/core/graph/verifier.py::_verdict_from_score). Shared by VerificationBadge
// (per-answer) and SourcePanel's retrieval summary (per-turn aggregate) so the
// same claim-level signal always reads the same color/label everywhere it appears.
export const VERDICT_META = {
  grounded: {
    color: 'var(--sage)',
    bg: 'var(--sage-light)',
    border: 'var(--sage-border)',
    label: 'Grounded',
  },
  partially_grounded: {
    color: 'var(--accent-yellow)',
    bg: 'var(--gold-light)',
    border: 'var(--gold-border)',
    label: 'Partially grounded',
  },
  unsupported: {
    color: 'var(--color-error)',
    bg: 'var(--color-error-bg)',
    border: 'var(--color-error-border)',
    label: 'Unsupported',
  },
}

export function verdictMeta(verdict) {
  return VERDICT_META[verdict] || VERDICT_META.unsupported
}
