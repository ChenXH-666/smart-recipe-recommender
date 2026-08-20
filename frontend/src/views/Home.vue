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

    <div class="stat-row">
      <div class="stat-card stat-blue">
        <div class="stat-icon">
          <el-icon :size="28"><DishDot /></el-icon>
        </div>
        <div class="stat-info">
          <h3>{{ stats.total_recipes }}</h3>
          <span>菜谱总数</span>
          <small v-if="stats.new_recipes_week" class="stat-sub">本周新增 {{ stats.new_recipes_week }}</small>
        </div>
      </div>
      <div class="stat-card stat-green">
        <div class="stat-icon">
          <el-icon :size="28"><Collection /></el-icon>
        </div>
        <div class="stat-info">
          <h3>{{ stats.total_meal_plans }}</h3>
          <span>套餐方案</span>
          <small v-if="stats.new_meal_plans_week" class="stat-sub">本周新增 {{ stats.new_meal_plans_week }}</small>
        </div>
      </div>
      <div class="stat-card stat-orange">
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

    <el-card class="section-card">
      <template #header>
        <div class="section-title">
          <div>
            <h3>AI 智能推荐</h3>
            <p v-if="userStore.isLoggedIn">试试对 AI 说一段话，它将为您推荐最合适的菜谱</p>
            <p v-else>描述你的需求获取推荐候选，登录后可解锁 AI 个性化解读</p>
          </div>
        </div>
      </template>
      <div class="ai-search">
        <el-input
          ref="aiInputRef"
          v-model="aiQuery"
          type="textarea"
          :rows="2"
          placeholder="例如：我想做一顿简单又好吃的家常菜，预算50元以内..."
        />
        <el-button type="primary" :loading="aiLoading" @click="goAiSearch" style="margin-top: 12px">
          <el-icon><MagicStick /></el-icon>
          AI 智能推荐
        </el-button>
      </div>
      <div class="quick-tags">
        <!-- 个性化"猜你想问"：登录后按用户偏好动态更新；点击仅把问题填入输入框 -->
        <el-tag
          v-for="tag in quickTags"
          :key="tag.label"
          class="qt"
          @click="fillQuickSuggest(tag.label)"
          effect="plain"
        >
          {{ tag.label }}
        </el-tag>
      </div>
    </el-card>

    <el-card class="section-card" v-if="userStore.isLoggedIn && personalizedItems.length">
      <template #header>
        <div class="section-title">
          <div>
            <h3>为你推荐</h3>
            <p>基于您的浏览历史和收藏偏好</p>
          </div>
        </div>
      </template>
      <div class="recipe-grid">
        <RecipeCard v-for="item in personalizedItems" :key="item.id" :recipe="item" />
      </div>
    </el-card>

    <el-card class="section-card">
      <template #header>
        <div class="section-title">
          <div>
            <h3>热门菜谱</h3>
            <p>本周最受欢迎的菜谱</p>
          </div>
          <el-button type="primary" plain @click="$router.push('/recipes')">
            查看更多
            <el-icon><ArrowRight /></el-icon>
          </el-button>
        </div>
      </template>
      <div class="recipe-grid">
        <RecipeCard v-for="item in hotRecipes" :key="item.id" :recipe="item" />
      </div>
    </el-card>

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

    <el-dialog v-model="showAiResult" title="AI 智能推荐" width="600px">
      <div v-if="aiCandidates.length" style="margin-bottom: 16px">
        <p style="margin-bottom: 12px; color: #374151">为你找到以下推荐：</p>
        <div class="candidate-list">
          <div v-for="c in aiCandidates" :key="c.id" class="candidate-card" @click="$router.push('/recipes/' + c.id)">
            <div class="cand-title">{{ c.title }}</div>
            <div class="cand-meta">
              <el-tag size="small" v-if="c.difficulty" effect="plain">{{ difficultyText(c.difficulty) }}</el-tag>
              <span v-if="c.cooking_time"><el-icon><Timer /></el-icon> {{ c.cooking_time }} 分钟</span>
              <span v-if="c.estimated_cost"><el-icon><Coin /></el-icon> ¥{{ c.estimated_cost }}</span>
            </div>
          </div>
        </div>
      </div>
      <div v-if="aiResponse" class="ai-response">
        <el-icon><ChatDotSquare /></el-icon>
        <div class="markdown-body" v-html="renderMarkdown(aiResponse)"></div>
      </div>
      <div v-if="aiLoading" style="text-align: center; padding: 30px">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <p style="margin-top: 12px; color: #6b7280">AI 正在为你推荐...</p>
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '../stores/user'
import api from '../api'
import { streamSSE } from '../utils/sse'
import { renderMarkdown } from '../utils/markdown'
import RecipeCard from '../components/RecipeCard.vue'

const router = useRouter()
const userStore = useUserStore()
const searchText = ref('')
const hotRecipes = ref([])
const mealPlans = ref([])
const personalizedItems = ref([])
const restrictionText = ref('')
const stats = ref({ total_recipes: 0, total_meal_plans: 0, total_users: 0, new_recipes_week: 0, new_meal_plans_week: 0, new_users_week: 0 })

const aiQuery = ref('')
const aiInputRef = ref(null)
const showAiResult = ref(false)
const aiLoading = ref(false)
const aiResponse = ref('')
const aiCandidates = ref([])

