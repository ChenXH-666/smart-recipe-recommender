<template>
  <div class="meal-plan-create-page" v-loading="loading">
    <el-card class="header-card" shadow="never">
      <div class="page-header">
        <div class="header-left">
          <h1>{{ isEdit ? '编辑套餐' : '创建套餐' }}</h1>
          <p class="subtitle">精心搭配你的专属菜单，分享给更多人</p>
        </div>
        <el-button @click="$router.push('/meal-plans')">
          <el-icon><ArrowLeft /></el-icon>
          返回列表
        </el-button>
      </div>
    </el-card>

    <el-card class="form-card" shadow="never">
      <template #header>
        <div class="section-header">
          <el-icon><Document /></el-icon>
          <h3>基本信息</h3>
        </div>
      </template>
      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="100px"
      >
        <el-form-item label="套餐标题" prop="title">
          <el-input
            v-model="form.title"
            placeholder="例如：周末家庭轻食晚餐"
            maxlength="200"
            show-word-limit
          />
        </el-form-item>

        <el-form-item label="套餐描述" prop="description">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            placeholder="简要描述这个套餐的特色、适合人群等..."
          />
        </el-form-item>

        <el-form-item label="封面图片">
          <el-input v-model="form.cover_image_url" placeholder="请输入图片URL（选填）" />
        </el-form-item>

        <el-form-item label="是否公开">
          <el-switch
            v-model="form.is_public"
            active-text="公开分享"
            inactive-text="仅自己可见"
          />
        </el-form-item>
      </el-form>
    </el-card>

    <el-card class="form-card" shadow="never">
      <template #header>
        <div class="section-header">
          <el-icon><KnifeFork /></el-icon>
          <h3>套餐菜品</h3>
          <span class="section-tip">点击"添加菜品"将菜谱加入套餐</span>
        </div>
      </template>
      <div v-for="(item, index) in form.items" :key="index" class="dynamic-row">
        <div class="row-label">菜品 {{ index + 1 }}</div>
        <el-row :gutter="12" align="middle">
          <el-col :span="9">
            <el-select
              v-model="item.recipe_id"
              placeholder="搜索并选择菜谱"
              filterable
              remote
              clearable
              :remote-method="remoteSearchRecipe"
              :loading="recipeSearchLoading"
              style="width:100%"
            >
              <el-option
                v-for="r in selectRecipeOptions"
                :key="r.id"
                :label="r.title"
                :value="r.id"
              />
            </el-select>
          </el-col>
          <el-col :span="4">
            <div class="sort-btns">
              <el-button
                size="small" circle text
                :disabled="index === 0"
                title="上移"
                @click="moveUp(index)"
              ><el-icon><Top /></el-icon></el-button>
              <el-button
                size="small" circle text
                :disabled="index === form.items.length - 1"
                title="下移"
                @click="moveDown(index)"
              ><el-icon><Bottom /></el-icon></el-button>
            </div>
          </el-col>
          <el-col :span="7">
            <el-input v-model="item.note" placeholder="备注（选填，例如：作为主菜）" />
          </el-col>
          <el-col :span="4">
            <el-button type="danger" plain @click="removeItem(index)" :disabled="form.items.length <= 1">
              <el-icon><Delete /></el-icon>
              移除
            </el-button>
          </el-col>
        </el-row>
      </div>
      <el-button type="primary" plain @click="addItem()">
        <el-icon><Plus /></el-icon>
        添加菜品
      </el-button>
      <el-button type="success" plain :loading="favLoading" @click="addFromFavorites" style="margin-left:8px">
        <el-icon><Star /></el-icon>
        从我的收藏添加
      </el-button>
    </el-card>

    <div class="footer-bar">
      <el-button size="large" @click="$router.push('/meal-plans')">
        取消
      </el-button>
      <el-button size="large" @click="handleSubmit(true)" :loading="submitting">
        <el-icon><Tickets /></el-icon>
        存草稿
      </el-button>
      <el-button type="primary" size="large" @click="handleSubmit(false)" :loading="submitting">
        <el-icon><Check /></el-icon>
        {{ isEdit ? '更新套餐' : '创建套餐' }}
      </el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api'
import { useRecipeCartStore } from '../stores/recipeCart'

const router = useRouter()
const route = useRoute()
const cart = useRecipeCartStore()

// 是否从"菜谱合集"跳转而来（复制他人套餐不算，复制不清合集）
const fromCart = computed(() => !!route.query.recipe_ids && !route.query.copy)

const formRef = ref(null)
const loading = ref(true)
const submitting = ref(false)
const recipeOptions = ref([])

// 编辑模式：当 URL 含 ?id=xxx 时，加载已有套餐数据并使用 PUT 更新
const editId = computed(() => route.query.id ? Number(route.query.id) : null)
const isEdit = computed(() => editId.value !== null)

