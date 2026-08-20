import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

function isValidJwt(token) {
  if (!token || typeof token !== 'string') return false
  const parts = token.split('.')
  return parts.length === 3 && parts.every(p => p.length > 0)
}

api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (isValidJwt(token)) {
      config.headers = config.headers || {}
      config.headers['Authorization'] = 'Bearer ' + token
    }
    return config
  },
  (error) => Promise.reject(error)
)

async function clearAuthAndRedirect() {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  ElMessage.warning('登录已过期，请重新登录')
  try {
    const routerMod = await import('@/router')
    routerMod.default.push('/login')
  } catch (e) {
    window.location.href = '/login'
  }
}

api.interceptors.response.use(
  (response) => response.data,
  async (error) => {
    const status = error.response?.status
    const url = error.config?.url || ''
    const detail = (error.response?.data?.detail || '').toString()

    const isLoginRequest = url.includes('/auth/login') || url.includes('/auth/register')

    if (status === 401 && !isLoginRequest) {
      await clearAuthAndRedirect()
      return Promise.reject(error)
    }

    if (status === 403 && !isLoginRequest) {
      const isPermissionDenied =
        detail.includes('权限') ||
        detail.includes('admin') ||
        detail.includes('需要管理员') ||
        detail.includes('Forbidden')

      if (isPermissionDenied) {
        ElMessage.error('权限不足，无法执行此操作')
      } else {
        await clearAuthAndRedirect()
      }
      return Promise.reject(error)
    }

    // FastAPI 422 验证错误返回的 detail 是数组（[{loc, msg, type}]），
    // 直接传给 ElMessage 会触发 setAttribute '0' 异常，需归一化为字符串
    const rawDetail = error.response?.data?.detail
    let message
    if (Array.isArray(rawDetail)) {
      message = rawDetail.map(e => e?.msg || JSON.stringify(e)).join('; ')
    } else {
      message = rawDetail || error.response?.data?.message || error.message || '请求失败，请稍后再试'
    }
    // 防御：确保 message 始终是字符串，避免 ElMessage 收到对象/数组导致渲染异常
    if (typeof message !== 'string') {
      message = JSON.stringify(message)
    }
    ElMessage.error(message)
    return Promise.reject(error)
  }
)

export default api

// ─────────────────────────────────────────────────────────────
// 命名端点函数（集中管理后端 API 路径，便于维护与重构）
// 组件可按需导入使用，如 `import { recipes } from '@/api'`
// 现有组件中的 api.get('/...') 字面量调用仍可继续工作，逐步迁移即可
// ─────────────────────────────────────────────────────────────
export const auth = {
  register: (data) => api.post('/auth/register', data),
  login: (data) => api.post('/auth/login', data),
  me: () => api.get('/auth/me'),
}

export const recipes = {
  list: (params) => api.get('/recipes', { params }),
  hot: (params) => api.get('/recipes/hot', { params }),
  detail: (id) => api.get(`/recipes/${id}`),
  create: (data) => api.post('/recipes', data),
  update: (id, data) => api.put(`/recipes/${id}`, data),
  remove: (id) => api.delete(`/recipes/${id}`),
}

export const mealPlans = {
  list: (params) => api.get('/meal-plans', { params }),
  detail: (id) => api.get(`/meal-plans/${id}`),
  create: (data) => api.post('/meal-plans', data),
  update: (id, data) => api.put(`/meal-plans/${id}`, data),
  remove: (id) => api.delete(`/meal-plans/${id}`),
}

export const cookingNotes = {
  list: (params) => api.get('/cooking-notes', { params }),
  detail: (id) => api.get(`/cooking-notes/${id}`),
  create: (data) => api.post('/cooking-notes', data),
  update: (id, data) => api.put(`/cooking-notes/${id}`, data),
  remove: (id) => api.delete(`/cooking-notes/${id}`),
  comments: (id, params) => api.get(`/cooking-notes/${id}/comments`, { params }),
  createComment: (id, data) => api.post(`/cooking-notes/${id}/comments`, data),
  removeComment: (cid) => api.delete(`/cooking-notes/comments/${cid}`),
}

export const reviews = {
  list: (recipeId, params) => api.get(`/reviews/recipes/${recipeId}`, { params }),
  create: (recipeId, data) => api.post(`/reviews/recipes/${recipeId}`, data),
  remove: (id) => api.delete(`/reviews/${id}`),
}

export const users = {
  updateProfile: (data) => api.put('/users/profile', data),
  favorites: (params) => api.get('/users/favorites', { params }),
  history: (params) => api.get('/users/history', { params }),
  conversations: () => api.get('/users/conversations'),
}

export const recommendations = {
  personalized: (params) => api.get('/recommendations/personalized', { params }),
  query: (data) => api.post('/recommendations/query', data),
}

export const admin = {
  stats: () => api.get('/admin/stats'),
  tags: (params) => api.get('/admin/tags', { params }),
  createTag: (params) => api.post('/admin/tags', null, { params }),
  updateTag: (id, params) => api.put(`/admin/tags/${id}`, null, { params }),
  removeTag: (id) => api.delete(`/admin/tags/${id}`),
  ingredients: (params) => api.get('/admin/ingredients', { params }),
  pendingRecipes: (params) => api.get('/admin/recipes/pending', { params }),
  auditRecipe: (id, data) => api.post(`/admin/recipes/${id}/audit`, data),
  removeRecipe: (id) => api.delete(`/admin/recipes/${id}`),
  pendingMealPlans: (params) => api.get('/admin/meal-plans/pending', { params }),
  auditMealPlan: (id, data) => api.post(`/admin/meal-plans/${id}/audit`, data),
  removeMealPlan: (id) => api.delete(`/admin/meal-plans/${id}`),
  users: (params) => api.get('/admin/users', { params }),
  toggleUserActive: (id) => api.post(`/admin/users/${id}/toggle-active`),
  updateUserRole: (id, role) => api.post(`/admin/users/${id}/role`, null, { params: { role } }),
}
