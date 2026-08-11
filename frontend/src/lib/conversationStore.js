const STORAGE_KEY = 'juryai.conversations.v1'
const MAX_STORED = 60
const TITLE_MAX_LEN = 64

function readAll() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function writeAll(list) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list.slice(0, MAX_STORED)))
  } catch {
    // Storage unavailable/full — history simply won't persist past this tab.
  }
}

export function deriveTitle(firstQuestion) {
  const trimmed = (firstQuestion || '').trim()
  if (!trimmed) return 'New conversation'
  return trimmed.length > TITLE_MAX_LEN ? `${trimmed.slice(0, TITLE_MAX_LEN - 1)}…` : trimmed
}

export function listConversations() {
  return readAll().sort((a, b) => b.updatedAt - a.updatedAt)
}

export function getConversation(id) {
  if (!id) return null
  return readAll().find(c => c.id === id) || null
}

export function upsertConversation(conversation) {
  if (!conversation?.id) return null
  const all = readAll()
  const idx = all.findIndex(c => c.id === conversation.id)
  const next = { ...conversation, updatedAt: Date.now() }
  if (idx === -1) all.unshift(next)
  else all[idx] = next
  writeAll(all)
  return next
}

export function deleteConversation(id) {
  writeAll(readAll().filter(c => c.id !== id))
}
