<template>
  <div class="recipe-edit-page" v-loading="loading">
    <el-card class="header-card" shadow="never">
      <div class="page-header">
        <div class="header-left">
          <h1>编辑菜谱</h1>
          <p class="subtitle">修改你的菜谱信息</p>
        </div>
        <el-button @click="$router.push(`/recipes/${route.params.id}`)">
          <el-icon><ArrowLeft /></el-icon>
          返回详情
        </el-button>
      </div>
    </el-card>

    <!-- ===== 基本信息 ===== -->
    <el-card class="form-card" shadow="never" v-if="!loading">
      <template #header>
        <div class="section-header">
          <el-icon><Document /></el-icon>
          <h3>基本信息</h3>
        </div>
      </template>
      <el-form :model="form" label-width="120px">
        <el-form-item label="菜谱标题" required>
          <el-input v-model="form.title" placeholder="请输入菜谱标题" />
        </el-form-item>
        <el-form-item label="菜谱描述">
          <el-input v-model="form.description" type="textarea" :rows="3" placeholder="简要描述这道菜..." />
        </el-form-item>
        <el-form-item label="封面图片">
          <el-input v-model="form.cover_image_url" placeholder="图片URL" />
          <div v-if="form.cover_image_url" class="cover-preview">
            <img :src="form.cover_image_url" alt="封面预览" />
          </div>
        </el-form-item>
        <el-form-item label="难度">
          <el-select v-model="form.difficulty" placeholder="选择难度" style="width:200px">
            <el-option label="简单" value="easy" />
            <el-option label="中等" value="medium" />
            <el-option label="困难" value="hard" />
          </el-select>
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="烹饪时间">
              <el-input-number v-model="form.cooking_time" :min="1" placeholder="分钟" controls-position="right" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="份数">
              <el-input-number v-model="form.servings" :min="1" placeholder="人份" controls-position="right" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="预估成本">
              <el-input-number v-model="form.estimated_cost" :min="0" :step="0.1" :precision="1" placeholder="元" controls-position="right" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>

        <el-form-item label="标签">
          <el-select
            v-model="form.tag_ids"
            multiple
            placeholder="请选择标签"
            style="width:100%"
          >
            <el-option
              v-for="tag in allTags"
              :key="tag.id"
              :label="tag.name"
              :value="tag.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- ===== 食材清单 ===== -->
    <el-card class="form-card" shadow="never">
      <template #header>
        <div class="section-header">
          <el-icon><KnifeFork /></el-icon>
          <h3>食材清单</h3>
        </div>
      </template>
      <div v-for="(item, idx) in form.ingredients" :key="idx" class="dynamic-row">
        <div class="row-label">食材 {{ idx + 1 }}</div>
        <el-row :gutter="12" align="middle">
          <el-col :span="8">
            <el-select v-model="item.ingredient_id" placeholder="选择食材" filterable style="width:100%">
              <el-option v-for="ing in allIngredients" :key="ing.id" :label="ing.name" :value="ing.id" />
            </el-select>
          </el-col>
          <el-col :span="5">
            <el-input v-model="item.quantity" placeholder="用量" />
          </el-col>
          <el-col :span="7">
            <el-input v-model="item.note" placeholder="备注" />
          </el-col>
          <el-col :span="4">
            <el-button type="danger" plain @click="removeIngredient(idx)" :disabled="form.ingredients.length <= 1">
              <el-icon><Delete /></el-icon>
              移除
            </el-button>
          </el-col>
        </el-row>
      </div>
      <el-button type="primary" plain @click="addIngredient">
        <el-icon><Plus /></el-icon>
        添加食材
      </el-button>
    </el-card>

    <!-- ===== 烹饪步骤 ===== -->
    <el-card class="form-card" shadow="never">
      <template #header>
        <div class="section-header">
          <el-icon><List /></el-icon>
          <h3>烹饪步骤</h3>
        </div>
      </template>
      <div v-for="(step, idx) in form.steps" :key="idx" class="dynamic-row step-row">
        <div class="step-header">
          <div class="step-label">
            <span class="step-num">{{ idx + 1 }}</span>
            <span>步骤</span>
          </div>
          <el-button type="danger" plain size="small" @click="removeStep(idx)" :disabled="form.steps.length <= 1">
            <el-icon><Delete /></el-icon>
            移除
          </el-button>
        </div>
        <el-input v-model="step.instruction" type="textarea" :rows="2" placeholder="描述这一步的做法..." style="margin-bottom:8px" />
        <el-row :gutter="12">
          <!-- <el-col :span="12">
            <el-input v-model="step.image_url" placeholder="步骤图片URL（可选）" />
          </el-col> -->
          <el-col :span="12">
            <el-input-number v-model="step.duration" :min="0" placeholder="时长(分钟)" controls-position="right" style="width:100%" />
          </el-col>
        </el-row>
      </div>
      <el-button type="primary" plain @click="addStep">
        <el-icon><Plus /></el-icon>
        添加步骤
      </el-button>
    </el-card>

    <div class="footer-bar">
      <el-button size="large" @click="$router.push(`/recipes/${route.params.id}`)">
        取消
      </el-button>
      <el-button size="large" @click="handleSubmit(true)" :loading="submitting">
        <el-icon><Tickets /></el-icon>
        存草稿
      </el-button>
      <el-button type="primary" size="large" @click="handleSubmit(false)" :loading="submitting">
        <el-icon><Check /></el-icon>
        保存修改
      </el-button>
    </div>
  </div>
