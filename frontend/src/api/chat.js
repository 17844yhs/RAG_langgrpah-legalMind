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
 * 事件类型：{ content } | { sources } | { interrupt } | { error } | { done: true }
 */
function parseSSEStream(response, controller) {
  async function* generate() {
    if (!response.ok) {
      // 流式端点在响应头阶段就失败：解析 RFC 9457 错误体
      const err = new Error(`HTTP ${response.status}`)
      try {
        const body = await response.json()
        err.code = body.code        // 业务错误码，如 AUTH_001
        err.traceId = body.traceId  // 报障凭据
        if (body.detail) err.message = body.detail
      } catch { /* 非 JSON 响应保持默认消息 */ }
      throw err
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    try {
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
    } finally {
      // 消费端提前退出（收到 interrupt 提前 return / 收到 error 事件 break）时，
      // 把剩余响应体读完让 fetch 自然完成——后端发完 interrupt/error 后紧跟
      // [DONE] 并关闭流，剩余只有几十字节。
      // 不能用 controller.abort()：abort 本身会被 Chrome 记为 net::ERR_ABORTED；
      // 也不能不读直接退出：悬挂连接要等 GC 回收时才报同样的错。
      try {
        while (!(await reader.read()).done) { /* 丢弃剩余字节 */ }
      } catch { /* 连接已断开等异常场景，忽略 */ }
    }
  }

  return { abort: () => controller.abort(), stream: generate() }
}

/**
 * 流式发送新消息
 * POST /api/v1/chat/stream
 */
export function streamSendMessage(message, sessionId) {
  const controller = new AbortController()

  const response = fetch('/api/v1/chat/stream', {
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
 * POST /api/v1/chat/resume
 * 同样返回 SSE 流（因为 resume 后可能触发下一个 interrupt）
 */
export function streamResumeMessage(sessionId, userResponse) {
  const controller = new AbortController()

  const response = fetch('/api/v1/chat/resume', {
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
