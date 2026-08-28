<template>
  <div class="recipe-list-page">
    <el-card class="filters-card" shadow="never">
      <div class="filters-header">
        <h2>菜谱浏览</h2>
        <el-button v-if="userStore.isLoggedIn" plain @click="$router.push('/user/my-recipes')">
          <el-icon><KnifeFork /></el-icon>
          我的菜谱
        </el-button>
        <el-button v-if="userStore.isLoggedIn" type="primary" @click="$router.push('/recipes/create')">
          <el-icon><Plus /></el-icon>
          创建菜谱
        </el-button>
      </div>
      <div class="filters-row">
        <el-input v-model="keyword" placeholder="搜索菜谱名称、食材..." clearable @keyup.enter="search" style="width: 260px">
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-select v-model="difficulty" placeholder="难度" multiple clearable style="width: 160px">
          <el-option label="简单" value="easy" />
          <el-option label="中等" value="medium" />
          <el-option label="困难" value="hard" />
        </el-select>
        <el-input-number v-model="minCost" :min="0" :step="10" placeholder="最低预算" controls-position="right" style="width: 160px" />
        <el-input-number v-model="maxCost" :min="0" :step="10" placeholder="最高预算" controls-position="right" style="width: 160px" />
        <el-select v-model="sortField" placeholder="排序字段" style="width: 110px">
          <el-option label="时间" value="created_at" />
          <el-option label="价格" value="estimated_cost" />
          <el-option label="难度" value="difficulty" />
        </el-select>
        <el-select v-model="sortOrder" placeholder="方向" style="width: 90px">
          <el-option label="升序" value="asc" />
          <el-option label="降序" value="desc" />
        </el-select>
        <el-button type="primary" @click="search">
          <el-icon><Search /></el-icon>
          搜索
        </el-button>
        <el-button @click="resetFilters">重置</el-button>
        <el-divider direction="vertical" />
        <el-input
          v-model="aiQuery"
          placeholder="智能搜索：用自然语言描述，如「清淡的夏季家常菜」"
          clearable
          @keyup.enter="aiSearch"
          style="width: 300px"
        >
          <template #prefix>
            <el-icon><MagicStick /></el-icon>
          </template>
        </el-input>
        <el-button type="primary" plain :loading="aiThinking" @click="aiSearch">
          <el-icon><MagicStick /></el-icon>
          智能搜索
        </el-button>
      </div>
    </el-card>

    <div class="results-info" v-if="!loading">
      <template v-if="isAiMode">
        智能搜索「{{ lastAiQuery }}」共 <strong>{{ total }}</strong> 个菜谱
        <el-button link type="primary" @click="exitAiMode">返回普通列表</el-button>
      </template>
      <template v-else>
        共 <strong>{{ total }}</strong> 个菜谱
      </template>
    </div>

    <div class="recipe-grid" v-loading="loading" element-loading-text="加载中...">
      <RecipeCard v-for="item in items" :key="item.id" :recipe="item" />
      <div v-if="items.length === 0 && !loading" class="empty-state">
        <el-icon :size="64"><DocumentDelete /></el-icon>
        <p>{{ isAiMode ? '暂未匹配到合适的菜谱，换个说法试试～' : '暂无符合条件的菜谱' }}</p>
      </div>
    </div>

    <div class="pagination" v-if="total > pageSize && !isAiMode">
      <el-pagination
        background
        layout="total, prev, pager, next"
        :total="total"
        :page-size="pageSize"
        v-model:current-page="page"
        @current-change="loadData"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useUserStore } from '../stores/user'
import { recipes, recommendations } from '../api'
import RecipeCard from '../components/RecipeCard.vue'

const route = useRoute()
const userStore = useUserStore()
const loading = ref(false)
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const keyword = ref('')
const difficulty = ref([])
const minCost = ref(null)
const maxCost = ref(null)
const sortField = ref('created_at')
const sortOrder = ref('desc')

// RAG 智能搜索（自然语言语义检索）：结果直接展示在主列表，无弹窗
const isAiMode = ref(false)
const aiQuery = ref('')
const aiThinking = ref(false)
const lastAiQuery = ref('')

async function aiSearch() {
  const q = aiQuery.value.trim()
  if (!q || aiThinking.value) return
  aiThinking.value = true
  try {
    const res = await recommendations.query({ query: q })
    // 只展示菜谱类型结果（套餐/组合不在此列表展示）
    const recipes = (res.items || []).filter((i) => i.type === 'recipe')
    items.value = recipes
    total.value = recipes.length
    isAiMode.value = true
    lastAiQuery.value = q
  } catch (e) {
    items.value = []
    total.value = 0
    isAiMode.value = true
    lastAiQuery.value = q
  } finally {
    aiThinking.value = false
  }
}

// 退出智能搜索模式，恢复普通筛选列表
function exitAiMode() {
  isAiMode.value = false
  aiQuery.value = ''
  page.value = 1
  loadData()
}

async function loadData() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize }
    if (keyword.value) params.keyword = keyword.value
    if (difficulty.value && difficulty.value.length) params.difficulty = difficulty.value.join(',')
    if (minCost.value !== null && minCost.value > 0) params.min_cost = minCost.value
    if (maxCost.value !== null && maxCost.value > 0) params.max_cost = maxCost.value
    if (sortField.value) {
      params.sort_by = sortField.value
      params.sort_order = sortOrder.value
    }
    const res = await recipes.list(params)
    items.value = res.items || []
    total.value = res.total || 0
  } finally {
    loading.value = false
  }
}

function search() {
  page.value = 1
  loadData()
}

function resetFilters() {
  keyword.value = ''
  difficulty.value = []
  minCost.value = null
  maxCost.value = null
  sortField.value = 'created_at'
  sortOrder.value = 'desc'
  page.value = 1
  loadData()
}

onMounted(() => {
  // 从 URL 查询参数中读取所有筛选条件，支持通过链接分享筛选状态
  if (route.query.keyword) keyword.value = route.query.keyword
  if (route.query.difficulty) {
    difficulty.value = String(route.query.difficulty).split(',').filter(Boolean)
  }
  if (route.query.min_cost) minCost.value = Number(route.query.min_cost)
  if (route.query.max_cost) maxCost.value = Number(route.query.max_cost)
  if (route.query.sort_by && route.query.sort_order) {
    sortField.value = route.query.sort_by
    sortOrder.value = route.query.sort_order
  }
  loadData()
})
</script>

<style scoped>
.recipe-list-page {
  max-width: 1400px;
}

.filters-card {
  margin-bottom: 16px;
  border-radius: 8px;
  border: 1px solid #ebeef5;
}

.filters-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}

.filters-header h2 {
  margin: 0;
  font-size: 20px;
  color: #1f2937;
  font-weight: 600;
}

.filters-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
}

.results-info {
  margin-bottom: 12px;
  font-size: 14px;
  color: #606266;
}

.results-info strong {
  color: #2563eb;
  font-size: 16px;
}

.recipe-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
  min-height: 300px;
}

.empty-state {
  grid-column: 1 / -1;
  text-align: center;
  padding: 60px 20px;
  color: #909399;
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

/* 移动端：筛选区纵向堆叠占满整行 */
@media (max-width: 767px) {
  .filters-header {
    flex-direction: column;
    gap: 12px;
    align-items: stretch;
  }
  .filters-row {
    align-items: stretch;
  }
  .filters-row > * {
    width: 100% !important;
    margin-right: 0;
  }
  .filters-row .el-divider {
    display: none;
  }
}
</style>
