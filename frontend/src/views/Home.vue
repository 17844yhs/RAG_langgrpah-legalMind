<script setup>
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
</script>

<template>
  <div>
    <!-- ==================== Hero 横幅区 ==================== -->
    <section
      class="relative overflow-hidden"
      :style="{
        background: 'linear-gradient(135deg, #0f2440 0%, #1a365d 50%, #2c5282 100%)'
      }"
    >
      <!-- 装饰性几何图案 -->
      <div class="absolute inset-0 opacity-[0.08]">
        <div
          class="absolute -top-24 -right-24 w-96 h-96 rounded-full border-[40px]"
          :style="{ borderColor: 'var(--accent)' }"
        ></div>
        <div
          class="absolute -bottom-32 -left-32 w-[500px] h-[500px] rounded-full border-[60px]"
          :style="{ borderColor: 'var(--accent)' }"
        ></div>
      </div>

      <div class="relative max-w-5xl mx-auto px-4 py-20 md:py-28 text-center">
        <!-- 金色徽标 -->
        <div
          class="inline-flex items-center gap-2 px-4 py-1.5 rounded-full text-xs font-medium tracking-wider uppercase mb-8"
          :style="{
            backgroundColor: 'rgba(201, 168, 76, 0.15)',
            color: 'var(--accent-light)',
            border: '1px solid rgba(201, 168, 76, 0.3)'
          }"
        >
          <span class="w-1.5 h-1.5 rounded-full" :style="{ backgroundColor: 'var(--accent)' }"></span>
          智能法律服务系统
        </div>

        <!-- 主标题 -->
        <h1
          class="font-serif text-4xl md:text-5xl lg:text-6xl font-bold leading-tight text-white mb-6"
        >
          专业法律咨询<br class="md:hidden" />
          <span :style="{ color: 'var(--accent-light)' }">AI 智能护航</span>
        </h1>

        <!-- 金色装饰线 -->
        <div class="w-20 h-0.5 mx-auto mb-6" :style="{ backgroundColor: 'var(--accent)' }"></div>

        <!-- 副标题 -->
        <p class="text-lg md:text-xl max-w-3xl mx-auto mb-10" :style="{ color: 'rgba(255,255,255,0.75)' }">
          基于先进人工智能的法律服务平台，为您提供法律文书生成、案例检索分析、在线法律咨询等一站式专业服务
        </p>

        <!-- CTA 按钮组 -->
        <div class="flex items-center justify-center gap-4">
          <router-link
            v-if="auth.isLoggedIn"
            to="/chat"
            class="inline-flex items-center gap-2 px-8 py-3.5 rounded-lg text-sm font-semibold text-white no-underline transition-all hover:shadow-xl hover:-translate-y-0.5"
            :style="{
              backgroundColor: 'var(--accent)',
              boxShadow: '0 4px 14px rgba(201, 168, 76, 0.4)'
            }"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
            开始咨询
          </router-link>
          <template v-else>
            <router-link
              to="/register"
              class="inline-flex items-center gap-2 px-8 py-3.5 rounded-lg text-sm font-semibold text-white no-underline transition-all hover:shadow-xl hover:-translate-y-0.5"
              :style="{
                backgroundColor: 'var(--accent)',
                boxShadow: '0 4px 14px rgba(201, 168, 76, 0.4)'
              }"
            >
              免费注册
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6" />
              </svg>
            </router-link>
            <router-link
              to="/login"
              class="inline-flex items-center px-8 py-3.5 rounded-lg text-sm font-semibold no-underline transition-all hover:bg-white/10"
              :style="{
                color: 'rgba(255,255,255,0.85)',
                border: '1px solid rgba(255,255,255,0.25)'
              }"
            >
              登录
            </router-link>
          </template>
        </div>
      </div>

      <!-- 底部波浪过渡 -->
      <div class="relative h-16 md:h-24" :style="{ backgroundColor: 'var(--bg)' }">
        <svg
          class="absolute top-0 w-full h-full"
          viewBox="0 0 1440 100"
          preserveAspectRatio="none"
          :style="{ color: 'var(--bg)' }"
        >
          <path
            fill="currentColor"
            d="M0,40 C360,100 1080,0 1440,60 L1440,100 L0,100 Z"
          ></path>
        </svg>
      </div>
    </section>

    <!-- ==================== 数据信任区 ==================== -->
    <section class="max-w-5xl mx-auto px-4 -mt-12 relative z-10 mb-16">
      <div
        class="grid md:grid-cols-3 rounded-xl shadow-lg overflow-hidden divide-x"
        :style="{
          backgroundColor: 'var(--bg)',
          border: '1px solid var(--border)',
          boxShadow: 'var(--shadow-lg)',
          divideColor: 'var(--border)'
        }"
      >
        <div class="py-8 px-6 text-center">
          <div
            class="text-3xl md:text-4xl font-bold font-serif mb-1"
            :style="{ color: 'var(--accent)' }"
          >
            10,000+
          </div>
          <div class="text-sm" :style="{ color: 'var(--text-secondary)' }">累计法律服务</div>
        </div>
        <div class="py-8 px-6 text-center">
          <div
            class="text-3xl md:text-4xl font-bold font-serif mb-1"
            :style="{ color: 'var(--accent)' }"
          >
            500+
          </div>
          <div class="text-sm" :style="{ color: 'var(--text-secondary)' }">法律文书模板</div>
        </div>
        <div class="py-8 px-6 text-center">
          <div
            class="text-3xl md:text-4xl font-bold font-serif mb-1"
            :style="{ color: 'var(--accent)' }"
          >
            50,000+
          </div>
          <div class="text-sm" :style="{ color: 'var(--text-secondary)' }">案例库收录</div>
        </div>
      </div>
    </section>

    <!-- ==================== 核心功能区 ==================== -->
    <section class="max-w-5xl mx-auto px-4 mb-20">
      <div class="text-center mb-12">
        <h2
          class="font-serif text-2xl md:text-3xl font-bold mb-3"
          :style="{ color: 'var(--text)' }"
        >
          核心法律服务
        </h2>
        <div class="w-12 h-0.5 mx-auto mb-4" :style="{ backgroundColor: 'var(--accent)' }"></div>
        <p class="text-sm max-w-xl mx-auto" :style="{ color: 'var(--text-secondary)' }">
          依托专业法律知识库与先进 AI 技术，为您提供全方位法律支持
        </p>
      </div>

      <div class="grid md:grid-cols-3 gap-6 lg:gap-8">
        <!-- 法律咨询 -->
        <router-link
          to="/chat"
          class="group block p-8 rounded-xl no-underline transition-all duration-300 hover:-translate-y-1"
          :style="{
            backgroundColor: 'var(--bg)',
            border: '1px solid var(--border)',
            color: 'var(--text)',
            boxShadow: 'var(--shadow-sm)'
          }"
          @mouseenter="$event.target.style.boxShadow = 'var(--shadow-lg)'"
          @mouseleave="$event.target.style.boxShadow = 'var(--shadow-sm)'"
        >
          <div class="w-14 h-14 rounded-xl flex items-center justify-center mb-5 transition-colors"
            :style="{ backgroundColor: 'rgba(26, 54, 93, 0.08)' }"
            @mouseenter="$event.currentTarget.style.backgroundColor = 'rgba(201, 168, 76, 0.15)'"
            @mouseleave="$event.currentTarget.style.backgroundColor = 'rgba(26, 54, 93, 0.08)'"
          >
            <svg class="w-7 h-7" :style="{ color: 'var(--primary)' }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
            </svg>
          </div>
          <h3 class="text-lg font-semibold mb-2 group-hover" :style="{ color: 'var(--text)' }">法律咨询</h3>
          <p class="text-sm leading-relaxed" :style="{ color: 'var(--text-secondary)' }">
            与 AI 律师在线对话，解答您的法律问题，提供专业法律意见与建议。
          </p>
          <div class="mt-4 flex items-center gap-1 text-xs font-medium" :style="{ color: 'var(--accent)' }">
            立即咨询
            <svg class="w-3.5 h-3.5 transition-transform group-hover:translate-x-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
          </div>
        </router-link>

        <!-- 文书生成 -->
        <router-link
          to="/documents"
          class="group block p-8 rounded-xl no-underline transition-all duration-300 hover:-translate-y-1"
          :style="{
            backgroundColor: 'var(--bg)',
            border: '1px solid var(--border)',
            color: 'var(--text)',
            boxShadow: 'var(--shadow-sm)'
          }"
          @mouseenter="$event.target.style.boxShadow = 'var(--shadow-lg)'"
          @mouseleave="$event.target.style.boxShadow = 'var(--shadow-sm)'"
        >
          <div class="w-14 h-14 rounded-xl flex items-center justify-center mb-5"
            :style="{ backgroundColor: 'rgba(26, 54, 93, 0.08)' }"
            @mouseenter="$event.currentTarget.style.backgroundColor = 'rgba(201, 168, 76, 0.15)'"
            @mouseleave="$event.currentTarget.style.backgroundColor = 'rgba(26, 54, 93, 0.08)'"
          >
            <svg class="w-7 h-7" :style="{ color: 'var(--primary)' }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          </div>
          <h3 class="text-lg font-semibold mb-2" :style="{ color: 'var(--text)' }">文书生成</h3>
          <p class="text-sm leading-relaxed" :style="{ color: 'var(--text-secondary)' }">
            自动生成起诉状、答辩状、合同等法律文书，高效便捷，格式规范。
          </p>
          <div class="mt-4 flex items-center gap-1 text-xs font-medium" :style="{ color: 'var(--accent)' }">
            立即使用
            <svg class="w-3.5 h-3.5 transition-transform group-hover:translate-x-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
          </div>
        </router-link>

        <!-- 案例检索 -->
        <router-link
          to="/cases"
          class="group block p-8 rounded-xl no-underline transition-all duration-300 hover:-translate-y-1"
          :style="{
            backgroundColor: 'var(--bg)',
            border: '1px solid var(--border)',
            color: 'var(--text)',
            boxShadow: 'var(--shadow-sm)'
          }"
          @mouseenter="$event.target.style.boxShadow = 'var(--shadow-lg)'"
          @mouseleave="$event.target.style.boxShadow = 'var(--shadow-sm)'"
        >
          <div class="w-14 h-14 rounded-xl flex items-center justify-center mb-5"
            :style="{ backgroundColor: 'rgba(26, 54, 93, 0.08)' }"
            @mouseenter="$event.currentTarget.style.backgroundColor = 'rgba(201, 168, 76, 0.15)'"
            @mouseleave="$event.currentTarget.style.backgroundColor = 'rgba(26, 54, 93, 0.08)'"
          >
            <svg class="w-7 h-7" :style="{ color: 'var(--primary)' }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </div>
          <h3 class="text-lg font-semibold mb-2" :style="{ color: 'var(--text)' }">案例检索</h3>
          <p class="text-sm leading-relaxed" :style="{ color: 'var(--text-secondary)' }">
            检索相关法律案例，查看裁判文书和引用法条，辅助案件分析。
          </p>
          <div class="mt-4 flex items-center gap-1 text-xs font-medium" :style="{ color: 'var(--accent)' }">
            立即检索
            <svg class="w-3.5 h-3.5 transition-transform group-hover:translate-x-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
          </div>
        </router-link>
      </div>
    </section>

    <!-- ==================== 特色亮点区 ==================== -->
    <section :style="{ backgroundColor: 'var(--bg-secondary)' }" class="py-16 md:py-20">
      <div class="max-w-5xl mx-auto px-4">
        <div class="text-center mb-12">
          <h2
            class="font-serif text-2xl md:text-3xl font-bold mb-3"
            :style="{ color: 'var(--text)' }"
          >
            为什么选择我们
          </h2>
          <div class="w-12 h-0.5 mx-auto" :style="{ backgroundColor: 'var(--accent)' }"></div>
        </div>

        <div class="grid md:grid-cols-3 gap-8 lg:gap-12">
          <div class="text-center">
            <div
              class="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-5"
              :style="{ backgroundColor: 'rgba(201, 168, 76, 0.12)' }"
            >
              <svg class="w-8 h-8" :style="{ color: 'var(--accent)' }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
            </div>
            <h3 class="text-base font-semibold mb-2">AI 智能驱动</h3>
            <p class="text-sm leading-relaxed" :style="{ color: 'var(--text-secondary)' }">
              采用先进的大语言模型技术，深度理解法律问题，提供精准专业的解答与建议。
            </p>
          </div>

          <div class="text-center">
            <div
              class="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-5"
              :style="{ backgroundColor: 'rgba(201, 168, 76, 0.12)' }"
            >
              <svg class="w-8 h-8" :style="{ color: 'var(--accent)' }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <h3 class="text-base font-semibold mb-2">专业精准可靠</h3>
            <p class="text-sm leading-relaxed" :style="{ color: 'var(--text-secondary)' }">
              基于权威法律知识库与真实案例数据训练，确保法律意见的准确性和专业性。
            </p>
          </div>

          <div class="text-center">
            <div
              class="w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-5"
              :style="{ backgroundColor: 'rgba(201, 168, 76, 0.12)' }"
            >
              <svg class="w-8 h-8" :style="{ color: 'var(--accent)' }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
            </div>
            <h3 class="text-base font-semibold mb-2">数据安全保障</h3>
            <p class="text-sm leading-relaxed" :style="{ color: 'var(--text-secondary)' }">
              采用企业级加密技术，严格保护您的隐私数据与法律咨询内容，安全无忧。
            </p>
          </div>
        </div>
      </div>
    </section>

    <!-- ==================== 底部 CTA ==================== -->
    <section class="py-16 md:py-20" :style="{ backgroundColor: 'var(--bg)' }">
      <div class="max-w-3xl mx-auto px-4 text-center">
        <h2
          class="font-serif text-2xl md:text-3xl font-bold mb-4"
          :style="{ color: 'var(--text)' }"
        >
          开始您的智能法律之旅
        </h2>
        <div class="w-12 h-0.5 mx-auto mb-4" :style="{ backgroundColor: 'var(--accent)' }"></div>
        <p class="text-sm mb-8 max-w-lg mx-auto" :style="{ color: 'var(--text-secondary)' }">
          注册即可免费体验 AI 法律咨询服务，让专业法律帮助触手可及
        </p>
        <router-link
          v-if="auth.isLoggedIn"
          to="/chat"
          class="inline-flex items-center gap-2 px-8 py-3.5 rounded-lg text-sm font-semibold text-white no-underline transition-all hover:shadow-xl hover:-translate-y-0.5"
          :style="{
            backgroundColor: 'var(--primary)',
            boxShadow: '0 4px 14px rgba(26, 54, 93, 0.3)'
          }"
        >
          进入咨询
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6" />
          </svg>
        </router-link>
        <template v-else>
          <router-link
            to="/register"
            class="inline-flex items-center gap-2 px-8 py-3.5 rounded-lg text-sm font-semibold text-white no-underline transition-all hover:shadow-xl hover:-translate-y-0.5"
            :style="{
              backgroundColor: 'var(--primary)',
              boxShadow: '0 4px 14px rgba(26, 54, 93, 0.3)'
            }"
          >
            免费注册
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 7l5 5m0 0l-5 5m5-5H6" />
            </svg>
          </router-link>
        </template>
      </div>
    </section>
  </div>
</template>