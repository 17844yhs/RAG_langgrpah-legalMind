<script setup>
import { onMounted, watch, ref, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { useChatStore } from '../stores/chat'
import ChatSidebar from '../components/chat/ChatSidebar.vue'
import ChatMessage from '../components/chat/ChatMessage.vue'
import ChatInput from '../components/chat/ChatInput.vue'

const route = useRoute()
const chat = useChatStore()
const messagesEnd = ref(null)
const showSidebar = ref(true)

// 加载会话列表
onMounted(() => {
  chat.loadSessions()
  // 如果路由有 sessionId，加载对应会话
  if (route.params.sessionId) {
    chat.loadMessages(route.params.sessionId)
  }
})

// 如果路由参数变化，加载对应会话
watch(() => route.params.sessionId, (newVal) => {
  if (newVal) {
    chat.loadMessages(newVal)
  }
})

// 自动滚动到底部
watch(
  () => chat.messages.length,
  async () => {
    await nextTick()
    messagesEnd.value?.scrollIntoView({ behavior: 'smooth' })
  }
)
</script>

<template>
  <div class="flex h-[calc(100vh-3.5rem)]">
    <!-- 侧边栏（移动端可收起） -->
    <div v-show="showSidebar" class="hidden md:block">
      <ChatSidebar />
    </div>
    <!-- 移动端侧边栏切换 -->
    <button
      @click="showSidebar = !showSidebar"
      class="md:hidden fixed bottom-20 left-4 z-10 w-10 h-10 rounded-full shadow-lg flex items-center justify-center text-sm cursor-pointer"
      :style="{ backgroundColor: 'var(--primary)', color: '#fff' }"
    >
      {{ showSidebar ? '✕' : '☰' }}
    </button>

    <!-- 右半部分：聊天区 -->
    <div class="flex-1 flex flex-col">
      <!-- 消息列表 -->
      <div class="flex-1 overflow-y-auto" :style="{ backgroundColor: 'var(--bg)' }">
        <!-- 空状态 -->
        <div
          v-if="chat.messages.length === 0"
          class="flex flex-col items-center justify-center h-full text-center px-4"
        >
          <div class="text-5xl mb-4">⚖️</div>
          <h3 class="text-lg font-semibold mb-2" :style="{ color: 'var(--text)' }">法律咨询助手</h3>
          <p class="text-sm max-w-md" :style="{ color: 'var(--text-secondary)' }">
            您好！我是您的 AI 法律助手，可以帮您解答法律问题、分析案情、提供法律建议。请告诉我您遇到的法律问题。
          </p>
        </div>

        <!-- 消息列表 -->
        <div v-else class="max-w-4xl mx-auto">
          <ChatMessage v-for="(msg, i) in chat.messages" :key="i" :message="msg" />
          <div ref="messagesEnd"></div>
        </div>
      </div>

      <!-- 输入区 -->
      <ChatInput />
    </div>
  </div>
</template>