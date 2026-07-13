import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import client from '../api/client'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || null)
  const user = ref(JSON.parse(localStorage.getItem('user') || 'null'))

  const isLoggedIn = computed(() => !!token.value)
  const username = computed(() => user.value?.username || '')
  const nickname = computed(() => user.value?.nickname || user.value?.username || '')

  function saveAuth(resp) {
    token.value = resp.access_token
    user.value = { username: resp.username, nickname: resp.nickname }
    localStorage.setItem('token', resp.access_token)
    localStorage.setItem('user', JSON.stringify(user.value))
  }

  async function login(loginData) {
    const { data } = await client.post('/auth/login', loginData)
    saveAuth(data)
    return data
  }

  async function register(registerData) {
    const { data } = await client.post('/auth/register', registerData)
    saveAuth(data)
    return data
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  function init() {
    token.value = localStorage.getItem('token')
    user.value = JSON.parse(localStorage.getItem('user') || 'null')
  }

  return { token, user, isLoggedIn, username, nickname, login, register, logout, init }
})