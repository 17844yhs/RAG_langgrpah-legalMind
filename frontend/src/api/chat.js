import client from './client'

export async function getSessions() {
  const { data } = await client.get('/chat/sessions')
  return data.sessions
}

export async function getMessages(sessionId, limit = 50) {
  const { data } = await client.get(`/chat/sessions/${sessionId}/messages`, { params: { limit } })
  return data.messages
}

export async function deleteSession(sessionId) {
  const { data } = await client.delete(`/chat/sessions/${sessionId}`)
  return data
}

/**
 * 流式发送消息
 * 返回一个对象 { abort, stream }
 * stream 是一个 AsyncGenerator，yield { content: string } 或 { sources: [...] } 或 { done: true }
 */
export function streamSendMessage(message, sessionId) {
  const controller = new AbortController()

  async function* generate() {
    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem('token')}`,
      },
      body: JSON.stringify({ message, session_id: sessionId || null }),
      signal: controller.signal,
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || '' // 保留未完成的行

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed || !trimmed.startsWith('data: ')) continue
        const payload = trimmed.slice(6)
        if (payload === '[DONE]') {
          yield { done: true }
          return
        }
        try {
          const parsed = JSON.parse(payload)
          yield parsed
        } catch {
          // 忽略无法解析的数据
        }
      }
    }
  }

  return { abort: () => controller.abort(), stream: generate() }
}