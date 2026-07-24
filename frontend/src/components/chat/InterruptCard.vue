<script setup>
import { ref, computed } from 'vue'
import { useChatStore } from '../../stores/chat'

const chat = useChatStore()
const input = ref('')

const interruptType = computed(() => chat.pendingInterrupt?.type || '')
const question = computed(() => {
  const data = chat.pendingInterrupt
  if (!data) return ''
  if (data.type === 'confirm_intent') return data.question
  if (data.type === 'need_more_info') return data.hint
  return ''
})

const icon = computed(() => {
  if (interruptType.value === 'confirm_intent') return '?'
  if (interruptType.value === 'need_more_info') return '+'
  return '!'
})

const placeholder = computed(() => {
  if (interruptType.value === 'confirm_intent') return '请补充说明您的需求...'
  if (interruptType.value === 'need_more_info') return '请补充案件相关信息...'
  return '请输入...'
})

function submit() {
  const text = input.value.trim()
  if (!text || chat.isStreaming) return
  input.value = ''
  chat.resumeInterrupt(text)
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    submit()
  }
}

/** 快捷选择（意图确认场景） */
function quickSelect(text) {
  input.value = text
  submit()
}

const quickOptions = computed(() => {
  if (interruptType.value === 'confirm_intent') {
    return [
      { label: '咨询法律问题', value: '我想咨询一个法律问题' },
      { label: '生成法律文书', value: '我需要生成一份法律文书' },
      { label: '查找相关案例', value: '帮我查找相关判例' },
    ]
  }
  return []
})
</script>

<template>
  <div
    v-if="chat.pendingInterrupt"
    class="mx-auto max-w-4xl px-4 py-3"
  >
    <div
      class="rounded-2xl border-2 p-4 shadow-sm"
      :style="{
        borderColor: 'var(--primary)',
        backgroundColor: 'var(--bg-secondary)',
      }"
    >
      <!-- 标题行 -->
      <div class="flex items-center gap-2 mb-3">
        <span
          class="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold text-white"
          :style="{ backgroundColor: 'var(--primary)' }"
        >
          {{ icon }}
        </span>
        <span class="text-sm font-semibold" :style="{ color: 'var(--text)' }">
          {{ interruptType === 'confirm_intent' ? '意图确认' : '补充信息' }}
        </span>
        <span
          v-if="chat.pendingInterrupt.confidence !== undefined"
          class="text-xs px-2 py-0.5 rounded-full"
          :style="{
            backgroundColor: chat.pendingInterrupt.confidence < 0.5 ? '#fee2e2' : '#fef3c7',
            color: chat.pendingInterrupt.confidence < 0.5 ? '#991b1b' : '#92400e',
          }"
        >
          置信度 {{ (chat.pendingInterrupt.confidence * 100).toFixed(0) }}%
        </span>
      </div>

      <!-- 问题描述 -->
      <div
        class="text-sm leading-relaxed mb-3 whitespace-pre-line"
        :style="{ color: 'var(--text-secondary)' }"
      >
        {{ question }}
      </div>

      <!-- 快捷选项（仅意图确认场景） -->
      <div v-if="quickOptions.length" class="flex flex-wrap gap-2 mb-3">
        <button
          v-for="opt in quickOptions"
          :key="opt.value"
          @click="quickSelect(opt.value)"
          class="text-xs px-3 py-1.5 rounded-full border cursor-pointer transition-colors hover:opacity-80"
          :style="{
            borderColor: 'var(--primary)',
            color: 'var(--primary)',
            backgroundColor: 'var(--bg)',
          }"
        >
          {{ opt.label }}
        </button>
      </div>

      <!-- 输入区 -->
      <div class="flex items-end gap-2">
        <textarea
          v-model="input"
          @keydown="onKeydown"
          :placeholder="placeholder"
          rows="2"
          class="flex-1 px-3 py-2 rounded-xl border text-sm outline-none resize-none transition-colors"
          :style="{
            backgroundColor: 'var(--bg)',
            borderColor: 'var(--border)',
            color: 'var(--text)',
          }"
        ></textarea>
        <button
          @click="submit"
          :disabled="!input.trim() || chat.isStreaming"
          class="px-4 py-2 rounded-xl text-sm font-medium text-white transition-opacity disabled:opacity-40 cursor-pointer whitespace-nowrap"
          :style="{ backgroundColor: 'var(--primary)' }"
        >
          确认
        </button>
      </div>
    </div>
  </div>
</template>
