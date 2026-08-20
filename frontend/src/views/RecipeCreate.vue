<template>
  <div class="recipe-create-page" v-loading="loading">
    <el-card class="header-card" shadow="never">
      <div class="page-header">
        <div class="header-left">
          <h1>创建菜谱</h1>
          <p class="subtitle">分享你的美味秘籍，让更多人学会这道菜</p>
        </div>
        <el-button @click="$router.push('/recipes')">
          <el-icon><ArrowLeft /></el-icon>
          返回列表
        </el-button>
      </div>
    </el-card>

    <!-- ===== 基本信息 ===== -->
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
        label-width="120px"
      >
        <el-form-item label="菜谱标题" prop="title">
          <el-input
            v-model="form.title"
            placeholder="例如：番茄炒蛋"
            maxlength="200"
            show-word-limit
          />
        </el-form-item>

        <el-form-item label="菜谱描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            placeholder="简要描述这道菜的特色、风味等..."
          />
        </el-form-item>

        <el-form-item label="封面图片">
          <el-input v-model="form.cover_image_url" placeholder="请输入图片URL（选填）" />
        </el-form-item>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="难度">
              <el-select v-model="form.difficulty" placeholder="请选择难度" style="width:100%">
                <el-option label="简单" value="easy" />
                <el-option label="中等" value="medium" />
                <el-option label="困难" value="hard" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="烹饪时间">
              <el-input-number v-model="form.cooking_time" :min="1" style="width:100%" controls-position="right">
                <template #suffix>分钟</template>
              </el-input-number>
            </el-form-item>
          </el-col>
        </el-row>

        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="份数">
              <el-input-number v-model="form.servings" :min="1" style="width:100%" controls-position="right">
                <template #suffix>人份</template>
              </el-input-number>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="预估成本">
              <el-input-number v-model="form.estimated_cost" :min="0" :step="0.1" :precision="1" style="width:100%" controls-position="right">
                <template #suffix>元</template>
              </el-input-number>
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
              v-for="tag in tagOptions"
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
      <div v-for="(ing, index) in form.ingredients" :key="index" class="dynamic-row">
        <div class="row-label">食材 {{ index + 1 }}</div>
        <el-row :gutter="12" align="middle">
          <el-col :span="8">
            <el-select
              v-model="ing.ingredient_id"
              placeholder="选择食材"
              filterable
              style="width:100%"
            >
              <el-option
                v-for="item in ingredientOptions"
                :key="item.id"
                :label="item.name"
                :value="item.id"
              />
            </el-select>
          </el-col>
          <el-col :span="4">
            <el-input v-model="ing.quantity" placeholder="用量" />
          </el-col>
          <el-col :span="5">
            <el-input v-model="ing.note" placeholder="备注（选填）" />
          </el-col>
          <el-col :span="3">
            <el-input-number v-model="ing.sort_order" :min="0" size="default" controls-position="right" style="width:100%" placeholder="排序" />
          </el-col>
          <el-col :span="4">
            <el-button type="danger" plain @click="removeIngredient(index)" :disabled="form.ingredients.length <= 1">
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
      <div v-for="(step, index) in form.steps" :key="index" class="dynamic-row step-row">
        <div class="step-header">
          <div class="step-label">
            <span class="step-num">{{ index + 1 }}</span>
            <span>步骤</span>
          </div>
          <el-button type="danger" plain size="small" @click="removeStep(index)" :disabled="form.steps.length <= 1">
            <el-icon><Delete /></el-icon>
            移除
          </el-button>
        </div>
        <el-input
          v-model="step.instruction"
          type="textarea"
          :rows="2"
          placeholder="描述这一步的做法..."
          style="margin-bottom:8px"
        />
        <el-row :gutter="12">
          <!-- <el-col :span="10">
            <el-input v-model="step.image_url" placeholder="步骤图片URL（选填）" />
          </el-col> -->
          <el-col :span="10">
            <el-input-number v-model="step.duration" :min="0" placeholder="时长" style="width:100%" controls-position="right">
              <template #suffix>分钟</template>
            </el-input-number>
          </el-col>
        </el-row>
      </div>
      <el-button type="primary" plain @click="addStep">
        <el-icon><Plus /></el-icon>
        添加步骤
      </el-button>
    </el-card>

    <div class="footer-bar">
      <el-button size="large" @click="$router.push('/recipes')">
        取消
      </el-button>
      <el-button size="large" @click="handleSubmit(true)" :loading="submitting">
        <el-icon><Tickets /></el-icon>
        存草稿
      </el-button>
      <el-button type="primary" size="large" @click="handleSubmit(false)" :loading="submitting">
        <el-icon><Check /></el-icon>
        发布菜谱
      </el-button>
    </div>
  </div>
