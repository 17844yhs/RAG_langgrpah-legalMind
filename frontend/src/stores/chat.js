import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getSessions, getMessages, deleteSession, streamSendMessage } from '../api/chat'

export const useChatStore = defineStore('chat', () => {
  const sessions = ref([])
  const currentSessionId = ref(null)
  const messages = ref([])
  const isStreaming = ref(false)
  const abortController = ref(null)

  const currentSession = computed(() =>
    sessions.value.find((s) => s.session_id === currentSessionId.value) || null
  )

  async function loadSessions() {
    try {
      sessions.value = await getSessions()
    } catch {
      // 静默处理
    }
  }

  async function loadMessages(sessionId) {
    currentSessionId.value = sessionId
    messages.value = []
    try {
      messages.value = await getMessages(sessionId)
    } catch {
      // 静默处理
    }
  }

  function newSession() {
    currentSessionId.value = null
    messages.value = []
  }

  async function removeSession(sessionId) {
    try {
      await deleteSession(sessionId)
      sessions.value = sessions.value.filter((s) => s.session_id !== sessionId)
      if (currentSessionId.value === sessionId) {
        newSession()
      }
    } catch {
      // 静默处理
    }
  }

  async function sendMessage(text) {
    if (isStreaming.value) return

    // 添加用户消息
    const userMsg = { role: 'user', content: text }
    messages.value.push(userMsg)

    // 创建占位的 AI 回复
    const aiMsg = { role: 'assistant', content: '', sources: [] }
    messages.value.push(aiMsg)
    const aiIdx = messages.value.length - 1  // 记录 AI 消息在数组中的索引

    isStreaming.value = true

    try {
      const { abort, stream } = streamSendMessage(text, currentSessionId.value)
      abortController.value = abort

      for await (const chunk of stream) {
        if (chunk.done) break
        if (chunk.content !== undefined) {
          messages.value[aiIdx].content += chunk.content  // 通过数组索引访问 Proxy，确保响应式更新
        }
        if (chunk.sources) {
          messages.value[aiIdx].sources = chunk.sources
        }
        if (chunk.session_id) {
          currentSessionId.value = chunk.session_id
          // 刷新会话列表
          if (!sessions.value.find((s) => s.session_id === chunk.session_id)) {
            await loadSessions()
          }
        }
      }
    } catch (e) {
      if (e.name !== 'AbortError') {
        aiMsg.content = '抱歉，消息发送失败，请重试。'
      }
    } finally {
      isStreaming.value = false
      abortController.value = null
    }

    return currentSessionId.value
  }

  function cancelStream() {
    if (abortController.value) {
      abortController.value.abort()
      abortController.value = null
      isStreaming.value = false
    }
  }

  return {
    sessions,
    currentSessionId,
    messages,
    isStreaming,
    currentSession,
    loadSessions,
    loadMessages,
    newSession,
    removeSession,
    sendMessage,
    cancelStream,
  }
})