</template>

<script setup>
/**
 * 菜谱编辑页
 * ===========
 * 编辑流程：加载已有菜谱数据 → 填充到表单 → 用户修改 → PUT /recipes/:id 提交更新
 *
 * 1. onMounted 时并行执行：
 *    a. loadMeta()   → 加载标签和食材列表（供下拉/复选框使用）
 *    b. loadRecipe() → 加载菜谱详情并填充到 form 的 reactive 对象中
 * 2. 提交时组装 payload，调用 PUT /recipes/:id 更新
 */
import { ref, reactive, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api'
import { useUserStore } from '../stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const loading = ref(true)
const submitting = ref(false)
const allTags = ref([])
const allIngredients = ref([])

const form = reactive({
  title: '',
  description: '',
  cover_image_url: '',
  difficulty: '',
  cooking_time: null,
  servings: null,
  estimated_cost: null,
  tag_ids: [],
  ingredients: [],
  steps: [],
})

// 加载标签和食材选项
// 后端 /admin/tags 和 /admin/ingredients 返回分页结构 {total, page, page_size, items}
// 这里取 .items 数组并请求较大 page_size（最大 500）一次性获取全部选项
async function loadMeta() {
  const [tagsRes, ingsRes] = await Promise.all([
    api.get('/admin/tags', { params: { page_size: 500 } }),
    api.get('/admin/ingredients', { params: { page_size: 500 } }),
  ])
  allTags.value = tagsRes.items || []
  allIngredients.value = ingsRes.items || []
}

// 加载已有菜谱数据并填充到表单
async function loadRecipe() {
  try {
    const recipe = await api.get(`/recipes/${route.params.id}`)
    // 权限校验：仅作者本人可进入编辑页；非作者重定向到详情页
    // 后端虽然也会在 PUT 时拦截，但提前校验避免用户填写后才发现无权限
    if (userStore.user?.id !== recipe.author_id) {
      ElMessage.error('只有菜谱作者可以编辑此菜谱')
      router.replace(`/recipes/${route.params.id}`)
      return
    }
    form.title = recipe.title || ''
    form.description = recipe.description || ''
    form.cover_image_url = recipe.cover_image_url || ''
    form.difficulty = recipe.difficulty || ''
    form.cooking_time = recipe.cooking_time ?? null
    form.servings = recipe.servings ?? null
    // estimated_cost 后端返回 Decimal 序列化为字符串（如 "50.00"），
    // el-input-number 期望 Number，需手动转换以避免 type check 警告
    form.estimated_cost = recipe.estimated_cost != null ? Number(recipe.estimated_cost) : null

    form.tag_ids = (recipe.tags || []).map(t => t.id)

    form.ingredients = (recipe.ingredients || []).map(ing => ({
      ingredient_id: ing.ingredient?.id || ing.ingredient_id,
      quantity: ing.quantity || '',
      note: ing.note || '',
      sort_order: ing.sort_order ?? 0,
    }))

    form.steps = (recipe.steps || []).map(step => ({
      step_number: step.step_number ?? 0,
      instruction: step.instruction || '',
      // image_url: step.image_url || '',  // 步骤图片功能，暂不启用
      duration: step.duration ?? null,
    }))
  } catch (e) {
    // 404 或其他错误：保持表单为空，触发 v-if="!loading && !form.title" 兜底 UI
    // 错误已由全局拦截器提示，此处仅需静默处理避免 "Unhandled error" Vue 警告
  } finally {
    loading.value = false
  }
}

function addIngredient() {
  form.ingredients.push({
    ingredient_id: null,
    quantity: '',
    note: '',
    sort_order: form.ingredients.length,
  })
}

function removeIngredient(idx) {
  form.ingredients.splice(idx, 1)
}

function addStep() {
  form.steps.push({
    step_number: form.steps.length + 1,
    instruction: '',
    // image_url: '',  // 步骤图片功能，暂不启用
    duration: null,
  })
}

function removeStep(idx) {
  form.steps.splice(idx, 1)
}

async function handleSubmit(asDraft = false) {
  // 业务校验：食材与步骤不能为空（与后端 RecipeUpdate 一致；存草稿除外）
  if (!form.title || !form.title.trim()) {
    ElMessage.warning('请输入菜谱标题')
    return
  }
  const validIngredients = form.ingredients.filter(ing => ing.ingredient_id)
  const validSteps = form.steps.filter(step => step.instruction && step.instruction.trim())
  if (!asDraft) {
    if (validIngredients.length === 0) {
      ElMessage.warning('请至少保留一条食材')
      return
    }
    if (validSteps.length === 0) {
      ElMessage.warning('请至少保留一条烹饪步骤')
      return
    }
  }

  submitting.value = true
  try {
    const steps = validSteps.map((s, i) => ({
      ...s,
      step_number: i + 1,
    }))
    // 显式构造 payload，避免 `...form` 把空字符串字段（如 difficulty=""）
    // 直接传给后端。后端 difficulty 是 MySQL ENUM 列，空字符串会被拒绝。
    // 空值字段统一转为 undefined（JSON 中省略），让后端按 unset 处理。
    const payload = {
      title: form.title,
      description: form.description || undefined,
      cover_image_url: form.cover_image_url || undefined,
      difficulty: form.difficulty || undefined,
      cooking_time: form.cooking_time,
      servings: form.servings,
      estimated_cost: form.estimated_cost,
      tag_ids: form.tag_ids,
      status: asDraft ? 'draft' : undefined,
      ingredients: validIngredients,
      steps,
    }
    await api.put(`/recipes/${route.params.id}`, payload)
    router.push(`/recipes/${route.params.id}`)
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  Promise.all([loadMeta(), loadRecipe()])
})
</script>

<style scoped>
.recipe-edit-page {
  max-width: 1100px;
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

.cover-preview {
  margin-top: 8px;
  width: 200px;
  height: 120px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #ebeef5;
}

.cover-preview img {
  width: 100%;
  height: 100%;
  object-fit: cover;
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

.step-row {
  background: #f8fafc;
}

.step-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.step-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
  color: #1f2937;
}

.step-num {
  width: 24px;
  height: 24px;
  background: #2563eb;
  color: #fff;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
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
  :deep(.el-select) {
    width: 100% !important;
  }

  /* 基本信息与动态食材/步骤行的多列 → 单列堆叠 */
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

  /* 封面预览改自适应宽度 */
  .cover-preview {
    width: 100% !important;
    height: auto;
  }
  .cover-preview img {
    height: auto;
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