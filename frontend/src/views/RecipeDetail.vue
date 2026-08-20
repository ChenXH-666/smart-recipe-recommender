<template>
  <div class="recipe-detail-page" v-loading="loading">
    <!-- 菜谱不存在的兜底提示 -->
    <el-card v-if="!loading && !recipe" shadow="never" class="not-found-card">
      <el-empty description="菜谱不存在或已被删除">
        <el-button type="primary" @click="$router.push('/recipes')">返回菜谱列表</el-button>
      </el-empty>
    </el-card>
    <template v-if="recipe">
      <!-- 顶部内容 -->
      <el-card class="detail-hero" shadow="never">
        <div class="hero-layout">
          <div class="hero-image" v-if="recipe.cover_image_url">
            <img :src="recipe.cover_image_url" :alt="recipe.title" />
          </div>
          <div class="hero-image" v-else>
            <el-icon :size="96"><Picture /></el-icon>
          </div>
          <div class="hero-info">
            <h1 class="title">{{ recipe.title }}</h1>
            <p class="description" v-if="recipe.description">{{ recipe.description }}</p>
            <div class="meta-row">
              <el-tag v-if="recipe.difficulty" :type="difficultyTypeMap[recipe.difficulty]" effect="light" size="large">
                {{ difficultyMap[recipe.difficulty] }}
              </el-tag>
              <span v-if="recipe.cooking_time" class="meta-item">
                <el-icon><Timer /></el-icon>
                烹饪 {{ recipe.cooking_time }} 分钟
              </span>
              <span v-if="recipe.servings" class="meta-item">
                <el-icon><UserFilled /></el-icon>
                {{ recipe.servings }} 人份
              </span>
              <span v-if="recipe.estimated_cost" class="meta-item">
                <el-icon><Coin /></el-icon>
                约 ¥{{ recipe.estimated_cost }}
              </span>
              <span class="meta-item" v-if="recipe.view_count">
                <el-icon><View /></el-icon>
                {{ recipe.view_count }} 次浏览
              </span>
            </div>
            <div class="tag-row" v-if="recipe.tags && recipe.tags.length">
              <el-tag v-for="tag in recipe.tags" :key="tag.id" size="default" effect="plain" class="t">
                <el-icon><PriceTag /></el-icon>
                {{ tag.name }}
              </el-tag>
            </div>
            <div class="action-row">
              <!-- 仅在菜谱已审核通过时才显示收藏按钮：pending/rejected 资源后端会拒绝收藏，避免按钮点击后报错 -->
              <el-button v-if="userStore.isLoggedIn && recipe.status === 'approved'" :type="isFaved ? 'warning' : 'primary'" @click="toggleFavorite">
                <el-icon><Star /></el-icon>
                {{ isFaved ? '已收藏' : '收藏' }}
              </el-button>
              <!-- 作者查看未通过审核的菜谱时给出状态提示，避免用户困惑为何不能收藏 -->
              <el-tag v-else-if="userStore.isLoggedIn && recipe.status !== 'approved'" :type="recipe.status === 'pending' ? 'warning' : 'danger'" effect="plain" size="default">
                {{ recipe.status === 'pending' ? '审核中，暂不可收藏' : '审核未通过，暂不可收藏' }}
              </el-tag>
              <el-button v-if="canEdit" type="success" @click="$router.push('/recipes/' + recipe.id + '/edit')">
                <el-icon><Edit /></el-icon>
                编辑菜谱
              </el-button>
              <el-button
                v-if="userStore.isLoggedIn && recipe.status === 'approved'"
                :type="cart.inCart(recipe.id) ? 'warning' : 'default'"
                plain
                @click="cart.toggle(recipe)"
              >
                <el-icon><ShoppingCart /></el-icon>
                {{ cart.inCart(recipe.id) ? '已在菜谱合集' : '加入菜谱合集' }}
              </el-button>
              <el-button plain @click="$router.push({ path: '/cooking-notes', query: { recipe_id: recipe.id } })">
                <el-icon><ChatDotRound /></el-icon>
                相关烹饪心得
              </el-button>
              <span class="author-info" v-if="recipe.author_nickname">
                <el-avatar :size="32" :src="recipe.author_avatar_url || undefined" :icon="User" style="background:#2563eb" />
                <span>{{ recipe.author_nickname }}</span>
              </span>
            </div>
          </div>
        </div>
      </el-card>

      <!-- 主体内容 -->
      <el-row :gutter="16" class="content-row">
        <el-col :span="18">
          <!-- 食材清单 -->
          <el-card class="section-card" shadow="never">
            <template #header>
              <div class="section-header">
                <el-icon><KnifeFork /></el-icon>
                <h3>食材清单</h3>
              </div>
            </template>
            <el-table :data="recipe.ingredients || []" size="default" style="width:100%">
              <el-table-column prop="ingredient.name" label="食材" min-width="140" />
              <el-table-column prop="quantity" label="用量" width="140" align="center" />
              <el-table-column prop="note" label="备注" />
            </el-table>
            <div v-if="!recipe.ingredients || recipe.ingredients.length === 0" class="empty-inline">
              暂无食材信息
            </div>
          </el-card>

          <el-alert
            v-if="userStore.isLoggedIn && recipe.diet_warnings && recipe.diet_warnings.length"
            type="warning"
            :closable="false"
            show-icon
            class="diet-warning"
          >
            <template #title>
              注意：本菜谱含你可能忌口的食材：{{ recipe.diet_warnings.join('、') }}
            </template>
          </el-alert>

          <!-- 营养估算 -->
          <el-card v-if="recipe.nutrition" class="section-card" shadow="never">
            <template #header>
              <div class="section-header">
                <el-icon><Odometer /></el-icon>
                <h3>营养估算</h3>
                <span class="section-badge">约 {{ recipe.servings || 1 }} 人份 · 估算值</span>
              </div>
            </template>
            <div class="nutrition-grid">
              <div class="nut-item">
                <span class="nut-val">{{ recipe.nutrition.kcal ?? '-' }}</span>
                <span class="nut-unit">kcal</span>
                <span class="nut-label">热量</span>
              </div>
              <div class="nut-item">
                <span class="nut-val">{{ recipe.nutrition.protein ?? '-' }}</span>
                <span class="nut-unit">g</span>
                <span class="nut-label">蛋白质</span>
              </div>
              <div class="nut-item">
                <span class="nut-val">{{ recipe.nutrition.fat ?? '-' }}</span>
                <span class="nut-unit">g</span>
                <span class="nut-label">脂肪</span>
              </div>
              <div class="nut-item">
                <span class="nut-val">{{ recipe.nutrition.carbs ?? '-' }}</span>
                <span class="nut-unit">g</span>
                <span class="nut-label">碳水</span>
              </div>
            </div>
          </el-card>

          <!-- 烹饪步骤 -->
          <el-card class="section-card" shadow="never">
            <template #header>
              <div class="section-header">
                <el-icon><DocumentCopy /></el-icon>
                <h3>烹饪步骤</h3>
              </div>
            </template>
            <el-timeline v-if="recipe.steps && recipe.steps.length">
              <el-timeline-item
                v-for="step in recipe.steps"
                :key="step.step_number"
                :timestamp="'步骤 ' + step.step_number"
                placement="top"
                :color="'#2563eb'"
              >
                <div class="step-item">
                  <p>{{ step.instruction }}</p>
                  <el-tag v-if="step.duration" size="small" effect="plain" type="warning" class="step-duration">
                    <el-icon><Timer /></el-icon>
                    {{ step.duration }} 分钟
                  </el-tag>
                </div>
              </el-timeline-item>
            </el-timeline>
            <div v-else class="empty-inline">
              暂无步骤信息
            </div>
          </el-card>

          <!-- 点评 -->
          <el-card class="section-card" shadow="never">
            <template #header>
              <div class="section-header">
                <el-icon><ChatDotRound /></el-icon>
                <h3>用户点评 ({{ reviewsTotal }})</h3>
              </div>
              <el-button v-if="userStore.isLoggedIn && !showReviewForm && !hasReviewed" type="primary" size="small" @click="showReviewForm = true">
                <el-icon><Edit /></el-icon>
                写点评
              </el-button>
              <el-tag v-else-if="hasReviewed" type="info" size="small" effect="plain">
                <el-icon><CircleCheck /></el-icon>
                已点评
              </el-tag>
            </template>
            <div v-if="showReviewForm" class="review-form">
              <el-rate v-model="reviewForm.rating" show-score />
              <el-input
                v-model="reviewForm.content"
                type="textarea"
                :rows="3"
                placeholder="分享你的烹饪体验与心得..."
                style="margin-top: 8px"
              />
              <div style="margin-top: 8px; text-align: right">
                <el-button size="small" @click="showReviewForm = false">取消</el-button>
                <el-button size="small" type="primary" @click="submitReview">提交</el-button>
              </div>
            </div>
            <div v-if="reviews.length === 0 && !showReviewForm" class="empty-inline">
              暂无点评，快来做第一个分享体验的人吧～
            </div>
            <div v-for="r in reviews" :key="r.id" class="review-item">
              <div class="review-header">
                <el-avatar :size="36" :src="r.user_avatar_url || undefined" :icon="User" style="background:#606266" />
                <div class="review-user">
                  <strong>{{ r.username }}</strong>
                  <el-rate :model-value="r.rating" disabled show-score size="small" />
                </div>
                <span class="review-time">{{ formatDate(r.created_at) }}</span>
              </div>
              <p class="review-content">{{ r.content }}</p>
            </div>
          </el-card>
        </el-col>

        <el-col :span="6">
          <!-- 相关心得 -->
          <el-card class="section-card" shadow="never" v-if="relatedNotes && relatedNotes.length">
            <template #header>
              <div class="section-header">
                <el-icon><Document /></el-icon>
                <h3>相关心得</h3>
              </div>
            </template>
            <div v-for="note in relatedNotes" :key="note.id" class="note-item" @click="$router.push('/cooking-notes/' + note.id)">
              <h4>{{ note.title }}</h4>
              <p v-if="note.content">{{ truncate(note.content, 60) }}</p>
            </div>
          </el-card>

          <!-- 系统信息 -->
          <el-card class="section-card" shadow="never">
            <template #header>
              <div class="section-header">
                <el-icon><InfoFilled /></el-icon>
                <h3>菜谱信息</h3>
              </div>
            </template>
            <div class="info-row">
              <span class="label">创建时间</span>
              <span>{{ formatDate(recipe.created_at) }}</span>
            </div>
            <div class="info-row" v-if="recipe.updated_at && recipe.updated_at !== recipe.created_at">
              <span class="label">最后更新</span>
              <span>{{ formatDate(recipe.updated_at) }}</span>
            </div>
            <div class="info-row" v-if="recipe.view_count">
              <span class="label">浏览次数</span>
              <span>{{ recipe.view_count }} 次</span>
            </div>
            <div class="info-row" v-if="recipe.favorite_count">
              <span class="label">收藏数量</span>
              <span>{{ recipe.favorite_count }} 人</span>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </template>
  </div>
