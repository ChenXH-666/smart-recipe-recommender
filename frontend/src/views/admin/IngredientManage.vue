<template>
  <div class="admin-ingredients">
    <!-- 顶部标题卡片 -->
    <el-card shadow="never" class="section-card">
      <div class="page-header">
        <div class="section-header">
          <el-icon><Food /></el-icon>
          <h3>食材管理</h3>
        </div>
        <el-button type="primary" size="small" @click="load">
          <el-icon><Refresh /></el-icon>
          刷新
        </el-button>
      </div>
      <div class="form-row">
        <el-input v-model="newName" placeholder="食材名称" style="width: 220px" />
        <el-input v-model="newCategory" placeholder="分类" style="width: 220px" />
        <el-button type="primary" @click="addIngredient">
          <el-icon><Plus /></el-icon>
          新增食材
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
      <el-table :data="filteredIngredients" v-loading="loading" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="名称" min-width="220">
          <template #default="{ row }">
            <span class="name-text">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="分类" width="180">
          <template #default="{ row }">
            <el-tag v-if="row.category" type="info" effect="plain" size="small">{{ row.category }}</el-tag>
            <span v-else style="color: #909399">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160" align="center" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="editIngredient(row)">
              <el-icon><Edit /></el-icon>
              编辑
            </el-button>
            <el-button type="danger" link size="small" @click="delIngredient(row)">
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
    <el-dialog v-model="editVisible" title="编辑食材" width="480px">
      <el-form label-width="100px">
        <el-form-item label="食材名称">
          <el-input v-model="editForm.name" placeholder="请输入食材名称" />
        </el-form-item>
        <el-form-item label="分类">
          <el-input v-model="editForm.category" placeholder="请输入分类" />
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

const ingredients = ref([])
const loading = ref(false)
const newName = ref('')
const newCategory = ref('')
const searchName = ref('')
const page = ref(1)
const pageSize = 100
const total = ref(0)

// 前端搜索过滤：匹配名称或分类（大小写不敏感）
const filteredIngredients = computed(() => {
  const kw = searchName.value.trim().toLowerCase()
  if (!kw) return ingredients.value
  return ingredients.value.filter(
    (i) =>
      (i.name || '').toLowerCase().includes(kw) ||
      (i.category || '').toLowerCase().includes(kw)
  )
})

const editVisible = ref(false)
const editForm = ref({ id: null, name: '', category: '' })

async function load() {
  loading.value = true
  try {
    const res = await api.get('/admin/ingredients', {
      params: { page: page.value, page_size: pageSize },
    })
    // 后端返回 { total, page, page_size, items }，需取 items 字段
    ingredients.value = Array.isArray(res) ? res : (res.items || [])
    total.value = res.total || ingredients.value.length
  } catch (e) {
    // 错误已由全局拦截器提示
  } finally {
    loading.value = false
  }
}

async function addIngredient() {
  if (!newName.value.trim()) {
    ElMessage.warning('请输入食材名称')
    return
  }
  const params = { name: newName.value.trim() }
  if (newCategory.value.trim()) params.category = newCategory.value.trim()
  try {
    await api.post('/admin/ingredients', null, { params })
    ElMessage.closeAll()  // 清除残留 toast，避免与新增成功消息混淆
    ElMessage.success('添加成功')
    newName.value = ''
    newCategory.value = ''
    // 新食材按 ID 升序排在末页，跳转到末页让用户看到刚创建的食材
    const lastPage = Math.max(1, Math.ceil((total.value + 1) / pageSize))
    page.value = lastPage
    load()
  } catch (e) {
    // 错误（如"食材已存在"）已由全局拦截器提示
  }
}

function editIngredient(row) {
  editForm.value = {
    id: row.id,
    name: row.name,
    category: row.category || '',
  }
  editVisible.value = true
}

async function saveEdit() {
  if (!editForm.value.name.trim()) {
    ElMessage.warning('食材名称不能为空')
    return
  }
  try {
    // 后端 update_ingredient 接口使用 Query 参数（name/category/image_url），需通过 params 传递
    await api.put(`/admin/ingredients/${editForm.value.id}`, null, {
      params: {
        name: editForm.value.name.trim(),
        category: editForm.value.category.trim() || undefined,
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

async function delIngredient(row) {
  try {
    await ElMessageBox.confirm(`确定删除食材「${row.name}」？`, '提示', { type: 'warning' })
  } catch (e) {
    return  // 用户点击取消
  }
  try {
    await api.delete(`/admin/ingredients/${row.id}`)
    ElMessage.closeAll()  // 清除残留的 ElMessageBox 遮罩和 toast
    ElMessage.success('删除成功')
    // 若当前页删除后为空且非第一页，回退一页
    if (ingredients.value.length === 1 && page.value > 1) {
      page.value -= 1
    }
    load()
  } catch (e) {
    // 错误（如"该食材被 N 个菜谱引用，无法删除"）已由全局拦截器提示
  }
}

onMounted(load)
</script>

<style scoped>
.admin-ingredients {
  max-width: 1200px;
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

.name-text {
  color: #1f2937;
  font-weight: 500;
}

.price-text {
  color: #e6a23c;
  font-weight: 600;
}

.pagination-wrap {
  display: flex;
  justify-content: center;
  margin-top: 20px;
}
</style>
