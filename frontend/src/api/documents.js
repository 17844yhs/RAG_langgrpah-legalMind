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

    if (!response.ok) throw new Error(`HTTP ${response.status}`)

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