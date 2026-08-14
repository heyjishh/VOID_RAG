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

export async function draftDocument(brief) {
  const { data } = await client.post('/draft', { brief })
  // data.content: Markdown string
  return data
}

export async function streamChat(question, conversationId, useWebSearch, callbacks) {
  const { onReasoningStep, onSourceChunk, onAnswerToken, onGate, onVerification, onDone, onError } = callbacks

  const response = await fetch('/api/v1/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      question,
      conversation_id: conversationId,
      use_web_search: useWebSearch,
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