</template>

<script setup>
/**
 * 菜谱详情页 - 数据加载流程
 * ===========================
 * 1. 组件挂载时，并行执行：
 *    a. loadData()    → 调用 GET /recipes/:id 获取菜谱详情
 *    b. loadReviews() → 调用 GET /reviews/recipes/:id 获取用户点评
 *    c. 如果已登录，POST /users/history 记录浏览历史（静默调用，失败不影响页面）
 *
 * 2. 用户交互：
 *    - 收藏/取消收藏 → toggleFavorite()
 *    - 提交点评 → submitReview()
 *    - 编辑菜谱（仅作者可见）→ 跳转 /recipes/:id/edit
 */
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useUserStore } from '../stores/user'
import { useRecipeCartStore } from '../stores/recipeCart'
import { User } from '@element-plus/icons-vue'
import api from '../api'

const route = useRoute()
const cart = useRecipeCartStore()
const userStore = useUserStore()
const loading = ref(true)
const recipe = ref(null)
const reviews = ref([])
const reviewsTotal = ref(0)
const isFaved = ref(false)
const showReviewForm = ref(false)
const relatedNotes = ref([])
const reviewForm = reactive({ rating: 0, content: '' })

const difficultyMap = { easy: '简单', medium: '中等', hard: '困难' }
const difficultyTypeMap = { easy: 'success', medium: 'warning', hard: 'danger' }

