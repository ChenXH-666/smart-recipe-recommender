<template>
  <div class="main-layout">
    <!-- ===== 顶部导航栏 ===== -->
    <div class="layout-header">
      <div class="header-left" @click="$router.push('/')">
        <div class="logo">
          <el-icon :size="28" color="#fff"><DishDot /></el-icon>
          <span class="logo-text">智能菜谱推荐系统</span>
        </div>
      </div>
      <!-- 移动端：导航以横向滑动标签栏展示于下方独立一行，无需汉堡按钮 -->
      <div class="header-center">
        <el-menu
          mode="horizontal"
          :default-active="activeMenu"
          @select="handleMenu"
          :ellipsis="false"
          class="header-menu"
          background-color="transparent"
          text-color="#fff"
          active-text-color="#fff"
        >
          <el-menu-item index="/">首页</el-menu-item>
          <el-menu-item index="/recipes">菜谱浏览</el-menu-item>
          <el-menu-item index="/meal-plans">套餐广场</el-menu-item>
          <el-menu-item index="/cooking-notes">烹饪心得</el-menu-item>
        </el-menu>
      </div>
      <div class="header-right">
        <template v-if="userStore.isLoggedIn">
          <el-dropdown @command="handleCommand">
            <span class="user-info">
              <el-avatar :size="34" :src="userStore.user?.avatar_url || undefined" :icon="User" style="background:#409EFF" />
              <span class="user-name">{{ userStore.user?.nickname || userStore.user?.username }}</span>
              <el-icon><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="profile">
                  <el-icon><User /></el-icon>个人中心
                </el-dropdown-item>
                <el-dropdown-item v-if="userStore.isAdmin" command="admin" divided>
                  <el-icon><Setting /></el-icon>后台管理
                </el-dropdown-item>
                <el-dropdown-item command="logout" divided>
                  <el-icon><SwitchButton /></el-icon>退出登录
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
        <template v-else>
          <el-button type="primary" @click="$router.push('/login')">登录</el-button>
          <el-button type="primary" @click="$router.push('/register')">注册</el-button>
        </template>
      </div>
    </div>

    <!-- ===== 主体内容区 ===== -->
    <div class="layout-body">
      <div class="layout-main">
        <!-- 面包屑导航 -->
        <div class="breadcrumb-bar">
          <el-breadcrumb separator="/">
            <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
            <el-breadcrumb-item
              v-for="(item, idx) in breadcrumbs"
              :key="idx"
              :to="item.path ? { path: item.path } : undefined"
            >
              {{ item.name }}
            </el-breadcrumb-item>
          </el-breadcrumb>
        </div>

        <!-- 页面内容（带淡入淡出过渡，:key 强制同级路由切换时重新渲染） -->
        <div class="page-content">
          <router-view v-slot="{ Component, route }">
            <component :is="Component" :key="route.path" />
          </router-view>
        </div>
      </div>
    </div>

    <!-- ===== 菜谱合集悬浮入口 + AI 助手悬浮按钮（仅登录用户可见） ===== -->
    <div class="float-stack" v-if="userStore.isLoggedIn">
      <el-tooltip content="菜谱合集（一键生成套餐）" placement="left">
        <div class="cart-float" @click="cartVisible = true">
          <el-icon :size="24"><Collection /></el-icon>
          <span v-if="cart.count" class="cart-badge">{{ cart.count }}</span>
        </div>
      </el-tooltip>
      <el-tooltip content="待做清单" placement="left">
        <div class="todo-float" @click="todoVisible = true">
          <el-icon :size="24"><Timer /></el-icon>
          <span v-if="todo.count" class="cart-badge">{{ todo.count }}</span>
        </div>
      </el-tooltip>
      <el-tooltip content="AI 烹饪助手" placement="left">
        <div class="ai-float" @click="aiChatStore.open()">
          <el-icon :size="24"><ChatDotSquare /></el-icon>
        </div>
      </el-tooltip>
    </div>

    <!-- A：菜谱合集（收集菜谱 → 一键生成套餐） -->
    <el-dialog v-model="cartVisible" title="菜谱合集（一键生成套餐）" width="520px" align-center>
      <p v-if="!cart.count" class="cart-empty">
        还没有选菜。去菜谱列表点卡片右上角第一个图标收集，随后一键生成套餐。
      </p>
      <div v-else class="cart-list">
        <div v-for="it in cart.items" :key="it.id" class="cart-row">
          <span class="cart-title">{{ it.title }}</span>
          <el-button size="small" type="danger" plain circle @click="cart.remove(it.id)">
            <el-icon><Close /></el-icon>
          </el-button>
        </div>
      </div>
      <div class="cart-actions">
        <el-button @click="cart.clear()" :disabled="!cart.count">清空</el-button>
        <el-button type="primary" :disabled="!cart.count" @click="createPlanFromCart">
          <el-icon><Plus /></el-icon>一键生成套餐
        </el-button>
      </div>
    </el-dialog>

    <!-- B：待做清单（暂存近期想做的菜） -->
    <el-dialog v-model="todoVisible" title="待做清单" width="520px" align-center>
      <p v-if="!todo.count" class="cart-empty">
        还没有待做的菜。在菜谱卡片上点时钟图标，把下一顿/近期想做的菜先收进来。
      </p>
      <div v-else class="cart-list">
        <div v-for="it in todo.items" :key="it.id" class="cart-row">
          <span class="cart-title">{{ it.title }}</span>
          <el-button size="small" type="danger" plain circle @click="todo.remove(it.id)">
            <el-icon><Close /></el-icon>
          </el-button>
        </div>
      </div>
      <div class="cart-actions">
        <el-button @click="todo.clear()" :disabled="!todo.count">清空</el-button>
        <el-button type="primary" plain @click="router.push('/user/todo'); todoVisible = false">查看全部</el-button>
      </div>
    </el-dialog>

    <!-- AI 对话侧边栏（Drawer 形式） -->
    <AiChatDialog :visible="aiChatStore.visible" @update:visible="(v) => { if (!v) aiChatStore.close() }" />
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '../stores/user'
import { useAiChatStore } from '../stores/aiChat'
import { useRecipeCartStore } from '../stores/recipeCart'
import { useTodoListStore } from '../stores/todoList'
import { ElMessage } from 'element-plus'
import AiChatDialog from '../components/AiChatDialog.vue'
import { User } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const aiChatStore = useAiChatStore()
const cart = useRecipeCartStore()
const todo = useTodoListStore()
const cartVisible = ref(false)
const todoVisible = ref(false)

