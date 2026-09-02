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
// 组件统一按需导入使用，如 `import { recipes, users } from '../api'`
// 约定：所有路径只在此文件出现一次，views/stores 一律调用命名端点，
//       后端路由变更时只需改这里。
// ─────────────────────────────────────────────────────────────
export const auth = {
  register: (data) => api.post('/auth/register', data),
  login: (data) => api.post('/auth/login', data),
  me: () => api.get('/auth/me'),
}

export const stats = {
  home: () => api.get('/stats'),
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
  shoppingList: (id) => api.get(`/meal-plans/${id}/shopping-list`),
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
  changePassword: (data) => api.put('/users/password', data),
  getPreferences: () => api.get('/users/preferences'),
  updatePreferences: (data) => api.put('/users/preferences', data),
  // 收藏：新增/取消（favoriteType: 'recipe' | 'meal_plan'）
  favorites: (params) => api.get('/users/favorites', { params }),
  addFavorite: (favoriteType, favoriteId) =>
    api.post('/users/favorites', null, {
      params: { favorite_type: favoriteType, favorite_id: favoriteId },
    }),
  removeFavorite: (id) => api.delete(`/users/favorites/${id}`),
  removeFavoriteByItem: (type, id) =>
    api.delete(`/users/favorites/by/${type}/${id}`),
  // 浏览历史：记录（params 传 { recipe_id } 或 { meal_plan_id }）与查询
  recordHistory: (params) => api.post('/users/history', null, { params }),
  history: (params) => api.get('/users/history', { params }),
  // AI 对话历史
  conversations: (params) => api.get('/users/conversations', { params }),
  conversationDetail: (id) => api.get(`/users/conversations/${id}`),
}

// AI 模块 —— 对话管理（聊天 SSE 流式请求走 utils/sse.js 的 fetch，不经 axios）
export const ai = {
  rewindEdit: (convId, data) =>
    api.post(`/ai/conversations/${convId}/rewind-edit`, data),
  deleteConversation: (convId) => api.delete(`/ai/conversations/${convId}`),
}

export const recommendations = {
  prompts: (params) => api.get('/recommendations/prompts', { params }),
  personalized: (params) => api.get('/recommendations/personalized', { params }),
  mealPlans: (params) => api.get('/recommendations/meal-plans', { params }),
  query: (data) => api.post('/recommendations/query', data),
}

export const admin = {
  stats: () => api.get('/admin/stats'),
  tags: (params) => api.get('/admin/tags', { params }),
  createTag: (params) => api.post('/admin/tags', null, { params }),
  updateTag: (id, params) => api.put(`/admin/tags/${id}`, null, { params }),
  removeTag: (id) => api.delete(`/admin/tags/${id}`),
  ingredients: (params) => api.get('/admin/ingredients', { params }),
  createIngredient: (params) => api.post('/admin/ingredients', null, { params }),
  auditIngredient: (id, data) => api.post(`/admin/ingredients/${id}/audit`, data),
  updateIngredient: (id, params) =>
    api.put(`/admin/ingredients/${id}`, null, { params }),
  removeIngredient: (id) => api.delete(`/admin/ingredients/${id}`),
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
