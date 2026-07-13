import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'
import { useAuthStore } from './stores/auth'
import './style.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)

// 初始化 auth 状态（从 localStorage 恢复）
const auth = useAuthStore()
auth.init()

app.mount('#app')