// 一键生成套餐：跳转到套餐创建页预填（不立即清合集，成功提交套餐后再清）
function createPlanFromCart() {
  if (!cart.count) return
  const ids = cart.items.map((i) => i.id).join(',')
  cartVisible.value = false
  router.push(`/meal-plans/create?recipe_ids=${ids}`)
}

console.log('[MainLayout] loaded with :key fix, route.path =', route.path)

// 路由切换时清除残留的 ElMessage 通知
// 原因：MainLayout 的 :key="route.path" 会强制同级路由切换时重新渲染组件，
// 这会打断 ElMessage 的自动关闭计时器，导致 toast 跨页面残留
watch(
  () => route.path,
  () => {
    ElMessage.closeAll()
  }
)

// 导航栏高亮：根据当前路径匹配导航菜单项。
// 后台管理与个人中心不属于顶部四个主导航，返回空串以免误高亮「菜谱浏览/首页」
const activeMenu = computed(() => {
  const p = route.path
  if (p.startsWith('/admin')) return ''
  if (p.startsWith('/user')) return ''
  if (p.startsWith('/recipes')) return '/recipes'
  if (p.startsWith('/meal-plans')) return '/meal-plans'
  if (p.startsWith('/cooking-notes') || p.startsWith('/notes')) return '/cooking-notes'
  return '/'
})

