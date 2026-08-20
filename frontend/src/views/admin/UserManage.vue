<template>
  <div class="admin-users">
    <!-- 顶部标题与搜索卡片 -->
    <el-card shadow="never" class="section-card">
      <div class="page-header">
        <div class="section-header">
          <el-icon><User /></el-icon>
          <h3>用户管理</h3>
        </div>
        <el-button type="primary" size="small" @click="load">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
      <div class="filter-row">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索用户名/昵称/邮箱"
          clearable
          style="width: 320px"
          @keyup.enter="search"
          @clear="search"
        >
          <template #prefix>
            <el-icon><Search /></el-icon>
          </template>
        </el-input>
        <el-button type="primary" @click="search">
          <el-icon><Search /></el-icon>
          搜索
        </el-button>
      </div>
    </el-card>

    <!-- 表格卡片 -->
    <el-card shadow="never" class="section-card">
      <el-table :data="items" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="username" label="用户名" width="160">
          <template #default="{ row }">
            <span class="username-text">{{ row.username }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="nickname" label="昵称" width="160" />
        <el-table-column prop="email" label="邮箱" min-width="200" />
        <el-table-column label="角色" width="100" align="center">
          <template #default="{ row }">
            <!-- :key 绑定 role，角色变更时强制重新渲染 el-tag，避免 el-zoom-in-center 过渡动画未清理导致新旧标签同时显示 -->
            <el-tag :key="row.role + '-' + row.id" :type="row.role === 'admin' ? 'primary' : 'info'" :effect="row.role === 'admin' ? 'light' : 'plain'" size="small">
              {{ row.role === 'admin' ? '管理员' : '普通用户' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.is_active ? 'success' : 'danger'" effect="light" size="small">
              {{ row.is_active ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="220" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.role !== 'admin'"
              :type="row.is_active ? 'warning' : 'success'"
              size="small"
              @click="toggle(row)"
            >
              <el-icon><component :is="row.is_active ? 'Lock' : 'Unlock'" /></el-icon>
              {{ row.is_active ? '禁用' : '启用' }}
            </el-button>
            <el-button
              v-if="row.role === 'admin'"
              type="primary"
              size="small"
              plain
              @click="changeRole(row, 'user')"
            >
              <el-icon><UserFilled /></el-icon>
              降为用户
            </el-button>
            <el-button
              v-else
              type="danger"
              size="small"
              plain
              @click="changeRole(row, 'admin')"
            >
              <el-icon><Avatar /></el-icon>
              升为管理员
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
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../../api'

const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 15
const loading = ref(false)
const searchKeyword = ref('')

// 当前登录管理员（用于禁止"撤销自己管理员权限"等危险操作）
const currentUser = JSON.parse(localStorage.getItem('user') || 'null')

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize }
    if (searchKeyword.value.trim()) {
      params.keyword = searchKeyword.value.trim()
    }
    const res = await api.get('/admin/users', { params })
    items.value = res.items || []
    total.value = res.total || 0
  } finally {
    loading.value = false
  }
}

// 发起搜索：关键词变化时回到第一页，避免停留在末页出现空白
function search() {
  page.value = 1
  load()
}

async function toggle(row) {
  try {
    await api.post(`/admin/users/${row.id}/toggle-active`)
    ElMessage.closeAll()  // 清除残留 toast
    ElMessage.success(row.is_active ? '已禁用用户' : '已启用用户')
    load()
  } catch (e) {
    // 兼容处理
  }
}

// 调整用户角色（PRD FR-A05）—— 后端接口 POST /admin/users/{id}/role?role=user|admin
async function changeRole(row, newRole) {
  // 前端预校验：不允许撤销自己的管理员权限
  if (currentUser && currentUser.id === row.id && newRole !== 'admin') {
    ElMessage.warning('不能撤销自己的管理员权限')
    return
  }
  const actionText = newRole === 'admin' ? '升为管理员' : '降为普通用户'
  try {
    await ElMessageBox.confirm(
      `确定要将用户 "${row.username}" ${actionText}吗？`,
      '角色调整确认',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    return  // 用户取消
  }
  try {
    await api.post(`/admin/users/${row.id}/role`, null, { params: { role: newRole } })
    ElMessage.closeAll()  // 清除残留 toast 和 messagebox 遮罩
    ElMessage.success(`已${actionText}`)
    load()
  } catch (e) {
    // 后端会校验：不能撤销自己的管理员权限、用户不存在等
  }
}

onMounted(load)
</script>

<style scoped>
.admin-users {
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
  margin-bottom: 12px;
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

.filter-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.username-text {
  color: #1f2937;
  font-weight: 500;
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}
</style>
