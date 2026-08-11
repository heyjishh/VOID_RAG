// Config-driven prompt/skill registry. Add a new template by appending a row —
// both the composer's Prompt Library popover and the Settings Skills list
// render from this single array, so no branching UI code is needed per item.
export const PROMPT_LIBRARY = [
  {
    id: 'summarize-judgment',
    skill: 'Summarize',
    label: 'Summarize a judgment',
    template: 'Summarize the key holding, reasoning, and precedent value of [case name or citation].',
  },
  {
    id: 'find-precedents',
    skill: 'Find precedents',
    label: 'Find precedents on a point of law',
    template: 'Find leading precedents on [legal issue], with citations and how courts have applied them.',
  },
  {
    id: 'section-analysis',
    skill: 'Draft analysis',
    label: 'Draft a Section 80C analysis',
    template: 'Draft an analysis of Section 80C of the Income Tax Act — scope, eligible deductions, and limits.',
  },
  {
    id: 'explain-provision',
    skill: 'Explain a provision',
    label: 'Explain a bare act provision',
    template: 'Explain [Section X of the Y Act] in plain language, including the punishment or consequence and any exceptions.',
  },
  {
    id: 'compare-provisions',
    skill: 'Compare provisions',
    label: 'Compare two provisions',
    template: 'Compare [Provision A] with [Provision B] — key differences, and when each applies.',
  },
  {
    id: 'draft-notice',
    skill: 'Draft a notice',
    label: 'Draft a legal notice',
    template: 'Draft a legal notice regarding [dispute], citing the relevant statutory provisions.',
  },
]