// 面包屑：根据路径映射中文名称。
// 后台管理子页面返回两级（后台管理 → 具体管理），且「后台管理」可点击返回仪表盘。
// 其余路径保持单级，无跳转链接。
const breadcrumbs = computed(() => {
  const p = route.path
  if (p === '/' || p === '') return []
  const adminPages = {
    'admin/recipe-audit': '菜谱审核',
    'admin/meal-plan-audit': '套餐审核',
    'admin/users': '用户管理',
    'admin/tags': '标签管理',
    'admin/ingredients': '食材管理',
  }
  const key = p.slice(1)
  // 后台管理子页面：返回「后台管理 → 具体管理」两级
  if (adminPages[key]) {
    return [
      { name: '后台管理', path: '/admin' },
      { name: adminPages[key] },
    ]
  }
  // 个人中心子页面：返回「个人中心 → 具体页面」两级，个人中心可点击回资料页
  const userPages = {
    'user/profile': '个人主页',
    'user/todo': '待做清单',
    'user/favorites': '我的收藏',
    'user/history': '浏览历史',
    'user/conversations': 'AI对话记录',
    'user/preferences': '偏好设置',
    'user/my-recipes': '我的菜谱',
    'user/my-meal-plans': '我的套餐',
  }
  if (userPages[key]) {
    return [
      { name: '个人中心', path: '/user/profile' },
      { name: userPages[key] },
    ]
  }
  const map = {
    admin: { name: '后台管理' },
    'for-you': { name: '为你推荐' },
    'hot-recipes': { name: '热门菜谱' },
    recipes: { name: '菜谱浏览' },
    'recipes/create': { name: '创建菜谱' },
    'meal-plans': { name: '套餐广场' },
    'meal-plans/create': { name: '创建套餐' },
    'cooking-notes': { name: '烹饪心得' },
  }
  if (map[key]) return [map[key]]
  // 菜谱编辑页：/recipes/:id/edit → 编辑菜谱
  if (route.params.id && key.endsWith('/edit')) return [{ name: '菜谱浏览' }, { name: '编辑菜谱' }]
  // 套餐编辑页：复用 /meal-plans/create，通过 ?id= 进入编辑态
  if (key === 'meal-plans/create' && route.query.id) return [{ name: '套餐广场' }, { name: '编辑套餐' }]
  if (route.params.id && key.startsWith('recipes/')) return [{ name: '菜谱浏览' }, { name: '菜谱详情' }]
  if (route.params.id && key.startsWith('meal-plans/')) return [{ name: '套餐广场' }, { name: '套餐详情' }]
  return []
})

function handleMenu(index) {
  router.push(index)
}

/**
 * 下拉菜单命令处理
 * - 大部分选项路径为 /user/{cmd}（profile, favorites, history, conversations）
 * - admin 特殊处理：直接跳转 /admin
 * - logout 特殊处理：调用 store logout 后跳转首页
 */
function handleCommand(cmd) {
  if (cmd === 'logout') {
    userStore.logout()
    router.push('/')
  } else if (cmd === 'admin') {
    router.push('/admin')
  } else {
    router.push(`/user/${cmd}`)
  }
}
</script>

<style scoped>
.main-layout {
  min-height: 100vh;
  background: #f0f2f5;
}

