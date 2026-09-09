<script setup>
import { ref, computed } from 'vue'
import { useChatStore } from '../../stores/chat'

const chat = useChatStore()

function selectSession(sessionId) {
  chat.loadMessages(sessionId)
}

// 删除确认：主题化模态框（替代原生 confirm，与整体风格一致）
const deletingId = ref(null)
const deletingTitle = computed(() => {
  const s = chat.sessions.find((x) => x.session_id === deletingId.value)
  return s?.title || '新对话'
})

function askDelete(sessionId, e) {
  e.stopPropagation()
  deletingId.value = sessionId
}

function cancelDelete() {
  deletingId.value = null
}

function doDelete() {
  if (deletingId.value) chat.removeSession(deletingId.value)
  deletingId.value = null
}
</script>

<template>
  <div class="w-72 border-r flex flex-col h-full" :style="{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)' }">
    <!-- 新建对话按钮 -->
    <div class="p-3">
      <button
        @click="chat.newSession()"
        class="w-full py-2 px-3 rounded-lg text-sm font-medium text-white transition-opacity cursor-pointer"
        :style="{ backgroundColor: 'var(--primary)' }"
      >
        + 新建对话
      </button>
    </div>

    <!-- 会话列表 -->
    <div class="flex-1 overflow-y-auto px-2 pb-2">
      <div
        v-for="s in chat.sessions"
        :key="s.session_id"
        @click="selectSession(s.session_id)"
        class="flex items-center justify-between px-3 py-2.5 rounded-lg mb-1 cursor-pointer text-sm transition-colors group"
        :style="{
          backgroundColor: chat.currentSessionId === s.session_id ? 'var(--border)' : 'transparent',
          color: 'var(--text)',
        }"
      >
        <span class="truncate flex-1">{{ s.title || '新对话' }}</span>
        <button
          @click="askDelete(s.session_id, $event)"
          class="session-delete opacity-0 group-hover:opacity-100 text-xs px-1.5 py-0.5 rounded transition-all cursor-pointer"
          title="删除"
        >
          ✕
        </button>
      </div>
      <div v-if="chat.sessions.length === 0" class="text-sm text-center py-8" :style="{ color: 'var(--text-secondary)' }">
        暂无会话记录
      </div>
    </div>

    <!-- 删除确认模态框（Teleport 到 body，遮罩 + 主题卡片） -->
    <Teleport to="body">
      <Transition name="modal-fade">
        <div
          v-if="deletingId"
          class="fixed inset-0 z-[100] flex items-center justify-center p-4"
          style="background: rgba(0, 0, 0, 0.55); backdrop-filter: blur(2px)"
          @click.self="cancelDelete"
        >
          <div
            class="w-full max-w-sm rounded-2xl border p-5"
            :style="{
              backgroundColor: 'var(--bg-secondary)',
              borderColor: 'var(--border)',
              boxShadow: 'var(--shadow-lg)',
            }"
          >
            <div class="flex items-center gap-3 mb-3">
              <span
                class="w-9 h-9 rounded-full flex items-center justify-center flex-shrink-0"
                style="background: rgba(239, 68, 68, 0.12); color: #ef4444"
              >
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" class="w-4.5 h-4.5" width="18" height="18" aria-hidden="true">
                  <path stroke-linecap="round" stroke-linejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
                </svg>
              </span>
              <h3 class="text-base font-semibold m-0" :style="{ color: 'var(--text)' }">删除会话</h3>
            </div>
            <p class="text-sm leading-relaxed mb-5 mt-0" :style="{ color: 'var(--text-secondary)' }">
              会话「<span :style="{ color: 'var(--text)' }">{{ deletingTitle }}</span>」将被删除，此操作不可恢复。
            </p>
            <div class="flex justify-end gap-2">
              <button
                @click="cancelDelete"
                class="btn-cancel px-4 py-1.5 rounded-lg text-sm cursor-pointer transition-colors"
                :style="{ color: 'var(--text-secondary)', border: '1px solid var(--border)' }"
              >
                取消
              </button>
              <button
                @click="doDelete"
                class="btn-danger px-4 py-1.5 rounded-lg text-sm font-medium text-white cursor-pointer"
              >
                删除
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity 0.18s ease;
}
.modal-fade-enter-active > div,
.modal-fade-leave-active > div {
  transition: transform 0.18s ease, opacity 0.18s ease;
}
.modal-fade-enter-from,
.modal-fade-leave-to {
  opacity: 0;
}
.modal-fade-enter-from > div,
.modal-fade-leave-to > div {
  transform: scale(0.95) translateY(6px);
}

/* 会话行删除按钮：内联样式会覆盖 Tailwind hover 类，改用 scoped 类控制 */
.session-delete {
  color: var(--text-secondary);
}
.session-delete:hover {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

/* 弹窗按钮：取消 = 幽灵按钮 hover 提亮；删除 = 危险红 + 按压反馈 */
.btn-cancel:hover {
  background: var(--bg-tertiary);
  color: var(--text);
}
.btn-danger {
  background-color: #dc2626;
  box-shadow: 0 1px 2px rgba(220, 38, 38, 0.35);
  transition: background-color 0.15s ease, transform 0.1s ease;
}
.btn-danger:hover {
  background-color: #b91c1c;
}
.btn-danger:active {
  transform: scale(0.97);
}
</style>