</template>

<script setup>
/**
 * 菜谱创建页
 * ===========
 * 表单分为三个区域：
 * 1. 基本信息 —— 标题、描述、封面、难度、烹饪时间、份数、成本、标签
 * 2. 食材清单 —— 动态增删行，每行选择食材 + 填写用量 + 备注
 * 3. 烹饪步骤 —— 动态增删行，每行填写步骤描述 + 图片 + 时长
 *
 * 提交时：表单校验 → 组装 payload → POST /recipes → 跳转到新菜谱详情页
 */
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../api'

const router = useRouter()

const formRef = ref(null)
const loading = ref(true)
const submitting = ref(false)
const tagOptions = ref([])
const ingredientOptions = ref([])

const form = reactive({
  title: '',
  description: '',
  cover_image_url: '',
  difficulty: '',
  cooking_time: null,
  servings: null,
  estimated_cost: null,
  tag_ids: [],
  ingredients: [
    { ingredient_id: null, quantity: '', note: '', sort_order: 0 },
  ],
  steps: [
    { instruction: '', /* image_url: '', */ duration: null },  // 步骤图片功能，暂不启用
  ],
})

const rules = {
  title: [
    { required: true, message: '请输入菜谱标题', trigger: ['blur', 'change'] },
    { max: 200, message: '标题不能超过200个字符', trigger: ['blur', 'change'] },
  ],
}

function addIngredient() {
  form.ingredients.push({ ingredient_id: null, quantity: '', note: '', sort_order: form.ingredients.length })
}

function removeIngredient(index) {
  form.ingredients.splice(index, 1)
  form.ingredients.forEach((ing, i) => { ing.sort_order = i })
}

function addStep() {
  form.steps.push({ instruction: '', /* image_url: '', */ duration: null })  // 步骤图片功能，暂不启用
}

function removeStep(index) {
  form.steps.splice(index, 1)
}

// 加载标签和食材选项，供下拉选择使用
// 后端 /admin/tags 和 /admin/ingredients 返回分页结构 {total, page, page_size, items}
// 这里取 .items 数组并请求较大 page_size（最大 500）一次性获取全部选项
async function loadOptions() {
  try {
    const [tagsRes, ingredientsRes] = await Promise.all([
      api.get('/admin/tags', { params: { page_size: 500 } }),
      api.get('/admin/ingredients', { params: { page_size: 500 } }),
    ])
    tagOptions.value = tagsRes.items || []
    ingredientOptions.value = ingredientsRes.items || []
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

async function handleSubmit(asDraft = false) {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  // 业务校验：食材与步骤不能为空（防止提交空菜谱；存草稿除外）
  const validIngredients = form.ingredients.filter(ing => ing.ingredient_id)
  const validSteps = form.steps.filter(step => step.instruction && step.instruction.trim())
  if (!asDraft) {
    if (validIngredients.length === 0) {
      ElMessage.warning('请至少添加一条食材')
      return
    }
    if (validSteps.length === 0) {
      ElMessage.warning('请至少添加一条烹饪步骤')
      return
    }
  }

  submitting.value = true
  try {
    const payload = {
      title: form.title,
      description: form.description || undefined,
      cover_image_url: form.cover_image_url || undefined,
      difficulty: form.difficulty || undefined,
      cooking_time: form.cooking_time,
      servings: form.servings,
      estimated_cost: form.estimated_cost,
      tag_ids: form.tag_ids.length ? form.tag_ids : undefined,
      status: asDraft ? 'draft' : undefined,
      ingredients: validIngredients
        .map(ing => ({
          ingredient_id: ing.ingredient_id,
          quantity: ing.quantity,
          note: ing.note || undefined,
          sort_order: ing.sort_order,
        })),
      steps: validSteps
        .map((step, idx) => ({
          step_number: idx + 1,
          instruction: step.instruction,
          // image_url: step.image_url || undefined,  # 步骤图片功能，暂不启用
          duration: step.duration,
        })),
    }
    const res = await api.post('/recipes', payload)
    router.push(`/recipes/${res.id}`)
  } catch (e) {
    console.error(e)
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  loadOptions()
})
</script>

<style scoped>
.recipe-create-page {
  max-width: 1100px;
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

  /* 表单标签改为顶部对齐，输入框占满整行，避免横向溢出 */
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

  /* 基本信息多列与动态食材/步骤行的各列 → 单列堆叠 */
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