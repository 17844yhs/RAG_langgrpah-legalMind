<script setup>
import { ref, onMounted } from 'vue'
import { listMemories, addMemory, deleteMemory } from '../api/memory'

const items = ref([])
const loading = ref(false)
const submitting = ref(false)
const content = ref('')
const tag = ref('背景')
const error = ref('')
const MAX_COUNT = 20
const MAX_CHARS = 500

async function load() {
  loading.value = true
  error.value = ''
  try {
    const res = await listMemories()
    items.value = res.data.items
  } catch (e) {
    error.value = e.app_message || '加载失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

async function submit() {
  const text = content.value.trim()
  if (!text) return
  submitting.value = true
  error.value = ''
  try {
    await addMemory(text, tag.value)
    content.value = ''
    await load()
  } catch (e) {
    error.value = e.app_message || e.response?.data?.detail || '添加失败'
  } finally {
    submitting.value = false
  }
}

async function remove(key) {
  error.value = ''
  try {
    await deleteMemory(key)
    await load()
  } catch (e) {
    error.value = e.app_message || '删除失败'
  }
}

onMounted(load)
</script>

<template>
  <div class="max-w-3xl mx-auto px-4 py-8">
    <h1 class="text-2xl font-serif font-semibold mb-2" :style="{ color: 'var(--text)' }">我的背景</h1>
    <p class="text-sm mb-4" :style="{ color: 'var(--text-secondary)' }">
      这些信息会跨会话保存，咨询时助手会主动参考、不再重复询问。内容由你本人维护，删除即彻底清除。
    </p>

    <!-- 填写指引：记忆存"关于你的持久事实"，本次诉求在提问时直接说 -->
    <div class="rounded-lg border px-4 py-3 mb-6 text-xs leading-relaxed" :style="{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }">
      <p><span class="font-medium" :style="{ color: 'var(--primary)' }">适合写：</span>身份与处境（在哪个城市、什么行业）、长期情况（月收入、用工形式）、案件背景事实（合同何时签的、拖欠多久）。</p>
      <p class="mt-1"><span class="font-medium" :style="{ color: 'var(--primary)' }">不用写：</span>本次的具体诉求——每次提问时直接说就行，那是当前对话的事，不是长期背景。</p>
    </div>

    <!-- 添加表单 -->
    <div class="rounded-xl border p-4 mb-6" :style="{ borderColor: 'var(--border)', backgroundColor: 'var(--bg)' }">
      <div class="flex gap-2 mb-3">
        <button
          v-for="t in ['背景', '偏好', '案件']"
          :key="t"
          @click="tag = t"
          class="text-xs px-3 py-1 rounded-full border cursor-pointer transition-all"
          :style="tag === t
            ? { borderColor: 'var(--primary)', backgroundColor: 'var(--primary)', color: '#fff' }
            : { borderColor: 'var(--border)', color: 'var(--text-secondary)' }"
        >{{ t }}</button>
      </div>
      <textarea
        v-model="content"
        rows="3"
        maxlength="500"
        placeholder="例如：本人在深圳一家互联网公司工作，月工资 1 万元，公司已拖欠两个月工资"
        class="w-full rounded-lg border px-3 py-2 text-sm resize-none outline-none"
        :style="{ borderColor: 'var(--border)', backgroundColor: 'var(--bg)', color: 'var(--text)' }"
      ></textarea>
      <div class="flex items-center justify-between mt-2">
        <span class="text-xs" :style="{ color: 'var(--text-secondary)' }">{{ content.length }}/{{ MAX_CHARS }}</span>
        <button
          @click="submit"
          :disabled="submitting || !content.trim() || items.length >= MAX_COUNT"
          class="text-sm px-4 py-1.5 rounded-md text-white cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          :style="{ backgroundColor: 'var(--primary)' }"
        >{{ submitting ? '保存中…' : '添加' }}</button>
      </div>
    </div>

    <p v-if="error" class="text-sm text-red-500 mb-4">{{ error }}</p>

    <!-- 列表 -->
    <div v-if="loading" class="text-sm py-8 text-center" :style="{ color: 'var(--text-secondary)' }">加载中…</div>
    <div v-else-if="items.length === 0" class="text-sm py-8 text-center" :style="{ color: 'var(--text-secondary)' }">
      还没有背景资料。添加后，新会话里助手会自动参考（例如不再重复询问你的工作情况）。
    </div>
    <ul v-else class="space-y-3">
      <li
        v-for="item in items"
        :key="item.key"
        class="rounded-xl border p-4 flex items-start justify-between gap-4"
        :style="{ borderColor: 'var(--border)' }"
      >
        <div>
          <span class="text-xs px-2 py-0.5 rounded-full mr-2" :style="{ backgroundColor: 'var(--bg)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }">{{ item.tag }}</span>
          <p class="text-sm mt-1 whitespace-pre-wrap" :style="{ color: 'var(--text)' }">{{ item.content }}</p>
        </div>
        <button
          @click="remove(item.key)"
          class="text-xs px-2 py-1 rounded-md nav-ghost-btn cursor-pointer shrink-0"
        >删除</button>
      </li>
    </ul>
    <p v-if="items.length >= MAX_COUNT" class="text-xs mt-4" :style="{ color: 'var(--text-secondary)' }">
      已达 {{ MAX_COUNT }} 条上限，删除部分条目后才能继续添加。
    </p>
  </div>
</template>
