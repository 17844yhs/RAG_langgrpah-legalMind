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
 * 解析 SSE 流，yield 结构化事件
 * 事件类型：{ content: string } | { sources: [...] } | { interrupt: {...} } | { done: true }
 */
function parseSSEStream(response, controller) {
  async function* generate() {
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
      buffer = lines.pop() || ''

      for (const line of lines) {
        const trimmed = line.trim()
        if (!trimmed || !trimmed.startsWith('data: ')) continue
        const payload = trimmed.slice(6)
        if (payload === '[DONE]') {
          yield { done: true }
          return
        }
        try {
          yield JSON.parse(payload)
        } catch {
          // 忽略无法解析的数据
        }
      }
    }
  }

  return { abort: () => controller.abort(), stream: generate() }
}

/**
 * 流式发送新消息
 * POST /api/chat/stream
 */
export function streamSendMessage(message, sessionId) {
  const controller = new AbortController()

  const response = fetch('/api/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${localStorage.getItem('token')}`,
    },
    body: JSON.stringify({ message, session_id: sessionId || null }),
    signal: controller.signal,
  })

  // 注意：fetch 返回 Promise<Response>，需要在 generate 里 await
  async function* wrappedGenerate() {
    const res = await response
    const parsed = parseSSEStream(res, controller)
    yield* parsed.stream
  }

  return { abort: () => controller.abort(), stream: wrappedGenerate() }
}

/**
 * 恢复被 interrupt 打断的图执行
 * POST /api/chat/resume
 * 同样返回 SSE 流（因为 resume 后可能触发下一个 interrupt）
 */
export function streamResumeMessage(sessionId, userResponse) {
  const controller = new AbortController()

  const response = fetch('/api/chat/resume', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${localStorage.getItem('token')}`,
    },
    body: JSON.stringify({ session_id: sessionId, response: userResponse }),
    signal: controller.signal,
  })

  async function* wrappedGenerate() {
    const res = await response
    const parsed = parseSSEStream(res, controller)
    yield* parsed.stream
  }

  return { abort: () => controller.abort(), stream: wrappedGenerate() }
}
