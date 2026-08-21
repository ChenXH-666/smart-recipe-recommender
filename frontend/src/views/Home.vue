<template>
  <div class="home-page">
    <div class="welcome-bar">
      <div class="welcome-info">
        <h2>{{ greeting }}</h2>
        <span class="subtitle">
          {{ userStore.isLoggedIn ? '欢迎回来，' + (userStore.user?.nickname || userStore.user?.username) + '！' : '欢迎使用智能菜谱推荐系统' }}
        </span>
      </div>
      <div class="quick-search">
        <el-input v-model="searchText" size="large" placeholder="搜索菜谱、食材或口味..." clearable @keyup.enter="handleSearch">
          <template #append>
            <el-button type="primary" @click="handleSearch">
              <el-icon><Search /></el-icon>
              搜索
            </el-button>
          </template>
        </el-input>
      </div>
    </div>

    <el-alert
      v-if="restrictionText && userStore.isLoggedIn"
      class="diet-banner"
      type="warning"
      :closable="false"
      show-icon
    >
      <template #title>
        已按你的忌口过滤：{{ restrictionText }}
        <el-button link type="primary" @click="$router.push('/user/preferences')">去设置</el-button>
      </template>
    </el-alert>

    <div class="stat-row" :class="{ 'three-col': userStore.isAdmin }">
      <div class="stat-card stat-blue" @click="$router.push('/recipes')">
        <div class="stat-icon">
          <el-icon :size="28"><DishDot /></el-icon>
        </div>
        <div class="stat-info">
          <h3>{{ stats.total_recipes }}</h3>
          <span>菜谱总数</span>
          <small v-if="stats.new_recipes_week" class="stat-sub">本周新增 {{ stats.new_recipes_week }}</small>
        </div>
      </div>
      <div class="stat-card stat-green" @click="$router.push('/meal-plans')">
        <div class="stat-icon">
          <el-icon :size="28"><Collection /></el-icon>
        </div>
        <div class="stat-info">
          <h3>{{ stats.total_meal_plans }}</h3>
          <span>套餐方案</span>
          <small v-if="stats.new_meal_plans_week" class="stat-sub">本周新增 {{ stats.new_meal_plans_week }}</small>
        </div>
      </div>
      <div v-if="userStore.isAdmin" class="stat-card stat-orange">
        <div class="stat-icon">
          <el-icon :size="28"><User /></el-icon>
        </div>
        <div class="stat-info">
          <h3>{{ stats.total_users }}</h3>
          <span>用户总数</span>
          <small v-if="stats.new_users_week" class="stat-sub">本周新增 {{ stats.new_users_week }}</small>
        </div>
      </div>
    </div>

    <div class="recipe-scroll" v-if="userStore.isLoggedIn && personalizedItems.length">
      <div class="scroll-header">
        <div>
          <h3>为你推荐</h3>
          <p>基于您的浏览历史和收藏偏好</p>
        </div>
        <el-button type="primary" plain @click="$router.push('/for-you')">
          查看更多
          <el-icon><ArrowRight /></el-icon>
        </el-button>
      </div>
      <div class="scroll-row">
        <RecipeCard v-for="item in personalizedItems" :key="item.id" :recipe="item" />
      </div>
    </div>

    <div class="recipe-scroll">
      <div class="scroll-header">
        <div>
          <h3>热门菜谱</h3>
          <p>本周最受欢迎的菜谱</p>
        </div>
        <el-button type="primary" plain @click="$router.push('/hot-recipes')">
          查看更多
          <el-icon><ArrowRight /></el-icon>
        </el-button>
      </div>
      <div class="scroll-row">
        <RecipeCard v-for="item in hotRecipes" :key="item.id" :recipe="item" />
      </div>
    </div>

    <el-card class="section-card">
      <template #header>
        <div class="section-title">
          <div>
            <h3>推荐套餐</h3>
            <p>精心搭配的完整菜单</p>
          </div>
          <el-button type="primary" plain @click="$router.push('/meal-plans')">
            查看更多
            <el-icon><ArrowRight /></el-icon>
          </el-button>
        </div>
      </template>
      <div class="plan-grid">
        <div v-for="plan in mealPlans" :key="plan.id" class="plan-card" @click="$router.push('/meal-plans/' + plan.id)">
          <div class="plan-icon">
            <el-icon :size="32"><Menu /></el-icon>
          </div>
          <div class="plan-content">
            <h4>{{ plan.title }}</h4>
            <p>{{ plan.description || '精心搭配的美味套餐' }}</p>
          </div>
          <el-icon class="plan-arrow"><ArrowRight /></el-icon>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '../stores/user'
