<template>
  <div class="favorites-page">
    <el-card class="header-card" shadow="never">
      <div class="page-header">
        <div class="header-info">
          <h1>我的收藏</h1>
          <p class="subtitle">共收藏 {{ total }} 项内容</p>
        </div>
      </div>
      <el-tabs v-model="tab" @tab-change="onTabChange" class="fav-tabs">
        <el-tab-pane label="菜谱" name="recipe" />
        <el-tab-pane label="套餐" name="meal_plan" />
      </el-tabs>
    </el-card>

    <div class="content" v-loading="loading" element-loading-text="加载中...">
      <div v-if="tab === 'recipe' && recipeItems.length" class="grid">
        <div v-for="item in recipeItems" :key="item.favorite_id || item.data?.id" class="grid-item">
          <div class="recipe-card" @click="goRecipe(item.data?.id)">
            <div class="card-image" v-if="item.data?.cover_image_url">
              <img :src="item.data.cover_image_url" :alt="item.data.title" />
            </div>
            <div class="card-image" v-else>
              <el-icon :size="48"><Picture /></el-icon>
            </div>
            <div class="card-body">
              <h3 class="card-title">{{ item.data?.title || '（已删除）' }}</h3>
              <div class="card-meta">
                <span v-if="item.data?.cooking_time">
                  <el-icon><Timer /></el-icon>
                  {{ item.data.cooking_time }}分钟
                </span>
                <span v-if="item.data?.difficulty">
                  <el-tag :type="difficultyTypeMap[item.data.difficulty] || 'info'" size="small" effect="plain">
                    {{ difficultyMap[item.data.difficulty] || item.data.difficulty }}
                  </el-tag>
                </span>
              </div>
              <div class="card-footer">
                <el-button type="danger" size="small" plain @click.stop="removeFav(item.favorite_id)">
                  <el-icon><StarFilled /></el-icon>
                  取消收藏
                </el-button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="tab === 'meal_plan' && planItems.length" class="grid">
        <div v-for="item in planItems" :key="item.favorite_id || item.data?.id" class="grid-item">
          <div class="plan-card" @click="goPlan(item.data?.id)">
            <div class="plan-icon">
              <el-icon :size="32"><Menu /></el-icon>
            </div>
            <div class="plan-body">
              <h3 class="plan-title">{{ item.data?.title || '（已删除）' }}</h3>
              <p class="plan-desc" v-if="item.data?.description">{{ item.data.description }}</p>
              <div class="card-footer">
                <el-button type="danger" size="small" plain @click.stop="removeFav(item.favorite_id)">
                  <el-icon><StarFilled /></el-icon>
                  取消收藏
                </el-button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="isEmpty" class="empty-state">
        <el-icon :size="64"><Star /></el-icon>
        <p>还没有收藏内容，快去发现喜欢的菜谱和套餐吧～</p>
      </div>
    </div>

    <div class="pagination" v-if="total > pageSize">
      <el-pagination
        background
        layout="prev, pager, next"
        :total="total"
        :page-size="pageSize"
        v-model:current-page="page"
        @current-change="load"
      />
    </div>
  </div>
</template>

<script setup>
/**
 * 收藏页面
 * =========
 * 页面结构：
 * 1. 顶部标题 + 分 Tab（菜谱 / 套餐）
 * 2. 根据当前 Tab 显示对应类型的收藏项列表
 * 3. 每项支持取消收藏（带确认弹窗）
 * 4. 分页加载
 *
 * 数据流：切换 Tab → 重置页码 → LOAD → GET /users/favorites?favorite_type=... → 渲染
 * 后端返回的数据中，item.data 是被收藏对象的快照（菜谱或套餐信息）
 */
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import api from '../../api'
import { ElMessage, ElMessageBox } from 'element-plus'

const router = useRouter()
const tab = ref('recipe')
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 12
const loading = ref(false)

