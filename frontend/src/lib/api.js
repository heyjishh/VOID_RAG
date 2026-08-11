import axios from 'axios'

export const API_BASE = '/api/v1'

const client = axios.create({ baseURL: API_BASE, timeout: 60000 })

export async function sendChat(question, conversationId = null) {
  const { data } = await client.post('/chat', { question, conversation_id: conversationId })
  // data.source_chunks: [{text, source, page, score, verified}]
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
