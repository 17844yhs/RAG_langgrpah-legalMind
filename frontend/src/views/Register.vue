<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()

const username = ref('')
const email = ref('')
const password = ref('')
const nickname = ref('')
const error = ref('')
const loading = ref(false)

async function handleRegister() {
  error.value = ''
  if (!username.value || !email.value || !password.value) {
    error.value = '请填写所有必填字段'
    return
  }
  loading.value = true
  try {
    await auth.register({
      username: username.value,
      email: email.value,
      password: password.value,
      nickname: nickname.value,
    })
    router.push('/chat')
  } catch (e) {
    error.value = e.response?.data?.detail || '注册失败，请重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="min-h-[calc(100vh-3.5rem)] flex items-center justify-center px-4 py-8">
    <div class="w-full max-w-sm p-8 rounded-2xl border" :style="{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border)' }">
      <h2 class="text-2xl font-bold text-center mb-2" :style="{ color: 'var(--text)' }">创建账号</h2>
      <p class="text-sm text-center mb-6" :style="{ color: 'var(--text-secondary)' }">注册法律咨询助手账号</p>

      <form @submit.prevent="handleRegister" class="space-y-4">
        <div>
          <label class="block text-sm font-medium mb-1" :style="{ color: 'var(--text)' }">用户名 <span class="text-red-500">*</span></label>
          <input
            v-model="username"
            type="text"
            placeholder="请输入用户名"
            class="w-full px-3 py-2 rounded-lg border text-sm outline-none"
            :style="{ backgroundColor: 'var(--bg)', borderColor: 'var(--border)', color: 'var(--text)' }"
          />
        </div>

        <div>
          <label class="block text-sm font-medium mb-1" :style="{ color: 'var(--text)' }">邮箱 <span class="text-red-500">*</span></label>
          <input
            v-model="email"
            type="email"
            placeholder="请输入邮箱"
            class="w-full px-3 py-2 rounded-lg border text-sm outline-none"
            :style="{ backgroundColor: 'var(--bg)', borderColor: 'var(--border)', color: 'var(--text)' }"
          />
        </div>

        <div>
          <label class="block text-sm font-medium mb-1" :style="{ color: 'var(--text)' }">密码 <span class="text-red-500">*</span></label>
          <input
            v-model="password"
            type="password"
            placeholder="请输入密码"
            class="w-full px-3 py-2 rounded-lg border text-sm outline-none"
            :style="{ backgroundColor: 'var(--bg)', borderColor: 'var(--border)', color: 'var(--text)' }"
          />
        </div>

        <div>
          <label class="block text-sm font-medium mb-1" :style="{ color: 'var(--text)' }">昵称</label>
          <input
            v-model="nickname"
            type="text"
            placeholder="选填"
            class="w-full px-3 py-2 rounded-lg border text-sm outline-none"
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
          {{ loading ? '注册中...' : '注册' }}
        </button>
      </form>

      <p class="text-sm text-center mt-6" :style="{ color: 'var(--text-secondary)' }">
        已有账号？<router-link to="/login" class="font-medium" :style="{ color: 'var(--primary)' }">立即登录</router-link>
      </p>
    </div>
  </div>
</template>