import api from '../api'
import RecipeCard from '../components/RecipeCard.vue'

const router = useRouter()
const userStore = useUserStore()
const searchText = ref('')
const hotRecipes = ref([])
const mealPlans = ref([])
const personalizedItems = ref([])
const restrictionText = ref('')
const stats = ref({ total_recipes: 0, total_meal_plans: 0, total_users: 0, new_recipes_week: 0, new_meal_plans_week: 0, new_users_week: 0 })

// 根据当前时间返回问候语
const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 12) return '早上好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

function handleSearch() {
  if (!searchText.value.trim()) return
  // 首页搜索直接进入菜谱浏览检索（AI 对话统一走右下角 AI 助手悬浮入口）
  router.push({ path: '/recipes', query: { keyword: searchText.value } })
}

async function loadData() {
  try {
    // 推荐套餐：登录用户走 RAG 个性化评估接口，未登录用户走公开套餐列表
    const plansPromise = userStore.isLoggedIn
      ? api.get('/recommendations/meal-plans', { params: { limit: 6 } })
      : api.get('/meal-plans', { params: { page_size: 6 } })
    const [hotRes, plansRes] = await Promise.all([
      api.get('/recipes/hot', { params: { page_size: 8 } }),
      plansPromise,
    ])
    hotRecipes.value = hotRes.items || []
    mealPlans.value = plansRes.items || []
    // 若统计接口未返回（如启动中），先用列表 total 兜底
    if (!stats.value.total_recipes && !stats.value.total_meal_plans) {
      stats.value.total_recipes = hotRes.total || hotRecipes.value.length
      stats.value.total_meal_plans = plansRes.total || mealPlans.value.length
    }
  } catch (e) {
    console.error(e)
  }
  // 首页统计卡片（独立接口，失败不影响主内容展示）
  try {
    const res = await api.get('/stats')
    stats.value = res || stats.value
  } catch (e) {
    console.error(e)
  }
  if (userStore.isLoggedIn) {
    // 读取忌口偏好，用于顶部"已按你的忌口过滤"提示条
    try {
      const prefs = await api.get('/users/preferences')
      if (prefs.diet_tags && prefs.diet_tags.length) {
        const { formatDietTags } = await import('../utils/diet')
        restrictionText.value = formatDietTags(prefs.diet_tags)
      }
    } catch (e) {
      console.error(e)
    }
    try {
      const res = await api.get('/recommendations/personalized', { params: { limit: 8 } })
      personalizedItems.value = res.items || []
    } catch (e) {
      console.error(e)
    }
  }
}

onMounted(loadData)
</script>

<style scoped>
.home-page {
  max-width: 1400px;
}

.welcome-bar {
  background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%);
  color: #fff;
  border-radius: 8px;
  padding: 24px 32px;
  margin-bottom: 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 4px 16px rgba(37, 99, 235, 0.2);
}

.welcome-info h2 {
  font-size: 24px;
  font-weight: 600;
  margin-bottom: 4px;
}

.subtitle {
  font-size: 14px;
  opacity: 0.9;
}

.quick-search {
  width: 420px;
}

.quick-search :deep(.el-input__wrapper) {
  border-radius: 6px 0 0 6px;
  box-shadow: none;
}

