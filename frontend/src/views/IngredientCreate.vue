<template>
  <div class="ingredient-create-page">
    <el-card class="header-card" shadow="never">
      <div class="page-header">
        <div class="header-left">
          <h1>创建食材</h1>
          <p class="subtitle">找不到想要的食材？在这里提交，管理员审核通过后即可在创建菜谱时选用</p>
        </div>
        <el-button @click="goBack">
          <el-icon><ArrowLeft /></el-icon>
          返回
        </el-button>
      </div>
    </el-card>

    <el-card class="form-card" shadow="never">
      <template #header>
        <div class="section-header">
          <el-icon><Food /></el-icon>
          <h3>食材信息</h3>
        </div>
      </template>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="review-tip"
        title="提交后需要管理员审核，审核通过后该食材会出现在所有用户的食材下拉列表中"
      />

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-width="120px"
      >
        <el-form-item label="食材名称" prop="name">
          <el-input
            v-model="form.name"
            placeholder="例如：猫耳朵、酸豆角、羽衣甘蓝"
            maxlength="100"
            show-word-limit
          />
        </el-form-item>

        <el-form-item label="分类">
          <el-input
            v-model="form.category"
            placeholder="例如：蔬菜、肉类、水产、调味料（选填）"
            maxlength="50"
          />
        </el-form-item>

        <el-form-item label="图片URL">
          <el-input v-model="form.image_url" placeholder="请输入图片URL（选填）" maxlength="500" />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="submitting" @click="submit">
            <el-icon><Check /></el-icon>
            提交食材
          </el-button>
          <el-button @click="reset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { admin } from '../api'

const route = useRoute()
const router = useRouter()
const formRef = ref(null)
const submitting = ref(false)

const form = reactive({
  name: '',
  category: '',
  image_url: '',
})

const rules = {
  name: [
    { required: true, message: '请输入食材名称', trigger: 'blur' },
    { min: 1, max: 100, message: '名称不能超过 100 个字符', trigger: 'blur' },
  ],
}

// 提交食材：普通用户提交进入待审核状态，管理员直接通过（后端按角色自动处理）
async function submit() {
  try {
    await formRef.value.validate()
  } catch (e) {
    return
  }
  submitting.value = true
  try {
    const params = { name: form.name.trim() }
    if (form.category.trim()) params.category = form.category.trim()
    if (form.image_url.trim()) params.image_url = form.image_url.trim()
    await admin.createIngredient(params)
    ElMessage.success('提交成功，等待管理员审核')
    setTimeout(() => {
      goBack()
    }, 800)
  } catch (e) {
    // 错误已由全局拦截器提示（如食材已存在）
  } finally {
    submitting.value = false
  }
}

function reset() {
  form.name = ''
  form.category = ''
  form.image_url = ''
  formRef.value?.clearValidate()
}

// 返回来源页：从创建菜谱跳转来时回到创建菜谱页，否则返回上一页
function goBack() {
  if (route.query.from === 'recipe-create') {
    router.push('/recipes/create')
  } else {
    router.back()
  }
}
</script>

<style scoped>
.ingredient-create-page {
  max-width: 860px;
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

.page-header h1 {
  margin: 0 0 4px;
  font-size: 22px;
  color: #1f2937;
  font-weight: 700;
}

.page-header .subtitle {
  margin: 0;
  color: #909399;
  font-size: 13px;
}

.form-card {
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

.review-tip {
  margin-bottom: 18px;
}

@media (max-width: 767px) {
  .page-header {
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
  }
  .page-header .el-button {
    width: 100%;
    margin-left: 0;
  }
  .form-card :deep(.el-form-item__label) {
    width: 80px !important;
  }
  .form-card :deep(.el-form-item__content) {
    margin-left: 80px !important;
  }
}
</style>
