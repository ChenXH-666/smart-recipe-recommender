<template>
  <div class="hot-recipes-page">
    <div class="page-head">
      <h2>热门菜谱</h2>
      <p>按浏览量排序的最受欢迎菜谱</p>
    </div>
    <div class="recipe-grid" v-loading="loading" element-loading-text="加载中...">
      <RecipeCard v-for="item in items" :key="item.id" :recipe="item" />
      <div v-if="items.length === 0 && !loading" class="empty-state">
        <el-icon :size="60"><DocumentDelete /></el-icon>
        <p>暂无菜谱</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { recipes } from '../api'
import RecipeCard from '../components/RecipeCard.vue'

const loading = ref(false)
const items = ref([])

async function load() {
  loading.value = true
  try {
    const res = await recipes.hot({ page_size: 24 })
    items.value = res.items || []
  } catch (e) {
    items.value = []
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.hot-recipes-page {
  max-width: 1400px;
}
.page-head {
  margin-bottom: 16px;
}
.page-head h2 {
  margin: 0;
  font-size: 22px;
  color: #1f2937;
}
.page-head p {
  margin: 4px 0 0;
  font-size: 13px;
  color: #909399;
}
.recipe-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
  min-height: 300px;
}
.empty-state {
  grid-column: 1 / -1;
  text-align: center;
  padding: 60px 20px;
  color: #909399;
}
</style>