const form = reactive({
  title: '',
  description: '',
  cover_image_url: '',
  is_public: true,
  items: [
    { recipe_id: null, sort_order: 0, note: '' },
  ],
})

const rules = {
  title: [
    { required: true, message: '请输入套餐标题', trigger: 'blur' },
    { max: 200, message: '标题不能超过200个字符', trigger: 'blur' },
  ],
}

function addItem() {
  form.items.push({ recipe_id: null, sort_order: form.items.length, note: '' })
}

// 上移/下移：交换相邻菜品的位置并重新编号（最上/最下的对应按钮禁用）
function moveUp(index) {
  if (index <= 0) return
  const arr = form.items
  ;[arr[index - 1], arr[index]] = [arr[index], arr[index - 1]]
  arr.forEach((it, i) => { it.sort_order = i })
}
function moveDown(index) {
  if (index >= form.items.length - 1) return
  const arr = form.items
  ;[arr[index], arr[index + 1]] = [arr[index + 1], arr[index]]
  arr.forEach((it, i) => { it.sort_order = i })
}

// ---- 菜谱下拉：基础选项（前 50）+ 远程搜索命中 ----
// 搜索过程中只展示命中的菜谱（并保留已选中项），清空搜索后回落为基础选项 ----
const searchKeyword = ref('')
const searchResults = ref([])
const recipeSearchLoading = ref(false)
const selectRecipeOptions = computed(() => {
  if (searchKeyword.value) {
    const map = new Map()
    for (const r of searchResults.value) map.set(r.id, r)
    // 保留已选菜谱，防止选中项从下拉里消失
    for (const it of form.items) {
      if (it.recipe_id) {
        const known = recipeOptions.value.find((r) => r.id === it.recipe_id)
        if (known && !map.has(known.id)) map.set(known.id, known)
      }
    }
    return Array.from(map.values())
  }
  return recipeOptions.value
})
async function remoteSearchRecipe(query) {
  const kw = String(query || '').trim()
  recipeSearchLoading.value = true
  try {
    if (!kw) {
      searchKeyword.value = ''
      searchResults.value = []
      return
    }
    // 后端用 title/描述 模糊匹配，这里只保留"名称包含关键词"的，避免混入描述命中项
    const res = await api.get('/recipes', { params: { keyword: kw, page_size: 50 } })
    const kwl = kw.toLowerCase()
    searchKeyword.value = kw
    searchResults.value = (res.items || []).filter((r) => String(r.title).toLowerCase().includes(kwl))
  } catch (e) {
    console.error(e)
  } finally {
    recipeSearchLoading.value = false
  }
}

// 确保所有已选菜谱的标题始终可解析（交换/搜索选中后不会显示成数字）
watch(
  () => form.items.map((it) => it.recipe_id),
  (ids) => {
    const missing = ids.filter((id) => id && !recipeOptions.value.some((r) => r.id === id))
    if (missing.length) ensureRecipeOptions(missing)
  },
  { deep: true, immediate: true }
)

function removeItem(index) {
  form.items.splice(index, 1)
  form.items.forEach((item, i) => { item.sort_order = i })
}

// 从收藏菜谱中快选添加进套餐
const favLoading = ref(false)
async function addFromFavorites() {
  favLoading.value = true
  try {
    const res = await api.get('/users/favorites', { params: { favorite_type: 'recipe', page_size: 50 } })
    const favs = res.items || []
    let added = 0
    for (const f of favs) {
      const rid = f.data && f.data.id
      if (rid && !form.items.some((i) => i.recipe_id === rid)) {
        form.items.push({ recipe_id: rid, sort_order: form.items.length, note: '' })
        added++
      }
    }
    if (added === 0) ElMessage.info('收藏中暂没有可添加的新菜谱')
    else ElMessage.success(`已添加 ${added} 道收藏菜谱`)
  } catch (e) {
    console.error(e)
    ElMessage.error('获取收藏失败')
  } finally {
    favLoading.value = false
  }
}