// 只有菜谱作者本人才能看到编辑按钮
const canEdit = computed(() => {
  return userStore.isLoggedIn && recipe.value && userStore.user?.id === recipe.value.author_id
})

// 检查当前登录用户是否已对当前菜谱发表过点评
// 后端业务规则：一个用户对同一菜谱只能点评一次。已点评后应隐藏"写点评"按钮
const hasReviewed = computed(() => {
  if (!userStore.isLoggedIn || !userStore.user?.id) return false
  return reviews.value.some(r => r.user_id === userStore.user.id)
})

function formatDate(d) {
  if (!d) return '—'
  const date = new Date(d)
  return date.toLocaleDateString('zh-CN') + ' ' + date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function truncate(str, len) {
  if (!str) return ''
  return str.length > len ? str.slice(0, len) + '...' : str
}

async function loadData() {
  try {
    const res = await api.get('/recipes/' + route.params.id)
    recipe.value = res
  } catch (e) {
    // 404 或其他错误：保持 recipe.value = null，触发 v-if="!loading && !recipe" 兜底 UI
    // 错误已由全局拦截器提示，此处仅需静默处理避免 "Unhandled error" Vue 警告
    recipe.value = null
  } finally {
    loading.value = false
  }
}

// 加载点评列表，加载失败不影响菜谱详情的展示
async function loadReviews() {
  try {
    const res = await api.get('/reviews/recipes/' + route.params.id)
    reviews.value = res.items || []
    reviewsTotal.value = res.total || 0
  } catch (e) {
    console.error('加载点评失败:', e)
  }
}

// 检查当前菜谱是否已被登录用户收藏 —— 刷新页面后保持正确的收藏按钮状态
async function checkFavoriteStatus() {
  if (!userStore.isLoggedIn) return
  try {
    const recipeId = parseInt(route.params.id)
    // 拉取用户收藏列表（菜谱类型），检查当前 recipe.id 是否在内
    const res = await api.get('/users/favorites', {
      params: { favorite_type: 'recipe', page: 1, page_size: 50 },
    })
    const items = res.items || []
    isFaved.value = items.some(it => it.data && it.data.id === recipeId)
  } catch (e) {
    // 拉取失败不影响页面渲染，默认未收藏
    isFaved.value = false
  }
}

async function toggleFavorite() {
  const recipeId = parseInt(route.params.id)
  if (isFaved.value) {
    try {
      await api.delete('/users/favorites/by/recipe/' + recipeId)
      isFaved.value = false
      ElMessage.success('已取消收藏')
    } catch (e) {
      // 拦截器已提示错误，状态保持不变
    }
  } else {
    try {
      await api.post('/users/favorites', null, { params: { favorite_type: 'recipe', favorite_id: recipeId } })
      isFaved.value = true
      ElMessage.success('收藏成功')
    } catch (e) {
      // 拦截器已提示错误，状态保持不变
    }
  }
}

async function submitReview() {
  if (!reviewForm.rating || !reviewForm.content.trim()) {
    ElMessage.warning('请填写评分和点评内容')
    return
  }
  try {
    await api.post('/reviews/recipes/' + route.params.id, reviewForm)
    reviewForm.rating = 0
    reviewForm.content = ''
    showReviewForm.value = false
    ElMessage.success('点评提交成功')
    loadReviews()
  } catch (e) {
    // 拦截器已提示错误（如重复点评、菜谱未审核等）
  }
}

onMounted(async () => {
  // 先加载菜谱详情：菜谱不存在（404/非法ID）时 recipe.value 保持 null
  await loadData()
  // 菜谱不存在时无需加载点评/收藏/浏览历史，避免控制台报 404/422 错误
  if (!recipe.value) return
  loadReviews()
  // 登录用户：检查收藏状态 + 记录浏览历史（静默调用，失败不影响用户体验）
  if (userStore.isLoggedIn) {
    checkFavoriteStatus()
    api.post('/users/history', null, { params: { recipe_id: route.params.id } }).catch(() => {})
  }
})
</script>

<style scoped>
.recipe-detail-page {
  max-width: 1400px;
}

.detail-hero {
  margin-bottom: 16px;
  border-radius: 8px;
  border: 1px solid #ebeef5;
}

.hero-layout {
  display: flex;
  gap: 24px;
}

.hero-image {
  flex-shrink: 0;
  width: 320px;
  height: 240px;
  border-radius: 8px;
  overflow: hidden;
  background: linear-gradient(135deg, #f5f7fa 0%, #e8ecf1 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #c0c4cc;
}

.hero-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.hero-info {
  flex: 1;
  min-width: 0;
}

.title {
  font-size: 26px;
  font-weight: 700;
  color: #1f2937;
  margin: 0 0 8px;
}

.description {
  color: #606266;
  line-height: 1.6;
  margin: 0 0 16px;
  font-size: 14px;
}

.meta-row {
  display: flex;
  gap: 16px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 14px;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #606266;
  font-size: 14px;
}

.tag-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.t {
  display: flex !important;
  align-items: center;
  gap: 4px;
}

.action-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-top: 16px;
  border-top: 1px solid #ebeef5;
}

.author-info {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #606266;
  font-size: 14px;
}

.content-row {
  margin: 0 !important;
}

.section-card {
  margin-bottom: 16px;
  border-radius: 8px;
  border: 1px solid #ebeef5;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #1f2937;
}

.section-header h3 {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}

.diet-warning {
  margin-bottom: 16px;
}

.section-badge {
  margin-left: auto;
  font-size: 12px;
  font-weight: 400;
  color: #909399;
}

.nutrition-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}
.nut-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 14px 8px;
  background: #f7fafc;
  border: 1px solid #eef2f7;
  border-radius: 8px;
}
.nut-val {
  font-size: 22px;
  font-weight: 700;
  color: #2563eb;
}
.nut-unit {
  font-size: 12px;
  color: #909399;
}
.nut-label {
  font-size: 12px;
  color: #6b7280;
}
@media (max-width: 768px) {
  .nutrition-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

.step-item p {
  line-height: 1.7;
  color: #303133;
  margin: 0 0 8px;
}

.step-duration {
  margin-top: 4px;
}

.review-form {
  background: #f8fafc;
  padding: 16px;
  border-radius: 6px;
  margin-bottom: 16px;
}

.review-item {
  padding: 14px 0;
  border-bottom: 1px solid #f0f0f0;
}

.review-item:last-child {
  border-bottom: none;
}

.review-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.review-user {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.review-user strong {
  font-size: 14px;
  color: #1f2937;
}

.review-time {
  margin-left: auto;
  font-size: 12px;
  color: #909399;
}

.review-content {
  font-size: 14px;
  color: #303133;
  line-height: 1.6;
  margin: 0 0 0 48px;
}

.note-item {
  cursor: pointer;
  padding: 10px 0;
  border-bottom: 1px solid #f0f0f0;
  transition: padding 0.2s;
}

.note-item:last-child {
  border-bottom: none;
}

.note-item:hover {
  padding-left: 8px;
}

.note-item h4 {
  font-size: 14px;
  margin: 0 0 4px;
  color: #1f2937;
  font-weight: 500;
}

.note-item p {
  font-size: 13px;
  color: #909399;
  margin: 0;
}

.info-row {
  display: flex;
  justify-content: space-between;
  padding: 8px 0;
  border-bottom: 1px dashed #f0f0f0;
  font-size: 13px;
}

.info-row:last-child {
  border-bottom: none;
}

.info-row .label {
  color: #909399;
}

.info-row span:last-child {
  color: #303133;
}

.empty-inline {
  text-align: center;
  padding: 20px;
  color: #909399;
  font-size: 14px;
}

@media (max-width: 900px) {
  .hero-layout {
    flex-direction: column;
  }
  .hero-image {
    width: 100%;
    height: 220px;
  }
}

@media (max-width: 767px) {
  /* 侧栏内容改为整行堆叠，避免 18/6 分栏在窄屏过窄 */
  .content-row :deep(.el-col) {
    flex-basis: 100% !important;
    width: 100% !important;
    max-width: 100% !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
  }
  /* 标题+页头操作按钮换行，作者信息不再右推 */
  .action-row {
    flex-wrap: wrap;
  }
  .author-info {
    margin-left: 0;
    width: 100%;
  }
  .tag-row {
    gap: 6px;
  }
}
</style>