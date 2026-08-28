<template>
  <div class="meal-plan-list">
    <el-card class="header-card" shadow="never">
      <div class="page-header">
        <div class="header-info">
          <h1>套餐广场</h1>
          <p class="subtitle">精选用户分享的套餐方案，为你提供一餐/一日的完美搭配</p>
        </div>
        <el-button v-if="userStore.isLoggedIn" plain size="large" @click="$router.push('/user/my-meal-plans')">
          <el-icon><Calendar /></el-icon>
          我的套餐
        </el-button>
        <el-button v-if="userStore.isLoggedIn" type="primary" size="large" @click="$router.push('/meal-plans/create')">
          <el-icon><Plus /></el-icon>
          创建套餐
        </el-button>
      </div>
    </el-card>

    <div class="results-info" v-if="!loading">
      共 <strong>{{ total }}</strong> 个套餐方案
    </div>

    <div class="plan-grid" v-loading="loading" element-loading-text="加载中...">
      <el-card
        v-for="plan in items"
        :key="plan.id"
        shadow="never"
        class="plan-card"
        @click="$router.push(`/meal-plans/${plan.id}`)"
      >
        <div class="card-icon">
          <el-icon :size="28"><Menu /></el-icon>
        </div>
        <div class="card-body">
          <h3 class="card-title">{{ plan.title }}</h3>
          <p class="card-desc" v-if="plan.description">{{ plan.description }}</p>
          <p class="card-desc card-desc-placeholder" v-else>暂无描述</p>
          <div class="card-meta">
            <span class="meta-item">
              <el-icon><User /></el-icon>
              {{ plan.author_nickname || '未知作者' }}
            </span>
            <span class="meta-item">
              <el-icon><View /></el-icon>
              {{ plan.view_count || 0 }}
            </span>
          </div>
        </div>
      </el-card>
      <div v-if="items.length === 0 && !loading" class="empty-state">
        <el-icon :size="64"><DocumentDelete /></el-icon>
        <p>暂无套餐方案</p>
      </div>
    </div>

    <div class="pagination" v-if="total > pageSize">
      <el-pagination
        background
        layout="total, prev, pager, next"
        :total="total"
        :page-size="pageSize"
        v-model:current-page="page"
        @current-change="load"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useUserStore } from '../stores/user'
import { mealPlans } from '../api'

const userStore = useUserStore()

const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 12
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const res = await mealPlans.list({ page: page.value, page_size: pageSize })
    items.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    // 错误已由全局拦截器提示，保持 items 为空数组显示空状态
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>

<style scoped>
.meal-plan-list {
  max-width: 1400px;
}

.header-card {
  margin-bottom: 16px;
  border-radius: 8px;
  border: 1px solid #ebeef5;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
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

.results-info {
  margin-bottom: 12px;
  font-size: 14px;
  color: #606266;
}

.results-info strong {
  color: #2563eb;
  font-size: 16px;
}

.plan-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.plan-card {
  cursor: pointer;
  transition: all 0.2s;
  border-radius: 8px;
  border: 1px solid #ebeef5;
  overflow: hidden;
}

.plan-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
  border-color: #bfdbfe;
}

.card-icon {
  width: 100%;
  height: 120px;
  background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
  color: #2563eb;
  display: flex;
  align-items: center;
  justify-content: center;
}

.card-body {
  padding: 14px 16px 16px;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
  margin: 0 0 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-desc {
  font-size: 13px;
  color: #606266;
  margin: 0 0 12px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  min-height: 39px;
}

.card-desc-placeholder {
  color: #c0c4cc;
}

.card-meta {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: #909399;
  padding-top: 10px;
  border-top: 1px dashed #ebeef5;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
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

@media (max-width: 767px) {
  .page-header {
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
  }
  .page-header .el-button {
    width: 100%;
    margin-left: 0;
  }
}
</style>
