<script setup>
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
</script>

<template>
  <div class="min-h-screen" :style="{ backgroundColor: 'var(--bg)' }">
    <!-- 顶部导航栏 -->
    <header class="border-b sticky top-0 z-50 backdrop-blur-sm" :style="{ backgroundColor: 'rgba(255,255,255,0.92)', borderColor: 'var(--border)' }">
      <div class="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
        <router-link to="/" class="flex items-center gap-2 no-underline font-semibold text-lg" :style="{ color: 'var(--text)' }">
          <span class="w-8 h-8 rounded-lg flex items-center justify-center text-white" :style="{ backgroundColor: 'var(--primary)' }">法</span>
          <span class="font-serif">法律咨询助手</span>
          <span class="hidden sm:inline-block w-px h-5 mx-1" :style="{ backgroundColor: 'var(--accent)' }"></span>
          <span class="hidden sm:inline-block text-xs font-normal tracking-wider uppercase" :style="{ color: 'var(--accent)' }">AI Legal</span>
        </router-link>

        <nav class="hidden md:flex items-center gap-1">
          <router-link to="/chat" class="no-underline text-sm px-3 py-1.5 rounded-md transition-colors hover:opacity-80" :style="{ color: 'var(--text-secondary)' }">法律咨询</router-link>
          <router-link to="/documents" class="no-underline text-sm px-3 py-1.5 rounded-md transition-colors hover:opacity-80" :style="{ color: 'var(--text-secondary)' }">文书生成</router-link>
          <router-link to="/cases" class="no-underline text-sm px-3 py-1.5 rounded-md transition-colors hover:opacity-80" :style="{ color: 'var(--text-secondary)' }">案例检索</router-link>
        </nav>

        <div class="flex items-center gap-3">
          <template v-if="auth.isLoggedIn">
            <span class="text-sm" :style="{ color: 'var(--text-secondary)' }">{{ auth.nickname }}</span>
            <button @click="auth.logout(); $router.push('/')" class="text-sm px-3 py-1.5 rounded-md border cursor-pointer transition-colors hover:bg-gray-50" :style="{ color: 'var(--text-secondary)', borderColor: 'var(--border)' }">退出</button>
          </template>
          <template v-else>
            <router-link to="/login" class="text-sm px-4 py-1.5 rounded-md border no-underline transition-colors hover:bg-gray-50" :style="{ color: 'var(--text-secondary)', borderColor: 'var(--border)' }">登录</router-link>
            <router-link to="/register" class="text-sm px-4 py-1.5 rounded-md text-white no-underline transition-all hover:shadow-md" :style="{ backgroundColor: 'var(--primary)' }">注册</router-link>
          </template>
        </div>
      </div>
    </header>

    <!-- 主内容区 -->
    <main>
      <router-view />
    </main>
  </div>
</template>