<template>
  <div class="my-meal-plans">
    <el-card class="head" shadow="never">
      <div class="head-row">
        <h2>我的套餐</h2>
        <el-button type="primary" @click="$router.push('/meal-plans/create')">
          <el-icon><Plus /></el-icon>新建套餐
        </el-button>
      </div>
      <div class="capsule-tabs">
        <span
          v-for="t in tabs" :key="t.value"
          class="capsule"
          :class="{ active: statusFilter === t.value }"
          @click="setFilter(t.value)"
        >{{ t.name }}</span>
      </div>
    </el-card>

    <div v-loading="loading" class="list">
      <div v-for="p in items" :key="p.id" class="row-card" @click="$router.push(`/meal-plans/${p.id}`)">
        <img class="cover" :src="p.cover_image_url || ''" :onerror="fallbackImg" alt="" />
        <div class="info">
          <div class="title-line">
            <span class="title">{{ p.title }}</span>
            <span class="status-pill" :class="'st-' + (p.status || '')">{{ statusMeta(p.status).label }}</span>
            <el-tag v-if="!p.is_public" size="small" type="info" effect="plain">仅自己</el-tag>
          </div>
          <p class="desc">{{ p.description || '暂无描述' }}</p>
          <p v-if="p.status === 'rejected' && p.review_comment" class="reject-reason">
            <el-icon><WarningFilled /></el-icon>驳回原因：{{ p.review_comment }}
          </p>
          <div class="meta">
            <span><el-icon><View /></el-icon>{{ p.view_count }}</span>
            <span><el-icon><Star /></el-icon>{{ p.favorite_count }}</span>
            <span><el-icon><Calendar /></el-icon>{{ formatDate(p.created_at) }}</span>
          </div>
        </div>
        <div class="actions" @click.stop>
          <el-button size="small" text type="primary" @click="$router.push(`/meal-plans/${p.id}`)">查看</el-button>
          <el-button size="small" text type="primary" @click="$router.push(`/meal-plans/create?id=${p.id}`)">继续编辑</el-button>
          <el-button size="small" text class="del-btn" @click="remove(p)">删除</el-button>
        </div>
      </div>
      <div v-if="!items.length && !loading" class="empty-box">
        <el-empty :description="emptyText" />
      </div>
    </div>

    <div class="pagination" v-if="total > pageSize">
      <el-pagination background layout="prev, pager, next" :total="total" :page-size="pageSize"
        v-model:current-page="page" @current-change="load" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { mealPlans } from '../../api'

const statusFilter = ref('')
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 12
const loading = ref(false)

const emptyText = computed(() => {
  const map = { approved: '已上架', pending: '待审核', draft: '草稿', rejected: '已驳回' }
  return statusFilter.value ? `还没有${map[statusFilter.value] || ''}的套餐` : '还没有套餐'
})

const tabs = [
  { name: '全部', value: '' },
  { name: '已上架', value: 'approved' },
  { name: '待审核', value: 'pending' },
  { name: '草稿', value: 'draft' },
  { name: '已驳回', value: 'rejected' },
]
const statusMap = {
  approved: { label: '已上架' },
  pending: { label: '待审核' },
  draft: { label: '草稿' },
  rejected: { label: '已驳回' },
}
const fallbackImg = "this.src='data:image/svg+xml;utf8,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><rect width=%22100%22 height=%22100%22 fill=%22%23f3f4f6%22/></svg>'"

function statusMeta(s) { return statusMap[s] || { label: s || '未知' } }
function formatDate(d) { return d ? new Date(d).toLocaleDateString('zh-CN') : '' }

async function load() {
  loading.value = true
  try {
    const params = { mine: 1, page: page.value, page_size: pageSize }
    if (statusFilter.value) params.status = statusFilter.value
    const res = await mealPlans.list(params)
    items.value = res.items || []
    total.value = res.total || 0
  } catch (e) { console.error(e) }
  finally { loading.value = false }
}

function setFilter(v) {
  if (statusFilter.value === v) return
  statusFilter.value = v
  page.value = 1
  load()
}

async function remove(p) {
  const ok = await ElMessageBox.confirm(`确定删除套餐「${p.title}」吗？`, '提示', { type: 'warning' }).catch(() => false)
  if (!ok) return
  await mealPlans.remove(p.id)
  ElMessage.success('已删除')
  load()
}

load()
</script>

<style scoped>
.my-meal-plans { max-width: 1050px; }
.head { border-radius: 14px; border: 1px solid #ebeef5; margin-bottom: 16px; }
.head-row { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 14px; }
.head h2 { margin: 0; font-size: 20px; }

.capsule-tabs { display: flex; flex-wrap: wrap; gap: 8px; }
.capsule {
  padding: 5px 18px;
  border-radius: 999px;
  background: #f3f4f6;
  color: #4b5563;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
  user-select: none;
}
.capsule:hover { background: #eef2ff; color: #2563eb; }
.capsule.active { background: #2563eb; color: #fff; }

.list { display: flex; flex-direction: column; gap: 14px; }
.row-card {
  display: flex;
  gap: 18px;
  align-items: center;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 14px;
  padding: 14px 18px;
  cursor: pointer;
  transition: all 0.2s;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.04);
}
.row-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.10);
  border-color: #bfdbfe;
}
.cover { width: 132px; height: 88px; object-fit: cover; border-radius: 10px; flex-shrink: 0; }
.info { flex: 1; min-width: 0; }
.title-line { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.title { font-size: 16px; font-weight: 600; color: #1f2937; }

.status-pill { font-size: 12px; padding: 1px 10px; border-radius: 999px; line-height: 20px; }
.st-approved { background: #ecfdf5; color: #059669; }
.st-pending { background: #fef3c7; color: #d97706; }
.st-draft { background: #eff6ff; color: #2563eb; }
.st-rejected { background: #fee2e2; color: #dc2626; }

.desc {
  color: #6b7280;
  font-size: 13px;
  margin: 6px 0 8px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 驳回原因（已驳回的套餐展示） */
.reject-reason {
  color: #dc2626;
  font-size: 12px;
  margin: 0 0 6px;
  display: flex;
  align-items: center;
  gap: 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.meta { display: flex; gap: 16px; color: #909399; font-size: 12px; align-items: center; }
.meta .el-icon { margin-right: 2px; vertical-align: -2px; }

.actions { flex-shrink: 0; display: flex; align-items: center; gap: 2px; }
.actions .el-button { margin-left: 0; }
.del-btn { color: #c0c4cc; }
.del-btn:hover { color: #dc2626; background: #fef2f2; }

.pagination { display: flex; justify-content: center; padding: 16px 0; }
.empty-box { background: #fff; border: 1px solid #ebeef5; border-radius: 14px; padding: 40px 20px; }

@media (max-width: 767px) {
  .head-row { flex-direction: column; align-items: stretch; gap: 10px; }
  .head-row .el-button { width: 100%; margin-left: 0; }
  .row-card { flex-wrap: wrap; gap: 12px; }
  .actions { flex-basis: 100%; justify-content: flex-end; flex-wrap: wrap; }
}
</style>