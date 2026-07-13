<script setup>
import { ref } from 'vue'
import { useChatStore } from '../../stores/chat'

const chat = useChatStore()
const input = ref('')

function send() {
  const text = input.value.trim()
  if (!text || chat.isStreaming) return
  input.value = ''
  chat.sendMessage(text)
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}
</script>

<template>
  <div class="border-t p-4" :style="{ borderColor: 'var(--border)', backgroundColor: 'var(--bg)' }">
    <div class="flex items-end gap-3 max-w-4xl mx-auto">
      <textarea
        v-model="input"
        @keydown="onKeydown"
        :placeholder="chat.isStreaming ? 'AI 正在回复...' : '输入您的法律问题...'"
        :disabled="chat.isStreaming"
        rows="1"
        class="flex-1 px-4 py-2.5 rounded-xl border resize-none text-sm outline-none transition-colors"
        :style="{
          backgroundColor: 'var(--bg-secondary)',
          borderColor: 'var(--border)',
          color: 'var(--text)',
          maxHeight: '120px',
        }"
      ></textarea>
      <button
        v-if="chat.isStreaming"
        @click="chat.cancelStream()"
        class="px-4 py-2.5 rounded-xl text-sm font-medium text-white cursor-pointer"
        style="background-color: #ef4444;"
      >
        停止
      </button>
      <button
        v-else
        @click="send()"
        :disabled="!input.trim()"
        class="px-5 py-2.5 rounded-xl text-sm font-medium text-white transition-opacity disabled:opacity-40 cursor-pointer"
        :style="{ backgroundColor: 'var(--primary)' }"
      >
        发送
      </button>
    </div>
  </div>
</template>