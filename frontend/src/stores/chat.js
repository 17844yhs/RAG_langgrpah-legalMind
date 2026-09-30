import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { getSessions, getMessages, deleteSession, streamSendMessage, streamResumeMessage, checkPending, streamContinueMessage } from '../api/chat'

export const useChatStore = defineStore('chat', () => {
  const sessions = ref([])
  const currentSessionId = ref(null)
  const messages = ref([])
  const isStreaming = ref(false)
  const abortController = ref(null)
  // Human-in-the-Loop：当图被 interrupt 打断时，存储 interrupt 数据
  const pendingInterrupt = ref(null)
  // 崩溃/断线恢复：会话存在待续跑的图执行（next 非空且非 HITL）时显示「继续生成」按钮
  const canContinue = ref(false)

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
    canContinue.value = false
    try {
      messages.value = await getMessages(sessionId)
    } catch {
      // 静默处理
    }
    // 崩溃恢复探测：进程重启后，中断轮次没落库（历史消息里看不到），
    // 但 checkpoint 里 next 非空——据此显示「继续生成」按钮
    await probePending(sessionId)
  }

  /**
   * 探测会话是否有待恢复的图执行（durable execution）。
   * 两个时机调用：① 加载/切换会话（覆盖进程崩溃重启）② 流式异常断开后（覆盖网络波动）。
   */
  async function probePending(sessionId) {
    if (!sessionId) return
    try {
      const { pending, interrupted } = await checkPending(sessionId)
      // interrupted 场景由 pendingInterrupt（HITL 问答卡片）接管
      canContinue.value = pending && !interrupted
    } catch {
      canContinue.value = false
    }
  }

  function newSession() {
    currentSessionId.value = null
    messages.value = []
    pendingInterrupt.value = null
    canContinue.value = false
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
    let interrupted = false
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
      // token 消耗（本请求所有 LLM 调用归集）
      // interrupt 路径后端也会发 usage，但打断轮次不在气泡上显示 token 行
      if (chunk.usage && !interrupted) {
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
      // 记录后不提前退出：后端 interrupt 后还紧跟 usage/[DONE] 并关闭流，
      // 继续消费到自然结束，fetch 才能正常完成（提前退出会留下
      // 悬挂/中止的连接，Chrome 控制台必现 net::ERR_ABORTED）
      if (chunk.interrupt) {
        interrupted = true
        pendingInterrupt.value = chunk.interrupt
        messages.value[aiIdx].stages = []  // 进度时间线交给 interrupt 问答 UI 接管
      }
    }
    // 流结束：进度时间线完成使命，清掉避免历史残留
    messages.value[aiIdx].stages = []
    if (!interrupted) {
      pendingInterrupt.value = null
    }
    return interrupted
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
      // 网络波动恢复探测：流断了但图可能仍在跑/停在节点边界，
      // 探测到 pending 就显示「继续生成」按钮（图已完成则探测为 false，拉历史即可）
      if (currentSessionId.value) {
        await probePending(currentSessionId.value)
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

  /**
   * 崩溃/断线恢复：点击「继续生成」按钮，从 checkpoint 续跑 pending 节点。
   * 与 resumeInterrupt 的区别：无需用户输入、不追加 user 消息——
   * 中断轮次的内容（已生成的部分 token 不补发，节点边界后续跑）直接写入新气泡。
   */
  async function continueGeneration() {
    if (isStreaming.value) return
    if (!currentSessionId.value || !canContinue.value) return

    // 占位的 AI 回复（续跑从气泡空白处继续，已流出的部分在断线前已渲染）
    const aiMsg = { role: 'assistant', content: '', sources: [], stages: [] }
    messages.value.push(aiMsg)
    const aiIdx = messages.value.length - 1

    canContinue.value = false
    isStreaming.value = true

    try {
      const { abort, stream } = streamContinueMessage(currentSessionId.value)
      abortController.value = abort
      await _consumeStream(stream, aiIdx)
    } catch (e) {
      if (e.name !== 'AbortError') {
        messages.value[aiIdx].content = e.message || '恢复失败，请稍后重试。'
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
    canContinue,
    currentSession,
    loadSessions,
    loadMessages,
    newSession,
    removeSession,
    sendMessage,
    resumeInterrupt,
    continueGeneration,
    cancelStream,
  }
})
