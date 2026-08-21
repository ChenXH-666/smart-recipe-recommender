<template>
  <div class="preferences-page">
    <el-card class="sec" shadow="never">
      <template #header>
        <div class="section-header">
          <el-icon><Operation /></el-icon>
          <h3>个性化偏好</h3>
          <span class="hint">这些偏好会用于推荐、套餐与 AI 建议（含过敏原/忌口过滤）</span>
        </div>
      </template>

      <el-form label-position="top">
        <el-form-item label="喜好的菜系 / 口味 / 做法（可多选）">
          <el-checkbox-group v-model="form.cuisines" class="tag-group">
            <el-checkbox v-for="c in cuisineOptions" :key="c" :value="c" border>{{ c }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>

        <el-form-item label="忌口 / 过敏原（勾选后，含这些食材的菜谱会被过滤掉）">
          <el-checkbox-group v-model="form.diet_tags" class="tag-group">
            <el-checkbox v-for="d in dietOptions" :key="d.value" :value="d.value" border>{{ d.label }}</el-checkbox>
          </el-checkbox-group>
          <el-divider style="margin:10px 0" />
          <el-checkbox v-model="form.vegetarian" border>我是素食者</el-checkbox>
        </el-form-item>

        <el-form-item label="用一句话描述你的偏好（可选，会作为补充上下文）">
          <el-input
            v-model="form.free_text"
            type="textarea"
            :rows="3"
            maxlength="200"
            show-word-limit
            placeholder="例如：我乳糖不耐、不吃香菜，喜欢川菜、常做快手菜，晚餐想清淡些…"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="saving" @click="save" style="min-width:120px">
            <el-icon><Check /></el-icon>保存偏好
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import api from '../../api'

const router = useRouter()

const cuisineOptions = [
  '川菜', '粤菜', '湘菜', '鲁菜', '本帮菜', '东北菜', '西北菜',
  '快捷家常', '清淡', '重口味', '无辣', '烤', '蒸', '炖汤',
  '面点烘焙', '减脂餐', '高蛋白', '甜品',
]

const dietOptions = [
  { value: 'seafood', label: '海鲜/水产' },
  { value: 'nuts', label: '坚果' },
  { value: 'dairy', label: '乳制品' },
  { value: 'egg', label: '鸡蛋' },
  { value: 'gluten', label: '麸质/面食' },
  { value: 'mushroom', label: '菌菇' },
  { value: 'soy', label: '大豆/豆制品' },
  { value: 'allium', label: '葱蒜' },
  { value: 'spicy', label: '吃辣(想避开)' },
]

const form = ref({ cuisines: [], diet_tags: [], free_text: '', vegetarian: false })
const saving = ref(false)

async function load() {
  try {
    const res = await api.get('/users/preferences')
    form.value = {
      cuisines: res.cuisines || [],
      diet_tags: res.diet_tags || [],
      free_text: res.free_text || '',
      vegetarian: (res.diet_tags || []).includes('veg'),
    }
  } catch (e) {
    console.error(e)
  }
}

async function save() {
  saving.value = true
  const diet_tags = [...form.value.diet_tags]
  if (form.value.vegetarian && !diet_tags.includes('veg')) diet_tags.push('veg')
  else if (!form.value.vegetarian) {
    const i = diet_tags.indexOf('veg')
    if (i >= 0) diet_tags.splice(i, 1)
  }
  try {
    await api.put('/users/preferences', {
      cuisines: form.value.cuisines,
      diet_tags,
      free_text: form.value.free_text,
    })
    ElMessage.success('偏好已保存')
    // 保存成功后自动返回上一页；无历史记录时（如直接访问）回个人中心资料页
    setTimeout(() => {
      if (window.history.length > 1) router.back()
      else router.push('/user/profile')
    }, 600)
  } catch (e) {
    ElMessage.error('保存失败，请稍后再试')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.preferences-page {
  max-width: 820px;
  margin: 0 auto;
}
.sec {
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
.hint {
  margin-left: auto;
  font-size: 12px;
  font-weight: 400;
  color: #909399;
}
.tag-group .el-checkbox {
  margin-right: 0;
  margin-bottom: 8px;
}
.tag-group {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
:deep(.el-form-item__label) {
  font-weight: 600;
  color: #303133;
}

@media (max-width: 767px) {
  .section-header {
    flex-wrap: wrap;
    gap: 6px;
  }
  .hint {
    margin-left: 0;
    width: 100%;
  }
}
</style>