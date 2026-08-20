<template>
  <div class="meal-plan-detail" v-loading="loading">
    <!-- 套餐不存在的兜底提示 -->
    <el-card v-if="!loading && !plan" shadow="never" class="not-found-card">
      <el-empty description="套餐不存在或已被删除">
        <el-button type="primary" @click="$router.push('/meal-plans')">返回套餐列表</el-button>
      </el-empty>
    </el-card>
    <template v-if="plan">
      <el-card class="detail-hero" shadow="never">
        <div class="hero-layout">
          <div class="hero-image" v-if="plan.cover_image_url">
            <img :src="plan.cover_image_url" :alt="plan.title" />
          </div>
          <div class="hero-image" v-else>
            <el-icon :size="72"><Menu /></el-icon>
          </div>
          <div class="hero-info">
            <h1 class="title">{{ plan.title }}</h1>
            <p class="description" v-if="plan.description">{{ plan.description }}</p>
            <p class="description placeholder" v-else>暂无描述</p>
            <div class="meta-row">
              <span class="meta-item">
                <el-icon><UserFilled /></el-icon>
                {{ plan.author_nickname || '未知作者' }}
              </span>
              <span class="meta-item">
                <el-icon><Calendar /></el-icon>
                {{ formatDate(plan.created_at) }}
              </span>
              <span class="meta-item">
                <el-icon><View /></el-icon>
                {{ plan.view_count || 0 }} 次浏览
              </span>
            </div>
            <div class="action-row" v-if="userStore.isLoggedIn">
              <!-- 仅在套餐已审核通过时才显示收藏按钮：pending/rejected 资源后端会拒绝收藏，避免按钮点击后报错 -->
              <el-button v-if="plan.status === 'approved'" :type="isFaved ? 'warning' : 'primary'" @click="toggleFavorite">
                <el-icon><Star /></el-icon>
                {{ isFaved ? '已收藏' : '收藏' }}
              </el-button>
              <!-- 作者查看未通过审核的套餐时给出状态提示 -->
              <el-tag v-else :type="plan.status === 'pending' ? 'warning' : 'danger'" effect="plain" size="default">
                {{ plan.status === 'pending' ? '审核中，暂不可收藏' : '审核未通过，暂不可收藏' }}
              </el-tag>
              <el-button v-if="canEdit" type="success" @click="$router.push(`/meal-plans/create?id=${plan.id}`)">
                <el-icon><Edit /></el-icon>
                编辑套餐
              </el-button>
              <el-button v-if="canEdit" type="danger" plain @click="handleDelete">
                <el-icon><Delete /></el-icon>
                删除套餐
              </el-button>
              <el-button type="primary" plain @click="openShopping">
                <el-icon><ShoppingCart /></el-icon>
                生成购物清单
              </el-button>
              <el-button v-if="userStore.isLoggedIn && plan && plan.user_id !== userStore.user?.id" type="info" plain @click="copyPlan">
                <el-icon><CopyDocument /></el-icon>
                复制套餐
              </el-button>
            </div>
          </div>
        </div>
      </el-card>

      <!-- 购物清单弹窗 -->
      <el-dialog v-model="shoppingVisible" title="购物清单" width="560px" align-center>
        <template v-if="shopping">
          <div class="shop-summary">
            <span>共 {{ shopping.recipe_count }} 道菜 · 约 ¥{{ shopping.total_cost }}</span>
            <span class="shop-hint">用量仅按食材归类列出，请自行加总判断实际购买量</span>
          </div>
          <div class="shop-list">
            <div v-for="(it, idx) in shopping.items" :key="idx" class="shop-row">
              <span class="shop-name">{{ it.name }}</span>
              <span class="shop-raw" v-if="it.raw.length"><el-tag size="small" type="info" effect="plain">{{ it.raw.join('、') }}</el-tag></span>
            </div>
          </div>
        </template>
        <template #footer>
          <el-button @click="shoppingVisible = false">关闭</el-button>
          <el-button type="primary" @click="copyShopping">
            <el-icon><CopyDocument /></el-icon>复制清单
          </el-button>
        </template>
      </el-dialog>

      <el-card class="section-card" shadow="never">
        <template #header>
          <div class="section-header">
            <el-icon><KnifeFork /></el-icon>
            <h3>套餐菜品（{{ plan.items?.length || 0 }}）</h3>
          </div>
        </template>
        <div v-if="plan.items?.length" class="recipe-grid">
          <el-card
            v-for="(item, idx) in plan.items"
            :key="item.id || idx"
            shadow="never"
            class="item-card"
            @click="goRecipe(item.recipe_id)"
          >
            <div class="item-index">{{ idx + 1 }}</div>
            <div class="item-content">
              <h4>{{ item.recipe_title || '（菜谱已删除）' }}</h4>
              <p v-if="item.note" class="item-note">{{ item.note }}</p>
            </div>
            <el-icon class="item-arrow"><ArrowRight /></el-icon>
          </el-card>
        </div>
        <div v-else class="empty-inline">
          <el-icon><DocumentDelete /></el-icon>
          <p>暂无菜品</p>
        </div>
      </el-card>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '../stores/user'
