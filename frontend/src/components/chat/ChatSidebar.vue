<script setup>
import { useChatStore } from '../../stores/chat'

const chat = useChatStore()

function selectSession(sessionId) {
  chat.loadMessages(sessionId)
}

function confirmDelete(sessionId, e) {
  e.stopPropagation()
  if (confirm('确认删除此会话？')) {
    chat.removeSession(sessionId)
  }
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
          @click="confirmDelete(s.session_id, $event)"
          class="opacity-0 group-hover:opacity-100 text-xs px-1.5 py-0.5 rounded transition-opacity cursor-pointer"
          :style="{ color: 'var(--text-secondary)' }"
          title="删除"
        >
          ✕
        </button>
      </div>
      <div v-if="chat.sessions.length === 0" class="text-sm text-center py-8" :style="{ color: 'var(--text-secondary)' }">
        暂无会话记录
      </div>
    </div>
  </div>
</template>