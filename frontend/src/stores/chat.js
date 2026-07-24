import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getSessions, getMessages, deleteSession, streamSendMessage, streamResumeMessage } from '../api/chat'

export const useChatStore = defineStore('chat', () => {
  const sessions = ref([])
  const currentSessionId = ref(null)
  const messages = ref([])
  const isStreaming = ref(false)
  const abortController = ref(null)
  // Human-in-the-Loop：当图被 interrupt 打断时，存储 interrupt 数据
  const pendingInterrupt = ref(null)

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
    pendingInterrupt.value = null
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

  /**
   * 消费 SSE 流的通用逻辑：处理 content / sources / interrupt / session_id
   * @param {AsyncIterable} stream - SSE 流
   * @param {number} aiIdx - AI 消息在 messages 数组中的索引
   * @returns {Promise<boolean>} - 是否被 interrupt 打断
   */
  async function _consumeStream(stream, aiIdx) {
    for await (const chunk of stream) {
      if (chunk.done) break

      if (chunk.content !== undefined) {
        messages.value[aiIdx].content += chunk.content
      }
      if (chunk.sources) {
        messages.value[aiIdx].sources = chunk.sources
      }
      if (chunk.session_id) {
        currentSessionId.value = chunk.session_id
        if (!sessions.value.find((s) => s.session_id === chunk.session_id)) {
          await loadSessions()
        }
      }
      // ── Human-in-the-Loop：检测到 interrupt ──
      if (chunk.interrupt) {
        pendingInterrupt.value = chunk.interrupt
        return true  // 被打断，停止消费
      }
    }
    // 流正常结束，清除 interrupt 状态
    pendingInterrupt.value = null
    return false
  }

  async function sendMessage(text) {
    if (isStreaming.value) return

    // 清除之前的 interrupt 状态
    pendingInterrupt.value = null

    // 添加用户消息
    const userMsg = { role: 'user', content: text }
    messages.value.push(userMsg)

    // 创建占位的 AI 回复
    const aiMsg = { role: 'assistant', content: '', sources: [] }
    messages.value.push(aiMsg)
    const aiIdx = messages.value.length - 1

    isStreaming.value = true

    try {
      const { abort, stream } = streamSendMessage(text, currentSessionId.value)
      abortController.value = abort
      await _consumeStream(stream, aiIdx)
    } catch (e) {
      if (e.name !== 'AbortError') {
        messages.value[aiIdx].content = '抱歉，消息发送失败，请重试。'
      }
    } finally {
      isStreaming.value = false
      abortController.value = null
    }

    return currentSessionId.value
  }

  /**
   * 恢复被 interrupt 打断的图执行。
   * 用户回答了 interrupt 问题后调用。
   */
  async function resumeInterrupt(userResponse) {
    if (isStreaming.value) return
    if (!currentSessionId.value) return

    // 添加用户的回答作为消息
    const userMsg = { role: 'user', content: userResponse }
    messages.value.push(userMsg)

    // 创建占位的 AI 回复
    const aiMsg = { role: 'assistant', content: '', sources: [] }
    messages.value.push(aiMsg)
    const aiIdx = messages.value.length - 1

    // 清除当前 interrupt，准备处理流（可能触发下一个 interrupt）
    pendingInterrupt.value = null
    isStreaming.value = true

    try {
      const { abort, stream } = streamResumeMessage(currentSessionId.value, userResponse)
      abortController.value = abort
      await _consumeStream(stream, aiIdx)
    } catch (e) {
      if (e.name !== 'AbortError') {
        messages.value[aiIdx].content = '抱歉，处理出错，请重试。'
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
      pendingInterrupt.value = null
    }
  }

  return {
    sessions,
    currentSessionId,
    messages,
    isStreaming,
    pendingInterrupt,
    currentSession,
    loadSessions,
    loadMessages,
    newSession,
    removeSession,
    sendMessage,
    resumeInterrupt,
    cancelStream,
  }
})
