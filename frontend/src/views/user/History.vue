<template>
  <div class="history-page">
    <el-card class="header-card" shadow="never">
      <div class="page-header">
        <div class="header-info">
          <h1>浏览历史</h1>
          <p class="subtitle">共 {{ total }} 条浏览记录</p>
        </div>
        <!-- TODO: 后端尚未实现 DELETE /users/history 批量清空接口，清空功能暂不可用 -->
        <!-- <el-button v-if="total > 0" type="danger" plain @click="clearHistory">
          <el-icon><Delete /></el-icon>
          清空历史
        </el-button> -->
      </div>
    </el-card>

    <div class="content" v-loading="loading" element-loading-text="加载中...">
      <div v-if="items.length" class="grid">
        <div v-for="h in items" :key="h.id" class="grid-item">
          <div class="recipe-card" @click="goDetail(h.data?.id)">
            <div class="card-image" v-if="h.data?.cover_image_url">
              <img :src="h.data.cover_image_url" :alt="h.data.title" />
            </div>
            <div class="card-image" v-else>
              <el-icon :size="48"><Picture /></el-icon>
            </div>
            <div class="card-body">
              <h3 class="card-title">{{ h.data?.title || '（已删除）' }}</h3>
              <p class="card-desc" v-if="h.data?.description">{{ h.data.description }}</p>
              <div class="card-meta">
                <el-icon><Clock /></el-icon>
                <span>{{ formatDate(h.viewed_at) }}</span>
                <span v-if="h.data?.cooking_time" class="meta-right">
                  <el-icon><Timer /></el-icon>
                  {{ h.data.cooking_time }}分钟
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="items.length === 0 && !loading" class="empty-state">
        <el-icon :size="64"><Clock /></el-icon>
        <p>暂无浏览记录，去逛逛感兴趣的菜谱吧～</p>
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
 * 浏览历史页面
 * =============
 * 功能：展示用户最近浏览过的菜谱记录，按时间倒序排列。
 * 浏览记录在 RecipeDetail.vue 中自动记录（onMounted → POST /users/history）。
 *
 * 注意：清空历史功能因后端 DELETE /users/history 接口未实现，已暂时隐藏按钮。
 */
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import api from '../../api'

const router = useRouter()
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 12
const loading = ref(false)

function formatDate(d) {
  if (!d) return '—'
  const date = new Date(d)
  return date.toLocaleDateString('zh-CN') + ' ' + date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

async function load() {
  loading.value = true
  try {
    const res = await api.get('/users/history', { params: { page: page.value, page_size: pageSize } })
    items.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    // 错误已由全局拦截器提示
  } finally {
    loading.value = false
  }
}

function goDetail(id) {
  if (id) router.push(`/recipes/${id}`)
}

onMounted(load)
</script>

<style scoped>
.history-page {
  max-width: 1400px;
}

.header-card {
  margin-bottom: 16px;
  border-radius: 8px;
  border: 1px solid #ebeef5;
}

.page-header {
  display: flex;
  align-items: center;
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

.content {
  min-height: 300px;
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}

.recipe-card {
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

.recipe-card:hover {
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

.card-body {
  padding: 14px 16px 16px;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
  margin: 0 0 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-desc {
  font-size: 13px;
  color: #909399;
  margin: 0 0 12px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-meta {
  display: flex;
  gap: 8px;
  font-size: 12px;
  color: #909399;
  align-items: center;
  padding-top: 10px;
  border-top: 1px dashed #ebeef5;
}

.meta-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 4px;
}

.empty-state {
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
  .page-header {
    flex-wrap: wrap;
    align-items: flex-start;
  }
  .card-meta {
    flex-wrap: wrap;
    gap: 8px;
  }
}
</style>