.layout-header {
  height: 60px;
  background: linear-gradient(90deg, #1e3a8a 0%, #2563eb 100%);
  display: flex;
  align-items: center;
  padding: 0 24px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-left {
  cursor: pointer;
}

.logo {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-text {
  font-size: 18px;
  font-weight: 700;
  color: #fff;
  letter-spacing: 1px;
  white-space: nowrap;
}

.header-center {
  flex: 1;
  display: flex;
  justify-content: center;
}

.header-menu {
  border-bottom: none !important;
  height: 60px;
}

.header-menu :deep(.el-menu-item) {
  height: 60px;
  line-height: 60px;
  font-size: 15px;
  margin: 0 8px;
}

.header-menu :deep(.el-menu-item:hover) {
  background: rgba(255, 255, 255, 0.12) !important;
}

.header-menu :deep(.el-menu-item.is-active) {
  background: rgba(255, 255, 255, 0.2) !important;
  font-weight: 600;
  border-bottom: 3px solid #fcd34d !important;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.header-right :deep(.el-button) {
  border-color: rgba(255, 255, 255, 0.6);
  color: #fff;
}

.header-right :deep(.el-button:hover) {
  background: rgba(255, 255, 255, 0.15);
  color: #fff;
  border-color: #fff;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #fff;
  cursor: pointer;
  padding: 6px 12px;
  border-radius: 4px;
  transition: background 0.2s;
}

.user-info:hover {
  background: rgba(255, 255, 255, 0.15);
}

.user-name {
  font-size: 14px;
  font-weight: 500;
}

.layout-body {
  min-height: calc(100vh - 60px);
}

.layout-main {
  max-width: 1400px;
  margin: 0 auto;
  padding: 20px 24px;
}

.breadcrumb-bar {
  background: #fff;
  padding: 12px 20px;
  border-radius: 4px;
  margin-bottom: 16px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}

.page-content {
  min-height: 500px;
}

.float-stack {
  position: fixed;
  right: 30px;
  bottom: 40px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  z-index: 50;
}

.cart-float {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: #ffffff;
  color: #2563eb;
  border: 2px solid #2563eb;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  position: relative;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.15);
  transition: all 0.25s;
}
.cart-float:hover {
  transform: translateY(-2px);
  background: #eff6ff;
}
.todo-float {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: #ffffff;
  color: #f59e0b;
  border: 2px solid #f59e0b;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  position: relative;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.15);
  transition: all 0.25s;
}
.todo-float:hover {
  transform: translateY(-2px);
  background: #fff7e6;
}
.cart-badge {
  position: absolute;
  top: -5px;
  right: -5px;
  min-width: 18px;
  height: 18px;
  padding: 0 4px;
  border-radius: 9px;
  background: #ef4444;
  color: #fff;
  font-size: 11px;
  line-height: 18px;
  text-align: center;
}

.cart-empty {
  color: #909399;
  text-align: center;
  margin: 0;
}
.cart-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}
.cart-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 50vh;
  overflow-y: auto;
}
.cart-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid #eef2f7;
  border-radius: 6px;
}
.cart-title {
  font-weight: 500;
  color: #1f2937;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ai-float {
  width: 56px;
  height: 56px;
  border-radius: 50%;
  background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 4px 16px rgba(37, 99, 235, 0.4);
  transition: all 0.25s;
  z-index: 50;
}

.ai-float:hover {
  transform: translateY(-3px) scale(1.05);
  box-shadow: 0 8px 24px rgba(37, 99, 235, 0.5);
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* ===== 响应式断点：≤900px 时启用移动端导航布局 ===== */
@media (max-width: 900px) {
  .layout-header {
    padding: 0 12px;
    flex-wrap: wrap;
    height: auto;
    min-height: 60px;
  }

  .logo-text {
    font-size: 15px;
  }

  /* 移动端导航：四个入口做成一行、超出左右滑动的横向标签栏 */
  .header-center {
    order: 3;
    width: 100%;
    max-height: none;
    overflow-x: auto;
    overflow-y: hidden;
    flex: none;
    display: flex;
    align-items: center;
    justify-content: flex-start;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
  }

  .header-center::-webkit-scrollbar {
    display: none;
  }

  .header-menu {
    height: auto;
    display: flex;
    flex-direction: row;
    flex-wrap: nowrap;
    width: max-content;
  }

  .header-menu :deep(.el-menu-item) {
    height: 48px;
    line-height: 48px;
    flex-shrink: 0;
    white-space: nowrap;
  }

  .header-right {
    margin-left: auto;
  }

  .user-name {
    display: none;
  }

  .layout-main {
    padding: 12px;
  }

  .float-stack {
    right: 16px;
    bottom: 24px;
  }
  .cart-float,
  .ai-float {
    width: 48px;
    height: 48px;
  }
}
</style>