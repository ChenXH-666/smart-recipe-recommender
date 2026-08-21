import { createRouter, createWebHistory } from 'vue-router'

/**
 * 路由表设计说明（答辩用）
 * ========================
 * 系统路由分为四大模块，按业务边界清晰划分：
 *
 * 1. 前台页面（'/'）—— 首页、菜谱浏览/创建/详情/编辑、套餐广场/创建/详情、烹饪心得
 *    所有前台页面共享 MainLayout（导航栏 + 面包屑 + 页脚 + AI 悬浮按钮）
 *    创建/编辑类页面通过 meta.requiresAuth 标记，仅登录用户可访问
 *
 * 2. 登录/注册（'/login', '/register'）—— 独立页面，不需要 MainLayout 导航栏
 *    未登录用户只能访问这两个页面和前台公开内容
 *
 * 3. 个人中心（'/user'）—— 个人信息、收藏、浏览历史、AI 对话记录
 *    复用 MainLayout，通过 meta.requiresAuth 标记，仅登录用户可访问
 *
 * 4. 后台管理（'/admin'）—— 仪表盘、菜谱审核、套餐审核、用户管理、标签/食材管理
 *    通过 meta.requiresAdmin 标记，在路由守卫中验证管理员权限
 *    非管理员访问会被重定向到首页
 */
const routes = [
  // ---- 前台页面（带导航栏）----
  {
    path: '/',
    component: () => import('../layouts/MainLayout.vue'),
    children: [
      { path: '', name: 'Home', component: () => import('../views/Home.vue') },
      { path: 'for-you', name: 'ForYou', component: () => import('../views/ForYouRecipes.vue') },
      { path: 'hot-recipes', name: 'HotRecipes', component: () => import('../views/HotRecipes.vue') },
      { path: 'recipes', name: 'Recipes', component: () => import('../views/RecipeList.vue') },
      { path: 'recipes/create', name: 'RecipeCreate', component: () => import('../views/RecipeCreate.vue'), meta: { requiresAuth: true } },
      { path: 'recipes/:id', name: 'RecipeDetail', component: () => import('../views/RecipeDetail.vue') },
      { path: 'recipes/:id/edit', name: 'RecipeEdit', component: () => import('../views/RecipeEdit.vue'), meta: { requiresAuth: true } },
      { path: 'meal-plans', name: 'MealPlans', component: () => import('../views/MealPlanList.vue') },
      { path: 'meal-plans/create', name: 'MealPlanCreate', component: () => import('../views/MealPlanCreate.vue'), meta: { requiresAuth: true } },
      { path: 'meal-plans/:id', name: 'MealPlanDetail', component: () => import('../views/MealPlanDetail.vue') },
      { path: 'cooking-notes', name: 'CookingNotes', component: () => import('../views/CookingNotes.vue') },
      { path: 'cooking-notes/:id', name: 'CookingNoteDetail', component: () => import('../views/CookingNoteDetail.vue') },
      // 旧路径 /notes 兼容重定向（PRD 6.2.2 路径对齐）
      { path: 'notes', redirect: '/cooking-notes' },
      { path: 'notes/:id', redirect: (to) => `/cooking-notes/${to.params.id}` },
    ],
  },
  // 登录/注册（独立页面，不需要导航栏）
  {
    path: '/login',
    name: 'Login',
    component: () => import('../views/Login.vue'),
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('../views/Register.vue'),
  },
  // 个人中心
  {
    path: '/user',
    component: () => import('../layouts/MainLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      // /user 默认跳转到资料页（避免空白）
      { path: '', redirect: '/user/profile' },
      { path: 'profile', name: 'Profile', component: () => import('../views/user/Profile.vue') },
      { path: 'favorites', name: 'Favorites', component: () => import('../views/user/Favorites.vue') },
      { path: 'history', name: 'History', component: () => import('../views/user/History.vue') },
      { path: 'conversations', name: 'Conversations', component: () => import('../views/user/Conversations.vue') },
      { path: 'preferences', name: 'Preferences', component: () => import('../views/user/Preferences.vue') },
      { path: 'todo', name: 'TodoList', component: () => import('../views/user/TodoList.vue') },
      { path: 'my-recipes', name: 'MyRecipes', component: () => import('../views/user/MyRecipes.vue') },
      { path: 'my-meal-plans', name: 'MyMealPlans', component: () => import('../views/user/MyMealPlans.vue') },
    ],
  },
  // 后台管理（通过 meta.requiresAdmin 标记，在路由守卫中校验管理员权限）
  {
    path: '/admin',
    component: () => import('../layouts/MainLayout.vue'),
    meta: { requiresAdmin: true },
    children: [
      { path: '', name: 'AdminDashboard', component: () => import('../views/admin/Dashboard.vue') },
      { path: 'recipe-audit', name: 'AdminRecipeAudit', component: () => import('../views/admin/RecipeAudit.vue') },
      { path: 'meal-plan-audit', name: 'AdminMealPlanAudit', component: () => import('../views/admin/MealPlanAudit.vue') },
      { path: 'users', name: 'AdminUsers', component: () => import('../views/admin/UserManage.vue') },
      { path: 'tags', name: 'AdminTags', component: () => import('../views/admin/TagManage.vue') },
      { path: 'ingredients', name: 'AdminIngredients', component: () => import('../views/admin/IngredientManage.vue') },
      // 旧路径兼容重定向（PRD 6.2.2 路径对齐）
      { path: 'recipes', redirect: '/admin/recipe-audit' },
      { path: 'meal-plans', redirect: '/admin/meal-plan-audit' },
    ],
  },
  // 404 兜底：所有未匹配的路径重定向到首页
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

// 创建路由实例，使用 HTML5 History 模式（URL 不带 # 号）
const router = createRouter({
  history: createWebHistory(),
  routes,
})

/**
 * 全局路由守卫：权限控制
 * - requiresAuth 路由：需登录，未登录跳转到登录页（携带 redirect 参数）
 * - requiresAdmin 路由：需管理员角色，未登录跳转登录页，非管理员跳转首页
 */
router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem('token')
  const userStr = localStorage.getItem('user')
  let user = null
  try {
    user = userStr ? JSON.parse(userStr) : null
  } catch {
    user = null
  }

  // 登录态校验
  if (to.matched.some(record => record.meta.requiresAuth)) {
    if (!token || !user) {
      next({ path: '/login', query: { redirect: to.fullPath } })
      return
    }
  }

  // 管理员权限校验
  if (to.matched.some(record => record.meta.requiresAdmin)) {
    if (!token || !user) {
      next({ path: '/login', query: { redirect: to.fullPath } })
      return
    }
    if (user.role !== 'admin') {
      next('/')
      return
    }
  }

  next()
})

export default router