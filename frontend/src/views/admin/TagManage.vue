<template>
  <div class="admin-tags">
    <!-- 顶部标题卡片 -->
    <el-card shadow="never" class="section-card">
      <div class="page-header">
        <div class="section-header">
          <el-icon><PriceTag /></el-icon>
          <h3>标签管理</h3>
        </div>
        <el-button type="primary" size="small" @click="load">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
      <div class="form-row">
        <el-input v-model="newName" placeholder="标签名称" style="width: 220px" />
        <el-input v-model="newType" placeholder="分类（如 cuisine、dish_type）" style="width: 260px" />
        <el-button type="primary" @click="addTag">
          <el-icon><Plus /></el-icon>
          新增标签
        </el-button>
        <el-input
          v-model="searchName"
          placeholder="搜索名称 / 分类"
          clearable
          style="width: 220px; margin-left: auto"
        >
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
      </div>
    </el-card>

    <!-- 表格卡片 -->
    <el-card shadow="never" class="section-card">
      <el-table :data="filteredTags" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="名称" min-width="200">
          <template #default="{ row }">
            <el-tag type="primary" effect="light">{{ row.name }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="type" label="分类" width="200">
          <template #default="{ row }">
            <span v-if="row.type" class="type-text">{{ row.type }}</span>
            <span v-else style="color: #909399">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" align="center" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="editTag(row)">
              <el-icon><Edit /></el-icon>
              编辑
            </el-button>
            <el-button type="danger" link size="small" @click="delTag(row)">
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

    <!-- 编辑对话框 -->
    <el-dialog v-model="editVisible" title="编辑标签" width="480px">
      <el-form label-width="80px">
        <el-form-item label="标签名称">
          <el-input v-model="editForm.name" placeholder="请输入标签名称" />
        </el-form-item>
        <el-form-item label="分类">
          <el-input v-model="editForm.type" placeholder="请输入分类" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../../api'

const tags = ref([])
const loading = ref(false)
const newName = ref('')
const newType = ref('')
const searchName = ref('')
const page = ref(1)
const pageSize = 100
const total = ref(0)

// 前端搜索过滤：匹配名称或分类（大小写不敏感）
const filteredTags = computed(() => {
  const kw = searchName.value.trim().toLowerCase()
  if (!kw) return tags.value
  return tags.value.filter(
    (t) =>
      (t.name || '').toLowerCase().includes(kw) ||
      (t.type || '').toLowerCase().includes(kw)
  )
})

const editVisible = ref(false)
const editForm = ref({ id: null, name: '', type: '' })

async function load() {
  loading.value = true
  try {
    const res = await api.get('/admin/tags', {
      params: { page: page.value, page_size: pageSize },
    })
    // 后端返回 { total, page, page_size, items }，需取 items 字段
    tags.value = Array.isArray(res) ? res : (res.items || [])
    total.value = res.total || tags.value.length
  } catch (e) {
    // 错误已由全局拦截器提示
  } finally {
    loading.value = false
  }
}

async function addTag() {
  if (!newName.value.trim()) {
    ElMessage.warning('请输入标签名称')
    return
  }
  try {
    await api.post('/admin/tags', null, { params: { name: newName.value.trim(), type: newType.value.trim() || undefined } })
    ElMessage.closeAll()  // 清除残留 toast，避免与新增成功消息混淆
    ElMessage.success('添加成功')
    newName.value = ''
    newType.value = ''
    load()
  } catch (e) {
    // 错误已由全局拦截器提示（如标签已存在）
  }
}

function editTag(row) {
  editForm.value = { id: row.id, name: row.name, type: row.type || '' }
  editVisible.value = true
}

async function saveEdit() {
  if (!editForm.value.name.trim()) {
    ElMessage.warning('标签名称不能为空')
    return
  }
  try {
    // 后端 update_tag 接口使用 Query 参数（name/type/description），需通过 params 传递
    await api.put(`/admin/tags/${editForm.value.id}`, null, {
      params: {
        name: editForm.value.name.trim(),
        type: editForm.value.type.trim() || undefined,
      },
    })
    ElMessage.closeAll()  // 清除残留的"添加成功"toast，避免误显示新增消息
    ElMessage.success('修改成功')
    editVisible.value = false
    load()
  } catch (e) {
    // 错误已由全局拦截器提示
  }
}

async function delTag(row) {
  try {
    await ElMessageBox.confirm(`确定删除标签「${row.name}」？`, '提示', { type: 'warning' })
  } catch (e) {
    return  // 用户取消
  }
  try {
    await api.delete(`/admin/tags/${row.id}`)
    ElMessage.closeAll()  // 清除残留的 ElMessageBox 遮罩和 toast
    ElMessage.success('删除成功')
    // 若当前页删除后为空且非第一页，回退一页
    if (tags.value.length === 1 && page.value > 1) {
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
.admin-tags {
  max-width: 1100px;
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

.form-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.type-text {
  color: #606266;
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}
</style>