async function loadRecipes() {
  try {
    const res = await api.get('/recipes', { params: { page_size: 50 } })
    recipeOptions.value = res.items || res
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

// 编辑模式：加载已有套餐数据，填充表单
async function loadMealPlan() {
  if (!editId.value) return
  try {
    const plan = await api.get(`/meal-plans/${editId.value}`)
    form.title = plan.title || ''
    form.description = plan.description || ''
    form.cover_image_url = plan.cover_image_url || ''
    form.is_public = plan.is_public !== false
    if (plan.items && plan.items.length > 0) {
      form.items = plan.items.map(item => ({
        recipe_id: item.recipe_id,
        sort_order: item.sort_order || 0,
        note: item.note || '',
      }))
    }
  } catch (e) {
    console.error(e)
  }
}

async function handleSubmit(asDraft = false) {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  submitting.value = true
  try {
    // 存草稿允许空菜品；正式提交才要求至少一道菜
    const hasItem = form.items.some(item => item.recipe_id)
    if (!asDraft && !hasItem) {
      ElMessage.warning('请至少添加一道菜')
      return
    }
    const payload = {
      title: form.title,
      description: form.description || undefined,
      cover_image_url: form.cover_image_url || undefined,
      is_public: form.is_public,
      status: asDraft ? 'draft' : undefined,
      items: form.items
        .filter(item => item.recipe_id)
        .map(item => ({
          recipe_id: item.recipe_id,
          sort_order: item.sort_order,
          note: item.note || undefined,
        })),
    }
    if (isEdit.value) {
      // 编辑模式：PUT 更新
      await api.put(`/meal-plans/${editId.value}`, payload)
      router.push(`/meal-plans/${editId.value}`)
    } else {
      // 创建模式：POST 新建
      const res = await api.post('/meal-plans', payload)
      // 仅当真正创建成功且是从合集跳转而来时才清空合集（复制他人套餐不清）
      if (fromCart.value) cart.clear()
      router.push(`/meal-plans/${res.id}`)
    }
  } catch (e) {
    console.error(e)
  } finally {
    submitting.value = false
  }
}

// 确保下拉里有这些菜谱可显示标题（下拉默认只载入前 50 道，缺失的按 id 补齐）
async function ensureRecipeOptions(ids) {
  const existing = new Set(recipeOptions.value.map((r) => r.id))
  const missing = ids.filter((id) => !existing.has(id))
  if (!missing.length) return
  const fetched = await Promise.all(
    missing.map((id) =>
      api.get(`/recipes/${id}`)
        .then((r) => ({ id: r.id, title: r.title }))
        .catch(() => null)
    )
  )
  for (const f of fetched) {
    if (f) recipeOptions.value.push(f)
  }
}

onMounted(async () => {
  await loadRecipes()
  if (isEdit.value) {
    await loadMealPlan()
  } else {
    // 从合集 / 复制他人套餐 跳转而来：?recipe_ids=1,2,3 → 预填套餐菜品
    const idsParam = route.query.recipe_ids
    if (idsParam) {
      const ids = String(idsParam).split(',').map(Number).filter(Boolean)
      if (ids.length) {
        form.items = ids.map((recipe_id, i) => ({ recipe_id, sort_order: i, note: '' }))
        await ensureRecipeOptions(ids)
      }
    }
    // 复制他人套餐：?copy=1 → 沿用其描述（不含标题与封面），供用户自定义标题
    if (route.query.copy && route.query.desc) {
      form.description = String(route.query.desc)
    }
  }
})
</script>

<style scoped>
.meal-plan-create-page {
  max-width: 1000px;
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

.header-left h1 {
  margin: 0 0 4px;
  font-size: 22px;
  color: #1f2937;
  font-weight: 700;
}

.header-left .subtitle {
  margin: 0;
  color: #909399;
  font-size: 13px;
}

.form-card {
  margin-bottom: 16px;
  border-radius: 8px;
  border: 1px solid #ebeef5;
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

.section-tip {
  margin-left: auto;
  color: #909399;
  font-size: 12px;
  font-weight: normal;
}

.sort-btns {
  display: flex;
  gap: 4px;
}
.sort-btns .el-button {
  margin-left: 0;
}

.dynamic-row {
  background: #f8fafc;
  padding: 14px 16px;
  border-radius: 8px;
  margin-bottom: 12px;
  border: 1px solid #ebeef5;
}

.row-label {
  font-size: 13px;
  font-weight: 500;
  color: #2563eb;
  margin-bottom: 8px;
}

.footer-bar {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #ebeef5;
  position: sticky;
  bottom: 0;
  box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.03);
}

/* ===== 移动端适配（≤767px 竖屏浏览） ===== */
@media (max-width: 767px) {
  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }

  /* 表单标签改为顶部对齐，输入框占满整行 */
  :deep(.el-form-item) {
    display: block;
  }
  :deep(.el-form-item__label) {
    float: none;
    display: block;
    width: auto !important;
    text-align: left;
    margin-bottom: 4px;
    line-height: 1.5;
  }
  :deep(.el-form-item__content) {
    margin-left: 0 !important;
    display: block;
  }

  /* 套餐菜品行的多列 → 单列堆叠 */
  :deep(.el-col) {
    flex: 0 0 100% !important;
    max-width: 100% !important;
  }
  .dynamic-row :deep(.el-col) {
    margin-bottom: 10px;
  }
  .dynamic-row :deep(.el-col):last-child {
    margin-bottom: 0;
  }

  /* 添加菜品 / 从我的收藏添加 按钮换行列排 */
  .form-card :deep(.el-button--primary),
  .form-card :deep(.el-button--success) {
    width: 100%;
    margin-left: 0 !important;
  }

  /* 底部操作按钮：列排占满整行 */
  .footer-bar {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }
  .footer-bar :deep(.el-button) {
    margin-left: 0;
    width: 100%;
  }
}
</style>
