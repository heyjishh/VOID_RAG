import axios from 'axios'

export const API_BASE = '/api/v1'

const client = axios.create({ baseURL: API_BASE, timeout: 60000 })

// Attach the server auth token to every call when a session exists.
client.interceptors.request.use(config => {
  try {
    const token = localStorage.getItem('juryai.token')
    if (token) config.headers.Authorization = `Bearer ${token}`
  } catch (e) {}
  return config
})

function authError(err) {
  const detail =
    err?.response?.data?.detail ||
    (Array.isArray(err?.response?.data?.detail)
      ? err.response.data.detail.map(d => d.msg).join(' · ')
      : undefined)
  const message =
    typeof detail === 'string'
      ? detail
      : err?.message === 'Network Error'
        ? 'Cannot reach the research server. It may be offline.'
        : err?.response?.status
          ? `Request failed (${err.response.status}).`
          : 'Something went wrong. Please try again.'
  const e = new Error(message)
  e.status = err?.response?.status
  throw e
}

export const authApi = {
  async sendOtp(payload) {
    try {
      const { data } = await client.post('/auth/otp/send', payload)
      return data
    } catch (err) {
      throw authError(err)
    }
  },
  async verifyOtp(payload) {
    try {
      const { data } = await client.post('/auth/otp/verify', payload)
      return data
    } catch (err) {
      throw authError(err)
    }
  },
  async register(payload) {
    try {
      const { data } = await client.post('/auth/register', payload)
      return data
    } catch (err) {
      throw authError(err)
    }
  },
  async login(payload) {
    try {
      const { data } = await client.post('/auth/login', payload)
      return data
    } catch (err) {
      throw authError(err)
    }
  },
  async forgot(payload) {
    try {
      const { data } = await client.post('/auth/forgot', payload)
      return data
    } catch (err) {
      throw authError(err)
    }
  },
  async reset(payload) {
    try {
      const { data } = await client.post('/auth/reset', payload)
      return data
    } catch (err) {
      throw authError(err)
    }
  },
  async logout(token) {
    try {
      await client.post('/auth/logout', {}, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
    } catch (e) {
      // Best-effort server-side revoke; clearing local state is what matters.
    }
  },
}

export async function sendChat(question, conversationId = null) {
  const { data } = await client.post('/chat', { question, conversation_id: conversationId })
  // data.source_chunks: [{text, source, page, score, verified}]
  return data
}

export async function draftDocument(payload) {
  const { data } = await client.post('/draft', payload)
  return data
}

export async function streamDraft(payload, callbacks) {
  const { onReasoningStep, onSourceChunk, onDraftToken, onDone, onError } = callbacks

  const headers = { 'Content-Type': 'application/json' }
  const token = localStorage.getItem('juryai.token')
  if (token) headers.Authorization = `Bearer ${token}`

  const response = await fetch('/api/v1/draft/stream', {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  })

  if (!response.ok) {
    onError?.(new Error(`HTTP ${response.status}`))
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    const parts = buffer.split('\n\n')
    buffer = parts.pop()

    for (const part of parts) {
      const lines = part.trim().split('\n')
      let eventType = 'message'
      let dataStr = ''

      for (const line of lines) {
        if (line.startsWith('event: ')) eventType = line.slice(7).trim()
        if (line.startsWith('data: ')) dataStr = line.slice(6).trim()
      }

      if (!dataStr) continue

      try {
        const data = JSON.parse(dataStr)
        if (eventType === 'reasoning_step') onReasoningStep?.(data)
        else if (eventType === 'source_chunk') onSourceChunk?.(data)
        else if (eventType === 'draft_token') onDraftToken?.(data)
        else if (eventType === 'done') {
          onDone?.(data)
          return
        } else if (eventType === 'error') {
          onError?.(new Error(data.detail || 'Stream error'))
        }
      } catch {
        // Ignore malformed events
      }
    }
  }
}

export async function uploadDraftDocument(sessionId, file) {
  const formData = new FormData()
  formData.append('session_id', sessionId)
  formData.append('file', file)
  const { data } = await client.post('/interact/documents', formData)
  // data.document: {file_hash, filename, chunk_count, duplicate}
  return data.document
}

export async function getRecentDrafts(page = 1, pageSize = 20) {
  const { data } = await client.get('/draft/recent', { params: { page, page_size: pageSize } })
  // DraftRunOut[] or {items, total} — normalize both shapes
  return Array.isArray(data) ? data : data.items || []
}

export async function streamChat(question, conversationId, useWebSearch, callbacks, outputFormat = 'CREAC', sources = null, mode = 'ask', sessionId = null) {
  const { onReasoningStep, onSourceChunk, onAnswerToken, onGate, onVerification, onDone, onError } = callbacks

  const chatHeaders = { 'Content-Type': 'application/json' }
  const chatToken = localStorage.getItem('juryai.token')
  if (chatToken) chatHeaders.Authorization = `Bearer ${chatToken}`

  const response = await fetch('/api/v1/chat/stream', {
    method: 'POST',
    headers: chatHeaders,
    body: JSON.stringify({
      question,
      conversation_id: conversationId,
      use_web_search: useWebSearch,
      output_format: outputFormat,
      // Filenames from listDocuments() to scope retrieval to; null/empty
      // searches the full corpus.
      sources: sources && sources.length ? sources : null,
      mode,
      session_id: sessionId,
    }),
  })

  if (!response.ok) {
    onError?.(new Error(`HTTP ${response.status}`))
    return
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    // Parse SSE chunks from buffer — events are separated by double newline
    const parts = buffer.split('\n\n')
    buffer = parts.pop() // keep the last (possibly incomplete) chunk

    for (const part of parts) {
      const lines = part.trim().split('\n')
      let eventType = 'message'
      let dataStr = ''

      for (const line of lines) {
        if (line.startsWith('event: ')) eventType = line.slice(7).trim()
        if (line.startsWith('data: ')) dataStr = line.slice(6).trim()
      }

      if (!dataStr) continue

      try {
        const data = JSON.parse(dataStr)
        if (eventType === 'reasoning_step') onReasoningStep?.(data)
        else if (eventType === 'source_chunk') onSourceChunk?.(data)
        else if (eventType === 'answer_token') onAnswerToken?.(data)
        else if (eventType === 'gate') onGate?.(data)
        else if (eventType === 'verification') onVerification?.(data)
        else if (eventType === 'done') {
          onDone?.(data)
          return
        }
      } catch {
        // Ignore parse errors for malformed events
      }
    }
  }
}

export async function triggerIngest(prefixFilter = '', syncOnly = true) {
  const { data } = await client.post('/ingest/s3', {
    prefix_filter: prefixFilter,
    sync_only: syncOnly,
  })
  return data
}

export async function getSyncStatus() {
  const { data } = await client.get('/ingest/status')
  // {total_on_s3, ingested, pending, pending_keys, error}
  return data
}

export async function getLegalNews() {
  const { data } = await client.get('/news/legal')
  // [{title, link, published, summary}, ...]
  return data
}

export async function getRun(runId) {
  const { data } = await client.get(`/runs/${encodeURIComponent(runId)}`)
  return data
}

export async function followUpRun(runId, question, useWebSearch = false) {
  const { data } = await client.post(`/runs/${encodeURIComponent(runId)}/followup`, {
    question,
    use_web_search: useWebSearch,
  })
  return data
}

export async function sourceAction(runId, sourceIndex, action = 'view') {
  const { data } = await client.post(`/runs/${encodeURIComponent(runId)}/sources/${encodeURIComponent(sourceIndex)}/actions`, {
    action,
  })
  return data
}

export async function getRunSource(runId, sourceIndex) {
  const { data } = await client.get(`/runs/${encodeURIComponent(runId)}/source/${encodeURIComponent(sourceIndex)}`)
  return data
}

export async function getRunSourceFile(runId, sourceIndex) {
  const { data } = await client.get(`/runs/${encodeURIComponent(runId)}/source/${encodeURIComponent(sourceIndex)}/file`, { responseType: 'text' })
  return { content: data }
}

export async function downloadRunPdf(runId) {
  const { data } = await client.post(`/runs/${encodeURIComponent(runId)}/download`, {}, { responseType: 'blob' })
  return data
}

export async function analyzeQuestion(question) {
  const { data } = await client.post('/chat/analyze', { question })
  return data
}

export async function improveQuestion(question) {
  const { data } = await client.post('/chat/improve', { question })
  return data
}

export async function listConversations(userId) {
  const { data } = await client.get('/conversations', { params: { user_id: userId } })
  return data
}

export async function createConversation(payload) {
  const { data } = await client.post('/conversations', payload)
  return data
}

export async function updateConversation(conversationId, payload) {
  const { data } = await client.patch(`/conversations/${encodeURIComponent(conversationId)}`, payload)
  return data
}

export async function deleteConversation(conversationId) {
  const { data } = await client.delete(`/conversations/${encodeURIComponent(conversationId)}`)
  return data
}

export async function listDocuments(prefix = '', limit = 100, offset = 0) {
  const { data } = await client.get('/documents', { params: { prefix, limit, offset } })
  return data
}

export async function listDocumentFolders() {
  const { data } = await client.get('/documents/folders')
  // {folders: [{bucket, folder, prefix, count}]}
  return data
}

export async function getLlmStatus() {
  const { data } = await client.get('/llm/status')
  // {provider, model, base_url, configured}
  return data
}

export async function scheduleIngest() {
  const { data } = await client.post('/ingest/s3/schedule')
  return data
}

export async function unscheduleIngest() {
  const { data } = await client.post('/ingest/s3/unschedule')
  return data
}

export async function getSchedulerStatus() {
  const { data } = await client.get('/ingest/s3/status')
  return data
}

export const interactApi = {
  async uploadDocument(sessionId, file) {
    const formData = new FormData()
    formData.append('session_id', sessionId)
    formData.append('file', file)
    const { data } = await client.post('/interact/documents', formData)
    // data.document: {file_hash, filename, chunk_count, duplicate}
    return data
  },
  async listDocuments(sessionId) {
    const { data } = await client.get('/interact/documents', { params: { session_id: sessionId } })
    // data.documents: [...]
    return data
  },
  async deleteDocument(sessionId, fileHash) {
    await client.delete(`/interact/documents/${fileHash}`, { params: { session_id: sessionId } })
  },
  async reuseDocument(sessionId, sourceSessionId, fileHash) {
    const { data } = await client.post('/interact/documents/reuse', {
      session_id: sessionId,
      source_session_id: sourceSessionId,
      file_hash: fileHash,
    })
    return data
  },
}
