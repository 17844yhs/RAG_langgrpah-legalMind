<script setup>
import { ref, onMounted } from 'vue'
import { searchCases, getCaseDetail } from '../api/cases'

const query = ref('')
const courtFilter = ref('')
const caseTypeFilter = ref('')
const results = ref([])
const total = ref(0)
const loading = ref(false)
const error = ref('')

// 详情弹窗
const showDetail = ref(false)
const detailLoading = ref(false)
const detail = ref(null)

const courtOptions = ['', '最高人民法院', '高级人民法院', '中级人民法院', '基层人民法院']
const caseTypeOptions = ['', '民事', '刑事', '行政', '劳动争议', '知识产权', '海事海商']

const currentPage = ref(1)
const pageSize = 10

async function doSearch(page = 1) {
  const q = query.value.trim()
  if (!q) {
    error.value = '请输入搜索关键词'
    return
  }

  error.value = ''
  loading.value = true
  currentPage.value = page

  try {
    const params = { q, limit: pageSize }
    if (courtFilter.value) params.court = courtFilter.value
    if (caseTypeFilter.value) params.case_type = caseTypeFilter.value
    const data = await searchCases(params)
    results.value = data.cases || []
    total.value = data.total || 0
  } catch (e) {
    error.value = e.response?.data?.detail || '搜索失败，请重试'
  } finally {
    loading.value = false
  }
}

