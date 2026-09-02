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
      // 质量自检重试：第一版草稿作废，清空气泡等修正版从零重写
      if (chunk.revision) {
        messages.value[aiIdx].content = ''
      }
      if (chunk.sources) {
        messages.value[aiIdx].sources = chunk.sources
      }
      // 回答元数据（结论/风险等级/法条）— 流结束后到达，渲染为答案卡片
      if (chunk.meta) {
        messages.value[aiIdx].meta = chunk.meta
      }
      // token 消耗（本请求所有 LLM 调用归集，interrupt 打断的对话也会发）
      if (chunk.usage) {
        messages.value[aiIdx].usage = chunk.usage
      }
      // 分阶段进度事件（意图识别/检索/生成），累积成步骤时间线：
      // 同名 stage 就地更新（running→done），保持顺序不重复
      if (chunk.stage) {
        const list = messages.value[aiIdx].stages || (messages.value[aiIdx].stages = [])
        const idx = list.findIndex((s) => s.stage === chunk.stage.stage)
        if (idx >= 0) list[idx] = chunk.stage
        else list.push(chunk.stage)
      }
      if (chunk.session_id) {
        currentSessionId.value = chunk.session_id
        if (!sessions.value.find((s) => s.session_id === chunk.session_id)) {
          await loadSessions()
        }
      }
      // ── SSE 错误事件：展示后端统一错误文案 ──
      if (chunk.error) {
        messages.value[aiIdx].content = chunk.error.detail || '服务暂时不可用，请稍后重试'
        break
      }
      // ── Human-in-the-Loop：检测到 interrupt ──
      if (chunk.interrupt) {
        pendingInterrupt.value = chunk.interrupt
        messages.value[aiIdx].stages = []  // 进度时间线交给 interrupt 问答 UI 接管
        return true  // 被打断，停止消费
      }
    }
    // 流正常结束：进度时间线完成使命，清掉避免历史残留
    messages.value[aiIdx].stages = []
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

    // 创建占位的 AI 回复（stages：分阶段进度时间线）
    const aiMsg = { role: 'assistant', content: '', sources: [], stages: [] }
    messages.value.push(aiMsg)
    const aiIdx = messages.value.length - 1

    isStreaming.value = true

    try {
      const { abort, stream } = streamSendMessage(text, currentSessionId.value)
      abortController.value = abort
      await _consumeStream(stream, aiIdx)
    } catch (e) {
      if (e.name !== 'AbortError') {
        // e.message 来自后端 problem+json 的 detail（流式端点为解析后的错误体）
        messages.value[aiIdx].content = e.message || '抱歉，消息发送失败，请重试。'
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

    // 创建占位的 AI 回复（stages：分阶段进度时间线）
    const aiMsg = { role: 'assistant', content: '', sources: [], stages: [] }
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
