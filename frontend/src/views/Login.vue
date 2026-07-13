<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const error = ref('')
const loading = ref(false)

async function handleLogin() {
  error.value = ''
  if (!username.value || !password.value) {
    error.value = '请填写用户名和密码'
    return
  }
  loading.value = true
  try {
    await auth.login({ username: username.value, password: password.value })
    const redirect = route.query.redirect || '/chat'
    router.push(redirect)
  } catch (e) {
    error.value = e.response?.data?.detail || '登录失败，请重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-[calc(100vh-3.5rem)] flex items-center justify-center px-4">
    <div class="w-full max-w-sm p-8 rounded-2xl border" :style="{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)' }">
      <h2 class="text-2xl font-bold text-center mb-2" :style="{ color: 'var(--text)' }">欢迎回来</h2>
      <p class="text-sm text-center mb-6" :style="{ color: 'var(--text-secondary)' }">登录您的法律咨询助手账号</p>

      <form @submit.prevent="handleLogin" class="space-y-4">
        <div>
          <label class="block text-sm font-medium mb-1" :style="{ color: 'var(--text)' }">用户名</label>
          <input
            v-model="username"
            type="text"
            placeholder="请输入用户名"
            class="w-full px-3 py-2 rounded-lg border text-sm outline-none transition-colors"
            :style="{ backgroundColor: 'var(--bg)', borderColor: 'var(--border)', color: 'var(--text)' }"
            @focus="$el.style.borderColor = 'var(--primary)'"
          />
        </div>

        <div>
          <label class="block text-sm font-medium mb-1" :style="{ color: 'var(--text)' }">密码</label>
          <input
            v-model="password"
            type="password"
            placeholder="请输入密码"
            class="w-full px-3 py-2 rounded-lg border text-sm outline-none transition-colors"
            :style="{ backgroundColor: 'var(--bg)', borderColor: 'var(--border)', color: 'var(--text)' }"
          />
        </div>

        <div v-if="error" class="text-sm p-3 rounded-lg" style="color: #dc2626; background-color: rgba(220, 38, 38, 0.1);">
          {{ error }}
        </div>

        <button
          type="submit"
          :disabled="loading"
          class="w-full py-2.5 rounded-lg text-white font-medium text-sm transition-opacity disabled:opacity-50 cursor-pointer"
          :style="{ backgroundColor: 'var(--primary)' }"
        >
          {{ loading ? '登录中...' : '登录' }}
        </button>
      </form>

      <p class="text-sm text-center mt-6" :style="{ color: 'var(--text-secondary)' }">
        还没有账号？
        <router-link to="/register" class="font-medium" :style="{ color: 'var(--primary)' }">立即注册</router-link>
      </p>
    </div>
  </div>
</template>