import { Star, Edit, Delete, ShoppingCart, CopyDocument } from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import api from '../api'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const loading = ref(true)
const plan = ref(null)
const isFaved = ref(false)
const shoppingVisible = ref(false)
const shopping = ref(null)

// 生成本套餐的购物清单并打开弹窗
async function openShopping() {
  if (!plan.value) return
  try {
    const res = await api.get(`/meal-plans/${plan.value.id}/shopping-list`)
    shopping.value = res
    shoppingVisible.value = true
  } catch (e) {
    ElMessage.error('获取购物清单失败')
  }
}

// 复制购物清单为文本
async function copyShopping() {
  if (!shopping.value) return
  const lines = shopping.value.items.map((it) => it.name + (it.raw.length ? '（' + it.raw.join('、') + '）' : ''))
  const text = `购物清单（${shopping.value.recipe_count}道菜，约¥${shopping.value.total_cost}）\n` + lines.join('\n')
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('清单已复制')
  } catch (e) {
    ElMessage.error('复制失败，请手动复制')
  }
}

// 复制他人套餐：沿用其菜品与描述，跳转到创建页（不含标题与封面）
function copyPlan() {
  if (!plan.value) return
  const items = plan.value.items || []
  const ids = items.map((i) => i.recipe_id).filter(Boolean).join(',')
  const desc = encodeURIComponent(plan.value.description || '')
  const q = [`copy=1`, `desc=${desc}`]
  if (ids) q.push(`recipe_ids=${ids}`)
  router.push(`/meal-plans/create?${q.join('&')}`)
}

// 只有套餐作者才能编辑/删除
const canEdit = computed(() => {
  return userStore.isLoggedIn && plan.value && userStore.user?.id === plan.value.user_id
})

function formatDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('zh-CN') + ' ' + new Date(d).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

function goRecipe(id) {
  if (id) router.push(`/recipes/${id}`)
}

// 检查当前套餐是否已被登录用户收藏
async function checkFavoriteStatus() {
  if (!userStore.isLoggedIn) return
  try {
    const planId = parseInt(route.params.id)
    const res = await api.get('/users/favorites', {
      params: { favorite_type: 'meal_plan', page: 1, page_size: 50 },
    })
    const items = res.items || []
    isFaved.value = items.some(it => it.data && it.data.id === planId)
  } catch (e) {
    isFaved.value = false
  }
}

async function toggleFavorite() {
  const planId = parseInt(route.params.id)
  if (isFaved.value) {
    try {
      await api.delete('/users/favorites/by/meal_plan/' + planId)
      isFaved.value = false
      ElMessage.success('已取消收藏')
    } catch (e) {
      // 拦截器已提示错误
    }
  } else {
    try {
      await api.post('/users/favorites', null, { params: { favorite_type: 'meal_plan', favorite_id: planId } })
      isFaved.value = true
      ElMessage.success('收藏成功')
    } catch (e) {
      // 拦截器已提示错误
    }
  }
}

