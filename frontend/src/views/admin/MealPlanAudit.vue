<template>
  <div class="admin-plans">
    <!-- 顶部标题卡片 -->
    <el-card shadow="never" class="section-card">
      <div class="page-header">
        <div class="section-header">
          <el-icon><Collection /></el-icon>
          <h3>套餐审核</h3>
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
          placeholder="按标题搜索"
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
        <el-table-column prop="title" label="标题" min-width="240">
          <template #default="{ row }">
            <span class="title-text">{{ row.title }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="creator_name" label="创建者" width="140" />
        <el-table-column label="创建时间" width="170">
          <template #default="{ row }">
            <span class="time-text">{{ formatDate(row.created_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审核意见" min-width="180">
          <template #default="{ row }">
            <el-tooltip v-if="row.review_comment" :content="row.review_comment" placement="top" :show-after="200">
              <span class="comment-text">{{ row.review_comment }}</span>
            </el-tooltip>
            <span v-else style="color: #909399">—</span>
          </template>
        </el-table-column>
        <el-table-column label="审核人" width="120">
          <template #default="{ row }">
            <span v-if="row.reviewer_name">{{ row.reviewer_name }}</span>
            <span v-else style="color: #909399">—</span>
          </template>
        </el-table-column>
        <el-table-column label="审核时间" width="170">
          <template #default="{ row }">
            <span class="time-text">{{ formatDate(row.reviewed_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="290" align="center">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="$router.push(`/meal-plans/${row.id}`)">
              <el-icon><View /></el-icon>
              查看
            </el-button>
            <el-button v-if="status === 'pending'" type="success" size="small" @click="audit(row.id, 'approve')">
              <el-icon><Check /></el-icon>
              通过
            </el-button>
            <el-button v-if="status === 'pending'" type="warning" size="small" @click="audit(row.id, 'reject')">
              <el-icon><Close /></el-icon>
              驳回
            </el-button>
            <el-button type="danger" size="small" @click="del(row.id)">
              <el-icon><Delete /></el-icon>
              删除
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

    <!-- 审核对话框（改用声明式 el-dialog 替代 ElMessageBox.prompt，避免编程式弹窗不关闭的问题） -->
    <el-dialog
      v-model="auditDialogVisible"
      :title="auditAction === 'approve' ? '通过审核' : '驳回审核'"
      width="500px"
      :close-on-click-modal="false"
      append-to-body
    >
      <el-form label-position="top">
        <el-form-item :label="auditAction === 'approve' ? '审核意见（可选）' : '审核意见（必填）'">
          <el-input
            v-model="auditComment"
            type="textarea"
            :rows="4"
            :placeholder="auditAction === 'approve' ? '可填写审核意见，留空则直接通过' : '请填写驳回原因'"
            maxlength="500"
            show-word-limit
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="auditDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmAudit" :loading="auditLoading">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import api from '../../api'

const status = ref('pending')
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 12
const loading = ref(false)
const keyword = ref('')

// 审核对话框状态
const auditDialogVisible = ref(false)
const auditAction = ref('approve')
const auditComment = ref('')
const auditId = ref(null)
const auditLoading = ref(false)

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
    const res = await api.get('/admin/meal-plans/pending', { params })
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

// 打开审核对话框，记录待审核的套餐 ID 和操作类型
function audit(id, action) {
  auditId.value = id
  auditAction.value = action
  auditComment.value = ''
  auditDialogVisible.value = true
}

// 确认审核：校验驳回意见 → 调用 API → 关闭对话框 → 刷新列表
async function confirmAudit() {
  if (auditAction.value === 'reject' && !auditComment.value.trim()) {
    ElMessage.warning('驳回时必须填写驳回意见')
    return
  }
  auditLoading.value = true
  try {
    await api.post(`/admin/meal-plans/${auditId.value}/audit`, {
      action: auditAction.value,
      comment: auditComment.value.trim(),
    })
    ElMessage.closeAll()  // 清除残留 toast，避免阻挡对话框关闭动画
    ElMessage.success(auditAction.value === 'approve' ? '已通过审核' : '已驳回')
    // 先关闭对话框，延迟刷新列表，避免 load() 触发的重新渲染打断 el-dialog 的关闭动画
    auditDialogVisible.value = false
    setTimeout(() => {
      load()
    }, 300)
  } catch (e) {
    // 错误已由全局拦截器提示
  } finally {
    auditLoading.value = false
  }
}

async function del(id) {
  try {
    await ElMessageBox.confirm('确定删除该套餐？此操作不可撤销。', '提示', { type: 'warning' })
  } catch (e) {
    return  // 用户取消
  }
  try {
    await api.delete(`/admin/meal-plans/${id}`)
    ElMessage.closeAll()  // 清除残留的 ElMessageBox 遮罩和 toast
    ElMessage.success('删除成功')
    // 若当前页删除后为空且非第一页，回退一页
    if (items.value.length === 1 && page.value > 1) {
      page.value -= 1
    }
    load()
  } catch (e) {
    // 错误已由全局拦截器提示
  }
}

onMounted(load)
</script>

<style scoped>
.admin-plans {
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

.title-text {
  color: #1f2937;
  font-weight: 500;
}

.time-text {
  color: #606266;
  font-size: 13px;
}

.comment-text {
  color: #f56c6c;
  font-size: 13px;
  cursor: default;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-block;
  max-width: 100%;
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}
</style>
