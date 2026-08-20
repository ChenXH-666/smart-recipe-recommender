<template>
  <div class="admin-dashboard" v-loading="loading">
    <!-- ===== 数据概览（分区卡片，与下方功能入口同风格） ===== -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <el-icon><DataAnalysis /></el-icon>
          <h3>数据概览</h3>
        </div>
      </template>
      <el-row :gutter="16">
        <el-col :xs="12" :sm="8" :md="6" v-for="item in statItems" :key="item.title">
          <div class="stat-tile" :style="{ borderColor: item.color }" @click="item.path && $router.push(item.path)">
            <div class="tile-icon" :style="{ background: item.iconBg, color: item.color }">
              <el-icon :size="26"><component :is="item.icon" /></el-icon>
            </div>
            <div class="tile-body">
              <div class="tile-num" :style="{ color: item.color }">{{ stats[item.key] }}</div>
              <div class="tile-label">{{ item.title }}</div>
            </div>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- ===== 快捷功能入口 ===== -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <el-icon><Menu /></el-icon>
          <h3>功能入口</h3>
        </div>
      </template>
      <el-row :gutter="16">
        <el-col :xs="12" :sm="8" :md="8" v-for="link in links" :key="link.path + link.title">
          <div class="link-card" @click="$router.push(link.path)">
            <div class="link-icon" :style="{ background: link.iconBg, color: link.color }">
              <el-icon :size="32"><component :is="link.icon" /></el-icon>
            </div>
            <div class="link-title">{{ link.title }}</div>
            <div class="link-desc">{{ link.desc }}</div>
          </div>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup>
/**
 * 后台管理仪表盘
 * ===============
 * 页面结构：
 * 1. 顶部统计卡片（菜谱总数 / 待审核菜谱 / 待审核套餐 / 用户总数）
 *    - 数据来源：GET /admin/stats
 *    - 点击卡片可跳转到对应管理页面
 * 2. 快捷功能入口（菜谱审核 / 套餐审核 / 标签管理 / 食材管理 / 用户管理）
 *    - 纯前端路由跳转，无需额外接口
 */
import { ref, onMounted } from 'vue'
import { DishDot, Collection, PriceTag, Food, User, Document, DataAnalysis, Menu } from '@element-plus/icons-vue'
import api from '../../api'

const loading = ref(true)
const stats = ref({ recipes: 0, pendingRecipes: 0, pendingPlans: 0, users: 0, totalPlans: 0, totalTags: 0, totalIngredients: 0 })

// 统计卡片：每张卡片可点击跳转到对应界面
//  - 菜谱/套餐浏览界面（/recipes、/meal-plans）对所有登录用户可见
//  - 菜谱/套餐/标签/食材/用户管理界面（/admin/*）为管理员专属
const statItems = [
  { title: '菜谱总数', key: 'recipes', icon: DishDot, color: '#2563eb', iconBg: '#eff6ff', path: '/recipes' },
  { title: '待审核菜谱', key: 'pendingRecipes', icon: Document, color: '#e6a23c', iconBg: '#fdf6ec', path: '/admin/recipe-audit' },
  { title: '套餐总数', key: 'totalPlans', icon: Collection, color: '#409eff', iconBg: '#ecf5ff', path: '/meal-plans' },
  { title: '待审核套餐', key: 'pendingPlans', icon: DataAnalysis, color: '#e6a23c', iconBg: '#fdf6ec', path: '/admin/meal-plan-audit' },
  { title: '标签总数', key: 'totalTags', icon: PriceTag, color: '#e6a23c', iconBg: '#fdf6ec', path: '/admin/tags' },
  { title: '食材总数', key: 'totalIngredients', icon: Food, color: '#f56c6c', iconBg: '#fef0f0', path: '/admin/ingredients' },
  { title: '用户总数', key: 'users', icon: User, color: '#67c23a', iconBg: '#f0f9eb', path: '/admin/users' },
]

// 功能入口链接（已去重，每个功能一个入口）
const links = [
  { path: '/admin/recipe-audit', title: '菜谱审核', desc: '审核用户提交的菜谱', icon: DishDot, color: '#2563eb', iconBg: '#eff6ff' },
  { path: '/admin/meal-plan-audit', title: '套餐审核', desc: '审核用户创建的套餐', icon: Collection, color: '#67c23a', iconBg: '#f0f9eb' },
  { path: '/admin/tags', title: '标签管理', desc: '管理菜谱标签分类', icon: PriceTag, color: '#e6a23c', iconBg: '#fdf6ec' },
  { path: '/admin/ingredients', title: '食材管理', desc: '管理食材与分类', icon: Food, color: '#f56c6c', iconBg: '#fef0f0' },
  { path: '/admin/users', title: '用户管理', desc: '管理用户与权限', icon: User, color: '#909399', iconBg: '#f4f4f5' },
]

onMounted(async () => {
  try {
    const res = await api.get('/admin/stats')
    stats.value = {
      recipes: res.total_recipes || 0,
      pendingRecipes: res.pending_recipes || 0,
      pendingPlans: res.pending_meal_plans || 0,
      totalPlans: res.total_meal_plans || 0,
      totalTags: res.total_tags || 0,
      totalIngredients: res.total_ingredients || 0,
      users: res.total_users || 0,
    }
  } catch (e) { console.error(e) }
  finally { loading.value = false }
})
</script>

<style scoped>
.admin-dashboard {
  max-width: 1400px;
}

.stats-row {
  margin-bottom: 16px;
}

.stat-tile {
  border: 1px solid #ebeef5;
  border-top: 4px solid transparent;
  border-radius: 8px;
  padding: 16px 12px;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 14px;
  cursor: pointer;
  background: #fff;
  transition: all 0.2s;
}

.stat-tile:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(37, 99, 235, 0.08);
}

.tile-icon {
  width: 52px;
  height: 52px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.tile-body {
  flex: 1;
  min-width: 0;
}

.tile-num {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.2;
}

.tile-label {
  font-size: 13px;
  color: #606266;
  margin-top: 4px;
}

.section-card {
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

.link-card {
  padding: 24px 16px;
  text-align: center;
  border-radius: 8px;
  border: 1px solid #ebeef5;
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 16px;
  background: #fff;
}

.link-card:hover {
  transform: translateY(-3px);
  border-color: #2563eb;
  box-shadow: 0 4px 16px rgba(37, 99, 235, 0.08);
}

.link-icon {
  width: 64px;
  height: 64px;
  border-radius: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin: 0 auto 12px;
}

.link-title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 4px;
}

.link-desc {
  font-size: 13px;
  color: #909399;
}

/* 移动端统计卡片和功能入口间距调整 */
@media (max-width: 768px) {
  .stat-tile {
    margin-bottom: 12px;
  }

  .link-card {
    margin-bottom: 12px;
  }
}

/* 更窄屏（≤767px）：统计卡片与功能入口改为单列占满，避免挤压 */
@media (max-width: 767px) {
  :deep(.el-col) {
    flex: 0 0 100% !important;
    max-width: 100% !important;
  }
}
</style>