// 删除套餐（带确认对话框）
// 拆分为两段 try/catch：第一段捕获用户取消，第二段处理 API 调用
// 避免删除成功后路由跳转打断 ElMessageBox 遮罩清理动画导致遮罩残留
async function handleDelete() {
  try {
    await ElMessageBox.confirm('确定要删除这个套餐吗？删除后无法恢复。', '删除确认', {
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch (e) {
    return  // 用户点击取消
  }
  try {
    await api.delete('/meal-plans/' + route.params.id)
    ElMessage.closeAll()  // 清除残留的 ElMessageBox 遮罩和 toast
    ElMessage.success('删除成功')
    // 延迟跳转，确保 ElMessageBox 遮罩层已完全清理
    setTimeout(() => {
      router.push('/meal-plans')
    }, 100)
  } catch (e) {
    // api 报错（拦截器已处理）
  }
}

onMounted(async () => {
  try {
    plan.value = await api.get(`/meal-plans/${route.params.id}`)
    // 登录用户：检查收藏状态 + 记录浏览历史（静默调用，失败不影响页面）
    if (userStore.isLoggedIn) {
      checkFavoriteStatus()
      api.post('/users/history', null, { params: { meal_plan_id: route.params.id } }).catch(() => {})
    }
  } catch (e) {
    // 404 或其他错误：保持 plan.value = null，触发 v-if="!loading && !plan" 兜底 UI
    // 错误已由全局拦截器提示（如登录过期），此处仅需静默处理避免 "Unhandled error" Vue 警告
    plan.value = null
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.meal-plan-detail {
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
  height: 220px;
  border-radius: 8px;
  overflow: hidden;
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #2563eb;
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

.description.placeholder {
  color: #c0c4cc;
}

.meta-row {
  display: flex;
  gap: 20px;
  align-items: center;
  flex-wrap: wrap;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #606266;
  font-size: 14px;
}

.action-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-top: 16px;
  margin-top: 4px;
  border-top: 1px solid #ebeef5;
}

.section-card {
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

.recipe-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}

.item-card {
  cursor: pointer;
  transition: all 0.2s;
  border-radius: 8px;
  border: 1px solid #ebeef5;
  padding: 14px 16px;
  display: flex;
  align-items: center;
  gap: 12px;
  background: #f8fafc;
}

.item-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
  border-color: #bfdbfe;
  background: #fff;
}

.item-index {
  width: 32px;
  height: 32px;
  background: #2563eb;
  color: #fff;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 14px;
  flex-shrink: 0;
}

.item-content {
  flex: 1;
  min-width: 0;
}

.item-content h4 {
  font-size: 14px;
  color: #1f2937;
  margin: 0 0 4px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.item-note {
  font-size: 12px;
  color: #909399;
  margin: 0;
}

.item-arrow {
  color: #909399;
  flex-shrink: 0;
}

.shop-summary {
  color: #374151;
  font-weight: 600;
  margin: 0 0 12px;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}
.shop-hint {
  font-size: 12px;
  font-weight: 400;
  color: #909399;
  text-align: right;
}
.shop-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 50vh;
  overflow-y: auto;
}
.shop-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 12px;
  border: 1px solid #eef2f7;
  border-radius: 6px;
}
.shop-name {
  font-weight: 600;
  color: #1f2937;
}

.empty-inline {
  text-align: center;
  padding: 40px 20px;
  color: #909399;
  font-size: 14px;
}

.empty-inline p {
  margin: 8px 0 0;
}

@media (max-width: 900px) {
  .hero-layout {
    flex-direction: column;
  }
  .hero-image {
    width: 100%;
    height: 180px;
  }
}

@media (max-width: 767px) {
  .action-row {
    flex-wrap: wrap;
  }
  .shop-summary {
    flex-direction: column;
    align-items: flex-start;
    gap: 6px;
  }
  .shop-hint {
    text-align: left;
  }
  .shop-row {
    flex-wrap: wrap;
  }
}
</style>