const difficultyMap = { easy: '简单', medium: '中等', hard: '困难' }
const difficultyTypeMap = { easy: 'success', medium: 'warning', hard: 'danger' }

// 按 type 字段筛选：后端已在 favorite_type 维度做了分页区分，
// 但返回的 items 中仍有 type 字段，这里做前端二次过滤以确保数据正确性
const recipeItems = computed(() => items.value.filter(i => i.type === 'recipe'))
const planItems = computed(() => items.value.filter(i => i.type === 'meal_plan'))

const isEmpty = computed(() => {
  if (loading.value) return false
  if (tab.value === 'recipe') return recipeItems.value.length === 0
  return planItems.value.length === 0
})

function onTabChange() {
  page.value = 1
  load()
}

async function load() {
  loading.value = true
  try {
    const res = await api.get('/users/favorites', {
      params: { favorite_type: tab.value, page: page.value, page_size: pageSize },
    })
    items.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    // 错误已由全局拦截器提示
  } finally {
    loading.value = false
  }
}

async function removeFav(id) {
  try {
    await ElMessageBox.confirm('确定要取消收藏吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch (e) {
    return  // 用户取消
  }
  try {
    await api.delete(`/users/favorites/${id}`)
    ElMessage.closeAll()  // 清除残留的 ElMessageBox 遮罩和 toast
    ElMessage.success('已取消收藏')
    // 若当前页删除后为空且非第一页，回退一页
    if (items.value.length === 1 && page.value > 1) {
      page.value -= 1
    }
    load()
  } catch (e) {
    // 错误已由全局拦截器提示
  }
}

function goRecipe(id) {
  if (id) router.push(`/recipes/${id}`)
}

function goPlan(id) {
  if (id) router.push(`/meal-plans/${id}`)
}

load()
</script>

<style scoped>
.favorites-page {
  max-width: 1400px;
}

.header-card {
  margin-bottom: 16px;
  border-radius: 8px;
  border: 1px solid #ebeef5;
}

.page-header {
  margin-bottom: 8px;
}

.header-info h1 {
  margin: 0 0 4px;
  font-size: 22px;
  color: #1f2937;
  font-weight: 700;
}

.header-info .subtitle {
  margin: 0;
  color: #909399;
  font-size: 13px;
}

.fav-tabs :deep(.el-tabs__header) {
  margin: 12px 0 0;
}

.content {
  min-height: 300px;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.recipe-card,
.plan-card {
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid #ebeef5;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  display: flex;
  flex-direction: column;
}

.recipe-card:hover,
.plan-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
  border-color: #bfdbfe;
}

.card-image {
  width: 100%;
  height: 160px;
  overflow: hidden;
  background: linear-gradient(135deg, #f5f7fa 0%, #e8ecf1 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #c0c4cc;
}

.card-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.plan-icon {
  height: 120px;
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  color: #2563eb;
  display: flex;
  align-items: center;
  justify-content: center;
}

.card-body,
.plan-body {
  padding: 14px 16px 16px;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.card-title,
.plan-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
  margin: 0 0 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.plan-desc {
  font-size: 13px;
  color: #909399;
  margin: 0 0 12px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  flex: 1;
}

.card-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #909399;
  align-items: center;
  padding-bottom: 12px;
}

.card-meta span {
  display: flex;
  align-items: center;
  gap: 4px;
}

.card-footer {
  padding-top: 12px;
  border-top: 1px dashed #ebeef5;
  margin-top: auto;
}

.empty-state {
  grid-column: 1 / -1;
  text-align: center;
  padding: 60px 20px;
  color: #909399;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #ebeef5;
}

.empty-state p {
  margin-top: 12px;
  font-size: 14px;
}

.pagination {
  display: flex;
  justify-content: center;
  padding: 16px 0;
}

@media (max-width: 767px) {
  .card-meta {
    flex-wrap: wrap;
    gap: 8px;
  }
  .card-footer .el-button {
    margin-left: 0;
  }
}
</style>