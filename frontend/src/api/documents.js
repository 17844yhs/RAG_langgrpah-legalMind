import client from './client'

export async function getTemplates() {
  const { data } = await client.get('/documents/templates')
  return data.templates
}

/**
 * 流式生成文书
 */
export function streamGenerateDocument(documentType, query, params, useReferences = true) {
  const controller = new AbortController()

  async function* generate() {
    const response = await fetch('/api/documents/generate/stream', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem('token')}`,
      },
      body: JSON.stringify({ document_type: documentType, query, params, use_references: useReferences }),
      signal: controller.signal,
    })

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
          const parsed = JSON.parse(payload)
          yield parsed
        } catch { /* ignore */ }
      }
    }
  }

  return { abort: () => controller.abort(), stream: generate() }
}