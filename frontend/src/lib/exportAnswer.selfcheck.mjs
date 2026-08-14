// Runnable self-check for exportAnswer's pure string logic. No test runner is
// installed, so this loads the sibling ESM module's bytes as a data: URL (the
// frontend package.json isn't type:module, so node would otherwise treat the
// .js as CommonJS) and asserts. Run: node src/lib/exportAnswer.selfcheck.mjs
import { readFileSync } from 'node:fs'
import assert from 'node:assert/strict'

const src = readFileSync(new URL('./exportAnswer.js', import.meta.url), 'utf8')
const { stripCitations, buildSourcesList, answerToMarkdown } = await import(
  'data:text/javascript;base64,' + Buffer.from(src).toString('base64')
)

// stripCitations collapses the space before a marker, keeps punctuation.
assert.equal(stripCitations('The court held X [1]. See also Y [12].'), 'The court held X. See also Y.')
assert.equal(stripCitations('No markers here.'), 'No markers here.')
assert.equal(stripCitations(''), '')
assert.equal(stripCitations(null), '')

const cites = [
  { source: 'corpus/ruling.pdf', page: 4, index: 1 },
  { source: 'brief.pdf', page: 0, index: 2 },
  { source: 'nopage.txt', page: null, index: 3 },
]

// Sources list: filename only, page +1, 1-based index, null page omitted.
assert.equal(
  buildSourcesList(cites),
  '[1] ruling.pdf — p.5\n[2] brief.pdf — p.1\n[3] nopage.txt'
)
assert.equal(buildSourcesList([]), '')

// Legacy citations (index 0) fall back to array position.
assert.equal(buildSourcesList([{ source: 'a.pdf', page: 2 }]), '[1] a.pdf — p.3')

// With citations: markers preserved, Sources section appended.
const withCite = answerToMarkdown('Held X [1].', cites, { withCitations: true })
assert.match(withCite, /Held X \[1\]\./)
assert.match(withCite, /## Sources/)
assert.match(withCite, /\[1\] ruling\.pdf — p\.5/)

// Without citations: markers stripped, no Sources section.
const clean = answerToMarkdown('Held X [1].', cites, { withCitations: false })
assert.equal(clean, 'Held X.\n')
assert.doesNotMatch(clean, /Sources/)

// No citations + withCitations still yields clean body, no dangling Sources.
assert.equal(answerToMarkdown('Plain.', [], { withCitations: true }), 'Plain.\n')

console.log('exportAnswer self-check: all assertions passed')