async function openDetail(caseId) {
  detailLoading.value = true
  showDetail.value = true
  detail.value = null
  try {
    detail.value = await getCaseDetail(caseId)
  } catch {
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

function closeDetail() {
  showDetail.value = false
  detail.value = null
}

function handleKeydown(e) {
  if (e.key === 'Enter') doSearch()
}
</script>

<template>
  <div class="max-w-5xl mx-auto px-4 py-8">
    <h2 class="text-2xl font-bold mb-6" :style="{ color: 'var(--text)' }">案例检索</h2>

    <!-- 搜索区 -->
    <div class="p-5 rounded-xl border mb-6 space-y-4" :style="{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)' }">
      <div class="flex gap-3">
        <input
          v-model="query"
          @keydown="handleKeydown"
          type="text"
          placeholder="输入关键词搜索案例，如：买卖合同纠纷、交通事故..."
          class="flex-1 px-4 py-2.5 rounded-lg border text-sm outline-none"
          :style="{ backgroundColor: 'var(--bg)', borderColor: 'var(--border)', color: 'var(--text)' }"
        />
        <button
          @click="doSearch()"
          :disabled="loading"
          class="px-6 py-2.5 rounded-lg text-white font-medium text-sm transition-opacity disabled:opacity-50 cursor-pointer"
          :style="{ backgroundColor: 'var(--primary)' }"
        >
          {{ loading ? '搜索中...' : '搜索' }}
        </button>
      </div>

      <div class="flex gap-4">
        <select
          v-model="courtFilter"
          class="px-3 py-2 rounded-lg border text-sm outline-none flex-1"
          :style="{ backgroundColor: 'var(--bg)', borderColor: 'var(--border)', color: 'var(--text)' }"
        >
          <option value="">全部法院</option>
          <option v-for="c in courtOptions.slice(1)" :key="c" :value="c">{{ c }}</option>
        </select>
        <select
          v-model="caseTypeFilter"
          class="px-3 py-2 rounded-lg border text-sm outline-none flex-1"
          :style="{ backgroundColor: 'var(--bg)', borderColor: 'var(--border)', color: 'var(--text)' }"
        >
          <option value="">全部案件类型</option>
          <option v-for="t in caseTypeOptions.slice(1)" :key="t" :value="t">{{ t }}</option>
        </select>
      </div>
    </div>

    <!-- 错误提示 -->
    <div v-if="error" class="text-sm p-3 rounded-lg mb-4" style="color: #dc2626; background-color: rgba(220, 38, 38, 0.1);">
      {{ error }}
    </div>

    <!-- 搜索结果 -->
    <div v-if="loading" class="text-center py-16">
      <div class="text-sm" :style="{ color: 'var(--text-secondary)' }">搜索中...</div>
    </div>

    <div v-else-if="results.length === 0 && query" class="text-center py-16">
      <div class="text-4xl mb-3">🔍</div>
      <p class="text-sm" :style="{ color: 'var(--text-secondary)' }">未找到相关案例，试试其他关键词</p>
    </div>

    <div v-else-if="results.length > 0" class="space-y-3">
      <div class="text-sm mb-2" :style="{ color: 'var(--text-secondary)' }">共找到 {{ total }} 条结果</div>

      <div
        v-for="(caseItem, i) in results"
        :key="caseItem.id || i"
        @click="openDetail(caseItem.id)"
        class="p-4 rounded-xl border cursor-pointer transition-all hover:shadow-md"
        :style="{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)' }"
      >
        <div class="flex items-start justify-between mb-2">
          <h3 class="font-semibold text-sm" :style="{ color: 'var(--text)' }">{{ caseItem.title || '无标题' }}</h3>
          <span class="text-xs px-2 py-0.5 rounded" :style="{ color: 'var(--primary)', backgroundColor: 'rgba(79,70,229,0.1)' }">
            {{ caseItem.case_type || '其他' }}
          </span>
        </div>
        <div class="grid grid-cols-3 gap-4 text-xs mb-2" :style="{ color: 'var(--text-secondary)' }">
          <div>案号：{{ caseItem.case_number || '-' }}</div>
          <div>法院：{{ caseItem.court || '-' }}</div>
          <div>日期：{{ caseItem.judgment_date || '-' }}</div>
        </div>
        <p class="text-xs line-clamp-2" :style="{ color: 'var(--text-secondary)' }">
          {{ caseItem.summary || '暂无摘要' }}
        </p>
      </div>
    </div>

    <!-- 案例详情弹窗 -->
    <Teleport to="body">
      <div
        v-if="showDetail"
        @click.self="closeDetail"
        class="fixed inset-0 z-50 flex items-center justify-center p-4"
        style="background-color: rgba(0,0,0,0.5);"
      >
        <div
          class="w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-2xl p-6"
          :style="{ backgroundColor: 'var(--bg)', color: 'var(--text)' }"
        >
          <div class="flex items-center justify-between mb-4">
            <h3 class="text-lg font-bold">案例详情</h3>
            <button @click="closeDetail" class="text-lg cursor-pointer" :style="{ color: 'var(--text-secondary)' }">✕</button>
          </div>

          <div v-if="detailLoading" class="text-center py-8">
            <div class="text-sm" :style="{ color: 'var(--text-secondary)' }">加载中...</div>
          </div>

          <div v-else-if="detail" class="space-y-4">
            <div>
              <div class="text-sm font-semibold mb-1">标题</div>
              <div class="text-sm" :style="{ color: 'var(--text-secondary)' }">{{ detail.title }}</div>
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <div class="text-sm font-semibold mb-1">案号</div>
                <div class="text-sm" :style="{ color: 'var(--text-secondary)' }">{{ detail.case_number }}</div>
              </div>
              <div>
                <div class="text-sm font-semibold mb-1">审理法院</div>
                <div class="text-sm" :style="{ color: 'var(--text-secondary)' }">{{ detail.court }}</div>
              </div>
              <div>
                <div class="text-sm font-semibold mb-1">裁判日期</div>
                <div class="text-sm" :style="{ color: 'var(--text-secondary)' }">{{ detail.judgment_date }}</div>
              </div>
              <div>
                <div class="text-sm font-semibold mb-1">案件类型</div>
                <div class="text-sm" :style="{ color: 'var(--text-secondary)' }">{{ detail.case_type }}</div>
              </div>
            </div>
            <div>
              <div class="text-sm font-semibold mb-1">裁判要旨</div>
              <div class="text-sm leading-relaxed" :style="{ color: 'var(--text-secondary)' }">{{ detail.summary }}</div>
            </div>
            <div v-if="detail.content">
              <div class="text-sm font-semibold mb-1">裁判文书全文</div>
              <div class="text-sm leading-relaxed whitespace-pre-wrap" :style="{ color: 'var(--text-secondary)' }">{{ detail.content }}</div>
            </div>
            <div v-if="detail.laws && detail.laws.length > 0">
              <div class="text-sm font-semibold mb-1">引用法条</div>
              <ul class="list-disc pl-5 space-y-1">
                <li v-for="(law, i) in detail.laws" :key="i" class="text-sm" :style="{ color: 'var(--text-secondary)' }">{{ law }}</li>
              </ul>
            </div>
          </div>

          <div v-else class="text-center py-8">
            <div class="text-sm" :style="{ color: 'var(--text-secondary)' }">加载失败或案例不存在</div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>