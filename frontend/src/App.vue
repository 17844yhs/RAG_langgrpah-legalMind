<script setup>
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
const route = useRoute()

// 移动端菜单（md 以下顶部导航链接隐藏，用汉堡下拉替代）
const mobileMenuOpen = ref(false)
watch(() => route.fullPath, () => { mobileMenuOpen.value = false })
</script>

<template>
  <div class="min-h-screen" :style="{ backgroundColor: 'var(--bg)' }">
    <!-- 顶部导航栏（主题感知：暗色模式下跟随变暗，文字始终可读） -->
    <header class="app-header border-b sticky top-0 z-50 backdrop-blur-md" :style="{ borderColor: 'var(--border)', boxShadow: 'var(--shadow-sm)' }">
      <div class="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
        <router-link to="/" class="flex items-center gap-2 no-underline font-semibold text-lg" :style="{ color: 'var(--text)' }">
          <span
            class="w-8 h-8 rounded-lg flex items-center justify-center text-white font-serif"
            :style="{ background: 'linear-gradient(135deg, var(--primary-light) 0%, var(--primary-dark) 100%)', boxShadow: '0 1px 4px rgba(0, 0, 0, 0.25), inset 0 0 0 1px rgba(255, 255, 255, 0.15)' }"
          >法</span>
          <span class="font-serif">法律咨询助手</span>
          <span class="hidden sm:inline-block w-px h-5 mx-1" :style="{ backgroundColor: 'var(--accent)' }"></span>
          <span class="hidden sm:inline-block text-xs font-normal tracking-wider uppercase" :style="{ color: 'var(--accent)' }">AI Legal</span>
        </router-link>

        <nav class="hidden md:flex items-center gap-1">
          <router-link to="/chat" class="nav-link no-underline text-sm px-3 py-1.5 rounded-md">法律咨询</router-link>
          <router-link to="/documents" class="nav-link no-underline text-sm px-3 py-1.5 rounded-md">文书生成</router-link>
          <router-link to="/cases" class="nav-link no-underline text-sm px-3 py-1.5 rounded-md">案例检索</router-link>
        </nav>

        <div class="flex items-center gap-3">
          <button
            @click="mobileMenuOpen = !mobileMenuOpen"
            class="md:hidden w-9 h-9 rounded-md nav-ghost-btn text-base cursor-pointer"
            aria-label="打开菜单"
          >{{ mobileMenuOpen ? '✕' : '☰' }}</button>
          <template v-if="auth.isLoggedIn">
            <span class="text-sm" :style="{ color: 'var(--text-secondary)' }">{{ auth.nickname }}</span>
            <button @click="auth.logout(); $router.push('/')" class="nav-ghost-btn text-sm px-3 py-1.5 rounded-md cursor-pointer">退出</button>
          </template>
          <template v-else>
            <router-link to="/login" class="nav-ghost-btn text-sm px-4 py-1.5 rounded-md no-underline">登录</router-link>
            <router-link to="/register" class="text-sm px-4 py-1.5 rounded-md text-white no-underline transition-all hover:shadow-md" :style="{ backgroundColor: 'var(--primary)' }">注册</router-link>
          </template>
        </div>
      </div>

      <!-- 移动端下拉导航（header 为 sticky 定位上下文，绝对定位不占布局空间） -->
      <div
        v-if="mobileMenuOpen"
        class="md:hidden absolute top-14 left-0 right-0 border-b shadow-lg"
        :style="{ backgroundColor: 'var(--bg)', borderColor: 'var(--border)' }"
      >
        <router-link to="/chat" class="nav-link block px-4 py-3 text-sm no-underline">法律咨询</router-link>
        <router-link to="/documents" class="nav-link block px-4 py-3 text-sm no-underline">文书生成</router-link>
        <router-link to="/cases" class="nav-link block px-4 py-3 text-sm no-underline">案例检索</router-link>
      </div>
    </header>

    <!-- 主内容区 -->
    <main>
      <router-view />
    </main>
  </div>
</template>