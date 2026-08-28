import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { auth } from '../api'
import axios from 'axios'

function parseUserFromStorage() {
  try {
    const raw = localStorage.getItem('user')
    if (!raw) return null
    return JSON.parse(raw)
  } catch (e) {
    localStorage.removeItem('user')
    return null
  }
}

function getTokenFromStorage() {
  const token = localStorage.getItem('token')
  if (!token || typeof token !== 'string') {
    localStorage.removeItem('token')
    return ''
  }
  const parts = token.split('.')
  if (parts.length !== 3 || !parts.every(p => p.length > 0)) {
    localStorage.removeItem('token')
    return ''
  }
  return token
}

export const useUserStore = defineStore('user', () => {
  const user = ref(parseUserFromStorage())
  const token = ref(getTokenFromStorage())

  const isLoggedIn = computed(() => !!token.value)
  const isAdmin = computed(() => user.value?.role === 'admin')

  async function login(username, password) {
    const res = await auth.login({ username, password })
    token.value = res.access_token
    user.value = res.user
    localStorage.setItem('token', res.access_token)
    localStorage.setItem('user', JSON.stringify(res.user))
    return res
  }

  async function register(data) {
    return await auth.register(data)
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  /**
   * 启动时校验登录态（防"自动登录成官方小厨但一操作就过期"）。
   *
   * 用独立的裸 axios 调用 /auth/me，绕开共享拦截器（避免弹"登录已过期"弹窗），
   * 静默处理：
   *   - token 有效     → 刷新并保存最新用户信息，保留登录态
   *   - token 过期/无效 → 静默清除登录态（不弹窗、不强跳转）
   *   - 后端暂不可用（非 401）→ 保留原样，避免误登出
   */
  async function validateSession() {
    const existing = token.value || localStorage.getItem('token')
    if (!existing) return false
    try {
      const { data } = await axios.get('/api/auth/me', {
        headers: { Authorization: 'Bearer ' + existing },
        timeout: 8000,
      })
      user.value = data
      localStorage.setItem('user', JSON.stringify(data))
      return true
    } catch (e) {
      if (e && e.response && e.response.status === 401) {
        token.value = ''
        user.value = null
        localStorage.removeItem('token')
        localStorage.removeItem('user')
      }
      return false
    }
  }

  return { user, token, isLoggedIn, isAdmin, login, register, logout, validateSession }
})