// 通用"猜你想问"预设备题（未登录/无偏好时兜底）
const defaultQuickTags = [
  { label: '减脂晚餐', prompt: '帮我推荐几道适合减脂的晚餐，健康又美味' },
  { label: '快手家常菜', prompt: '我想做几道快手家常菜，简单省时' },
  { label: '川菜', prompt: '我想吃川菜，帮我推荐几道正宗又好吃的' },
  { label: '高蛋白', prompt: '帮我推荐几道高蛋白的菜' },
  { label: '50元以内', prompt: '我想在50元以内做一顿二人餐，帮我搭配' },
]
// 个性化"猜你想问"：登录后由后端按收藏/浏览/点评动态生成
const quickTags = ref(defaultQuickTags)

// 点击预设标签：仅把预设问题填入输入框并聚焦，不自动触发 AI 推荐
function fillQuickSuggest(label) {
  const target = quickTags.value.find((t) => t.label === label)
  aiQuery.value = target ? target.prompt : label
  nextTick(() => aiInputRef.value?.focus())
}

const difficultyMap = { easy: '简单', medium: '中等', hard: '困难' }

// 根据当前时间返回问候语
const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 12) return '早上好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

function difficultyText(d) {
  return difficultyMap[d] || d
}

function handleSearch() {
  if (!searchText.value.trim()) return
  // 检测自然语言查询（包含推荐、帮我等关键词），优先走 AI 推荐
  if (userStore.isLoggedIn && /推荐|帮|给我|一顿|想|吃什么|设计|搭配/.test(searchText.value)) {
    aiQuery.value = searchText.value
    goAiSearch()
    return
  }
  router.push({ path: '/recipes', query: { keyword: searchText.value } })
}

/**
 * AI 智能搜索
 * ============
 * 分两种模式（PRD 4.1：游客可获取推荐候选，仅不可发起 AI 多轮对话）：
 *   - 游客：调用免认证的 POST /recommendations/query，仅返回候选菜谱（无 AI 流式对话）
 *   - 登录用户：调用 POST /recommendations/stream-recommend（SSE 流式），
 *     先下发 [CANDIDATES] 候选，再逐 chunk 推送 AI 推荐语
 *
 * SSE 流式读取统一走 utils/sse.js 的 streamSSE（消除重复的 fetch+ReadableStream 代码）
 */
async function goAiSearch() {
  if (!aiQuery.value.trim()) return
  showAiResult.value = true
  aiLoading.value = true
  aiResponse.value = ''
  aiCandidates.value = []

  // 游客：免认证候选推荐
  if (!userStore.isLoggedIn) {
    try {
      const res = await api.post('/recommendations/query', { query: aiQuery.value })
      aiCandidates.value = res.items || []
      aiResponse.value = aiCandidates.value.length
        ? '以上为基于关键词的推荐候选，登录后可获取 AI 个性化解读与多轮对话。'
        : '未找到匹配菜谱，试试换个描述吧～'
    } catch (e) {
      aiResponse.value = '推荐服务暂时不可用，请稍后再试。'
    } finally {
      aiLoading.value = false
    }
    return
  }

  // 登录用户：SSE 流式推荐
  try {
    let aiText = ''
    await streamSSE({
      url: '/api/recommendations/stream-recommend',
      body: { query: aiQuery.value },
      onCandidate: (candidates) => { aiCandidates.value = candidates || [] },
      onChunk: (text) => {
        aiText += text
        aiResponse.value = aiText
      },
    })
    if (!aiResponse.value && !aiCandidates.value.length) {
      aiResponse.value = '未找到匹配菜谱，试试换个描述吧～'
    }
  } catch (e) {
    if (e && e.name === 'AbortError') return
    aiResponse.value = 'AI 服务暂时不可用，请稍后重试。'
  } finally {
    aiLoading.value = false
  }
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
    // 加载个性化"猜你想问"预设备题（失败则保持通用列表）
    try {
      const res = await api.get('/recommendations/prompts', { params: { limit: 6 } })
      if (res.items && res.items.length) quickTags.value = res.items
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
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}

.diet-banner {
  margin-bottom: 16px;
}

@media (max-width: 900px) {
  .stat-row {
    grid-template-columns: repeat(2, 1fr);
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

.ai-search {
  background: #f8fafc;
  border-radius: 6px;
  padding: 16px;
  margin-bottom: 12px;
}

.recipe-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
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

.quick-tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  padding-top: 8px;
}

.qt {
  cursor: pointer;
  transition: all 0.2s;
}

.qt:hover {
  transform: translateY(-1px);
}

.candidate-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.candidate-card {
  background: #f8fafc;
  padding: 14px 16px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s;
}

.candidate-card:hover {
  background: #eff6ff;
}

.cand-title {
  font-weight: 500;
  color: #1f2937;
  margin-bottom: 6px;
}

.cand-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #6b7280;
  align-items: center;
}

.cand-meta span {
  display: flex;
  align-items: center;
  gap: 4px;
}

.ai-response {
  background: #f0f9ff;
  padding: 14px 16px;
  border-radius: 6px;
  display: flex;
  gap: 10px;
  color: #1e40af;
  line-height: 1.7;
}

.ai-response p {
  flex: 1;
  margin: 0;
}
</style>