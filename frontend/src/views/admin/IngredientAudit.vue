<template>
  <div class="admin-ingredient-audit">
    <!-- 顶部标题卡片 -->
    <el-card shadow="never" class="section-card">
      <div class="page-header">
        <div class="section-header">
          <el-icon><Food /></el-icon>
          <h3>食材审核</h3>
        </div>
        <el-button type="primary" size="small" @click="load">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
      <el-tabs v-model="status" @tab-change="onTabChange">
        <el-tab-pane label="待审核" name="pending" />
        <el-tab-pane label="已通过" name="approved" />
        <el-tab-pane label="已驳回" name="rejected" />
      </el-tabs>
      <div class="search-row">
        <el-input
          v-model="keyword"
          placeholder="按名称搜索"
          clearable
          style="width: 280px"
          @keyup.enter="search"
          @clear="search"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-button type="primary" @click="search">
          <el-icon><Search /></el-icon>
          搜索
        </el-button>
      </div>
    </el-card>

    <!-- 表格 -->
    <el-card shadow="never" class="section-card">
      <el-table :data="items" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="名称" min-width="200">
          <template #default="{ row }">
            <span class="name-text">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="160">
          <template #default="{ row }">
            <el-tag v-if="row.category" type="info" effect="plain" size="small">{{ row.category }}</el-tag>
            <span v-else style="color: #909399">—</span>
          </template>
        </el-table-column>
        <el-table-column label="提交人" width="140">
          <template #default="{ row }">
            <span v-if="row.submitter_name">{{ row.submitter_name }}</span>
            <span v-else style="color: #909399">管理员创建</span>
          </template>
        </el-table-column>
        <el-table-column label="提交时间" width="170">
          <template #default="{ row }">
            <span class="time-text">{{ formatDate(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="图片" width="100" align="center">
          <template #default="{ row }">
            <el-image
              v-if="row.image_url"
              :src="row.image_url"
              :preview-src-list="[row.image_url]"
              preview-teleported
              fit="cover"
              style="width: 48px; height: 48px; border-radius: 6px"
            />
            <span v-else style="color: #909399">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" align="center">
          <template #default="{ row }">
            <template v-if="status === 'pending'">
              <el-button type="success" size="small" @click="audit(row, 'approve')">
                <el-icon><Check /></el-icon>
                通过
              </el-button>
              <el-button type="warning" size="small" @click="audit(row, 'reject')">
                <el-icon><Close /></el-icon>
                驳回
              </el-button>
            </template>
            <!-- 已通过/已驳回的食材支持重新审核（如误操作回退） -->
            <el-button v-else type="primary" link size="small" @click="audit(row, status === 'approved' ? 'reject' : 'approve')">
              {{ status === 'approved' ? '改为驳回' : '改为通过' }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-wrap" v-if="total > 0">
        <el-pagination
          layout="total, prev, pager, next, jumper"
          :total="total"
          :page-size="pageSize"
          v-model:current-page="page"
          @current-change="load"
          background
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { admin } from '../../api'

const status = ref('pending')
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 12
const loading = ref(false)
const keyword = ref('')

function formatDate(d) {
  if (!d) return '—'
  const date = new Date(d)
  return date.toLocaleDateString('zh-CN') + ' ' + date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

async function load() {
  loading.value = true
  try {
    const params = { status: status.value, page: page.value, page_size: pageSize }
    if (keyword.value.trim()) {
      params.keyword = keyword.value.trim()
    }
    const res = await admin.ingredients(params)
    items.value = res.items || []
    total.value = res.total || 0
  } finally {
    loading.value = false
  }
}

// 切换标签或发起搜索时回到第一页
function onTabChange() {
  page.value = 1
  load()
}

function search() {
  page.value = 1
  load()
}

// 审核食材：通过/驳回（确认弹窗 → 调用 API → 刷新列表）
async function audit(row, action) {
  const tip = action === 'approve' ? `确定通过食材「${row.name}」？通过后所有用户可在创建菜谱时选用。` : `确定驳回食材「${row.name}」？驳回后不会出现在食材下拉中。`
  try {
    await ElMessageBox.confirm(tip, '提示', { type: 'warning' })
  } catch (e) {
    return  // 用户取消
  }
  try {
    await admin.auditIngredient(row.id, { action })
    ElMessage.closeAll()
    ElMessage.success(action === 'approve' ? '已通过' : '已驳回')
    load()
  } catch (e) {
    // 错误已由全局拦截器提示
  }
}

onMounted(load)
</script>

<style scoped>
.admin-ingredient-audit {
  max-width: 1400px;
}

.section-card {
  border-radius: 8px;
  border: 1px solid #ebeef5;
  margin-bottom: 16px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.search-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 4px;
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

.name-text {
  color: #1f2937;
  font-weight: 500;
}

.time-text {
  color: #606266;
  font-size: 13px;
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}

/* ===== 移动端适配（≤767px 竖屏浏览） ===== */
@media (max-width: 767px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }

  .search-row {
    flex-wrap: wrap;
    gap: 10px;
  }
  .search-row :deep(.el-input) {
    flex: 1 1 100%;
    width: 100% !important;
  }
  .search-row :deep(.el-button) {
    width: 100%;
    margin-left: 0;
  }
}
</style>