.quick-search :deep(.el-input-group__append) {
  border-radius: 0 6px 6px 0;
}

.stat-row {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

/* 管理员显示三张卡（菜谱/套餐/用户）时平分为三列；非管理员两卡各占一半 */
.stat-row.three-col {
  grid-template-columns: repeat(3, 1fr);
}

.diet-banner {
  margin-bottom: 16px;
}

@media (max-width: 900px) {
  .stat-row {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* 移动端：欢迎栏纵向排列，搜索框占满整行 */
@media (max-width: 767px) {
  .welcome-bar {
    flex-direction: column;
    align-items: stretch;
    padding: 18px 20px;
    gap: 14px;
  }
  .quick-search {
    width: 100%;
  }
  .stat-row {
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  .stat-card {
    padding: 14px;
    gap: 10px;
  }
  .stat-icon {
    width: 44px;
    height: 44px;
  }
  .stat-info h3 {
    font-size: 22px;
  }
  .section-title {
    align-items: flex-start;
    gap: 8px;
  }
  .section-title p {
    line-height: 1.5;
  }
}

.stat-card {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  border: 1px solid #f0f0f0;
  transition: all 0.2s;
  cursor: pointer;
}

.stat-card:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
  transform: translateY(-2px);
}

.stat-icon {
  width: 56px;
  height: 56px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
}

.stat-blue .stat-icon { background: linear-gradient(135deg, #3b82f6, #2563eb); }
.stat-green .stat-icon { background: linear-gradient(135deg, #22c55e, #16a34a); }
.stat-orange .stat-icon { background: linear-gradient(135deg, #f59e0b, #d97706); }
.stat-teal .stat-icon { background: linear-gradient(135deg, #14b8a6, #0d9488); }

.stat-info h3 {
  font-size: 26px;
  font-weight: 700;
  color: #1f2937;
  margin: 0;
}

.stat-info span {
  font-size: 13px;
  color: #6b7280;
}

.stat-sub {
  display: block;
  margin-top: 2px;
  font-size: 12px;
  color: #9ca3af;
}

.section-card {
  margin-bottom: 20px;
  border-radius: 8px;
  border: 1px solid #ebeef5;
}

.section-title {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-title h3 {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
  margin: 0;
}

.section-title p {
  font-size: 13px;
  color: #9ca3af;
  margin: 4px 0 0;
}

.recipe-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
}

/* 横向单行滑动区（为你推荐 / 热门菜谱） */
.recipe-scroll {
  background: #fff;
  border-radius: 8px;
  border: 1px solid #ebeef5;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  margin-bottom: 16px;
  padding: 20px 20px 12px;
}
.scroll-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.scroll-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
}
.scroll-header p {
  margin: 4px 0 0;
  font-size: 13px;
  color: #909399;
}
.scroll-row {
  display: flex;
  gap: 16px;
  overflow-x: auto;
  padding-bottom: 8px;
  scrollbar-width: none;
  -webkit-overflow-scrolling: touch;
  scroll-snap-type: x mandatory;
}
.scroll-row::-webkit-scrollbar {
  display: none;
}
.scroll-row :deep(.recipe-card) {
  flex: 0 0 240px;
  scroll-snap-align: start;
  scroll-snap-stop: always;
}

.plan-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 12px;
}

.plan-card {
  background: #f8fafc;
  padding: 20px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  gap: 16px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.plan-card:hover {
  background: #eff6ff;
  border-color: #bfdbfe;
}

.plan-icon {
  width: 48px;
  height: 48px;
  background: #2563eb;
  color: #fff;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.plan-content {
  flex: 1;
  min-width: 0;
}

.plan-content h4 {
  font-size: 15px;
  color: #1f2937;
  margin: 0 0 4px;
}

.plan-content p {
  font-size: 13px;
  color: #6b7280;
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.plan-arrow {
  color: #9ca3af;
  font-size: 16px;
}
</style>