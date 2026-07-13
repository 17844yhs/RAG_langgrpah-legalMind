<script setup>
import { computed } from 'vue'
import { marked } from 'marked'

const props = defineProps({
  message: { type: Object, required: true },
})

const isUser = computed(() => props.message.role === 'user')
const isAssistant = computed(() => props.message.role === 'assistant')

const renderedContent = computed(() => {
  if (!props.message.content) return ''
  return marked(props.message.content, { breaks: true })
})
</script>

<template>
  <div class="flex gap-3 px-4 py-5" :class="{ 'flex-row-reverse': isUser }">
    <!-- 头像 -->
    <div
      class="w-8 h-8 rounded-full flex-shrink-0 flex items-center justify-center text-sm font-medium text-white"
      :style="{ backgroundColor: isUser ? 'var(--primary)' : '#10b981' }"
    >
      {{ isUser ? '我' : 'AI' }}
    </div>

    <!-- 内容区 -->
    <div class="max-w-[75%] min-w-0">
      <!-- 用户消息 -->
      <div
        v-if="isUser"
        class="px-4 py-2.5 rounded-2xl text-sm leading-relaxed"
        :style="{ backgroundColor: 'var(--primary)', color: '#fff' }"
      >
        {{ message.content }}
      </div>

      <!-- AI 消息 -->
      <div v-if="isAssistant" class="space-y-2">
        <!-- 正在流式输出或已有内容 -->
        <div
          v-if="message.content"
          class="px-4 py-2.5 rounded-2xl text-sm leading-relaxed markdown-body"
          :style="{ backgroundColor: 'var(--bg-secondary)', color: 'var(--text)' }"
        >
          <div v-html="renderedContent"></div>
        </div>
        <div
          v-else
          class="px-4 py-2.5 rounded-2xl"
          :style="{ backgroundColor: 'var(--bg-secondary)' }"
        >
          <span class="inline-block w-2 h-4 rounded" :style="{ backgroundColor: 'var(--text-secondary)' }" style="animation: blink 1s infinite;"></span>
        </div>

        <!-- 引用来源 -->
        <div v-if="message.sources && message.sources.length > 0" class="px-1">
          <details class="text-xs" :style="{ color: 'var(--text-secondary)' }">
            <summary class="cursor-pointer font-medium">引用来源 ({{ message.sources.length }})</summary>
            <div class="mt-2 space-y-1">
              <div v-for="(src, i) in message.sources" :key="i" class="p-2 rounded" :style="{ backgroundColor: 'var(--bg)' }">
                <div class="font-medium">{{ src.title || `来源 ${i + 1}` }}</div>
                <div v-if="src.content" class="mt-1 line-clamp-3">{{ src.content }}</div>
              </div>
            </div>
          </details>
        </div>
      </div>
    </div>
  </div>
</template>

<style>
@keyframes blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
</style>