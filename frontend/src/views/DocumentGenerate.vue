<script setup>
import { ref, onMounted, computed } from 'vue'
import { getTemplates, streamGenerateDocument } from '../api/documents'
import { marked } from 'marked'

const templates = ref([])
const selectedType = ref('')
const query = ref('')
const paramsText = ref('')
const isLoading = ref(false)
const isStreaming = ref(false)
const content = ref('')
const references = ref([])
const error = ref('')

const selectedTemplate = computed(() =>
  templates.value.find((t) => t.type === selectedType.value)
)

onMounted(async () => {
  try {
    templates.value = await getTemplates()
    if (templates.value.length > 0) {
      selectedType.value = templates.value[0].type
    }
  } catch {
    // 静默处理
  }
})

function parseParams() {
  const lines = paramsText.value
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)

  const params = {}
  for (const line of lines) {
    const match = line.match(/^([^:：]+)[:：]\s*(.+)$/)
    if (!match) continue

    const key = match[1].trim()
    const val = match[2].trim()
    if (key && val) params[key] = val
  }

  return params
}

async function handleGenerate() {
  if (!query.value.trim()) {
    error.value = '请输入您的需求描述'
    return
  }

  error.value = ''
  content.value = ''
  references.value = []
  isLoading.value = true
  isStreaming.value = true

  try {
    const params = parseParams()
    const { stream } = streamGenerateDocument(selectedType.value, query.value, params)
    for await (const chunk of stream) {
      if (chunk.done) break
      if (chunk.content !== undefined) {
        content.value += chunk.content
      }
      if (chunk.references) {
        references.value = chunk.references
      }
    }
  } catch (e) {
    if (e.name !== 'AbortError') {
      error.value = '生成失败，请重试'
    }
  } finally {
    isLoading.value = false
    isStreaming.value = false
  }
}

const renderedContent = computed(() => {
  if (!content.value) return ''
  return marked(content.value, { breaks: true })
})

function copyContent() {
  navigator.clipboard.writeText(content.value)
    .then(() => alert('已复制到剪贴板'))
    .catch(() => alert('复制失败'))
}
</script>

<template>
  <div class="max-w-5xl mx-auto px-4 py-8">
    <h2 class="text-2xl font-bold mb-6" :style="{ color: 'var(--text)' }">法律文书生成</h2>

    <div class="grid md:grid-cols-5 gap-6">
      <!-- 左侧：表单区 -->
      <div class="md:col-span-2 space-y-5">
        <div>
          <label class="block text-sm font-medium mb-1.5" :style="{ color: 'var(--text)' }">文书类型</label>
          <select
            v-model="selectedType"
            class="w-full px-3 py-2 rounded-lg border text-sm outline-none"
            :style="{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)', color: 'var(--text)' }"
          >
            <option v-for="t in templates" :key="t.type" :value="t.type">{{ t.description }}</option>
          </select>
        </div>

        <div>
          <label class="block text-sm font-medium mb-1.5" :style="{ color: 'var(--text)' }">需求描述</label>
          <textarea
            v-model="query"
            placeholder="请详细描述您的需求，例如：我要起诉某公司拖欠货款..."
            rows="6"
            class="w-full px-3 py-2 rounded-lg border text-sm outline-none resize-none"
            :style="{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)', color: 'var(--text)' }"
          ></textarea>
        </div>

        <div>
          <label class="block text-sm font-medium mb-1.5" :style="{ color: 'var(--text)' }">补充参数（每行一个，选填）</label>
          <textarea
            v-model="paramsText"
            placeholder="例如：&#10;原告：张三&#10;被告：李四公司&#10;案由：买卖合同纠纷"
            rows="4"
            class="w-full px-3 py-2 rounded-lg border text-sm outline-none resize-none"
            :style="{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)', color: 'var(--text)' }"
          ></textarea>
        </div>

        <div v-if="error" class="text-sm p-3 rounded-lg" style="color: #dc2626; background-color: rgba(220, 38, 38, 0.1);">
          {{ error }}
        </div>

        <button
          @click="handleGenerate"
          :disabled="isStreaming || !query.trim()"
          class="w-full py-2.5 rounded-lg text-white font-medium text-sm transition-opacity disabled:opacity-50 cursor-pointer"
          :style="{ backgroundColor: 'var(--primary)' }"
        >
          {{ isStreaming ? '生成中...' : '生成文书' }}
        </button>
      </div>

      <!-- 右侧：结果区 -->
      <div class="md:col-span-3">
        <div
          class="border rounded-xl min-h-[400px] flex flex-col"
          :style="{ borderColor: 'var(--border)' }"
        >
          <!-- 空状态 -->
          <div
            v-if="!content && !isStreaming"
            class="flex-1 flex items-center justify-center text-center p-8"
          >
            <div>
              <div class="text-4xl mb-3">📄</div>
              <p class="text-sm" :style="{ color: 'var(--text-secondary)' }">在左侧填写信息后，点击"生成文书"</p>
            </div>
          </div>

          <!-- 生成内容 -->
          <div v-else class="flex-1 p-6 overflow-y-auto">
            <div class="flex items-center justify-between mb-4">
              <h3 class="font-semibold" :style="{ color: 'var(--text)' }">
                {{ selectedTemplate?.description || selectedType }}
              </h3>
              <button
                v-if="content"
                @click="copyContent"
                class="text-xs px-3 py-1 rounded border cursor-pointer"
                :style="{ color: 'var(--text-secondary)', borderColor: 'var(--border)' }"
              >
                复制全文
              </button>
            </div>
            <div class="markdown-body text-sm leading-relaxed" :style="{ color: 'var(--text)' }" v-html="renderedContent"></div>
            <!-- 流式闪烁 -->
            <span
              v-if="isStreaming"
              class="inline-block w-2 h-4 ml-1 rounded"
              :style="{ backgroundColor: 'var(--text-secondary)' }"
              style="animation: blink 1s infinite;"
            ></span>
          </div>

          <!-- 引用 -->
          <div v-if="references.length > 0" class="border-t p-4" :style="{ borderColor: 'var(--border)' }">
            <details class="text-xs" :style="{ color: 'var(--text-secondary)' }">
              <summary class="cursor-pointer font-medium">参考来源 ({{ references.length }})</summary>
              <div class="mt-2 space-y-1">
                <div v-for="(ref, i) in references" :key="i" class="p-2 rounded" :style="{ backgroundColor: 'var(--bg-secondary)' }">
                  <div class="font-medium">{{ ref.title || `来源 ${i + 1}` }}</div>
                  <div v-if="ref.content" class="mt-1">{{ ref.content.slice(0, 200) }}...</div>
                </div>
              </div>
            </details>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>