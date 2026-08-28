<template>
  <div class="recipe-card" @click="$router.push('/recipes/' + recipe.id)">
    <div class="card-image">
      <img
        v-if="displayImageUrl && !imgFailed"
        :src="displayImageUrl"
        :alt="recipe.title"
        loading="lazy"
        @error="onImgError"
      />
      <div v-if="!displayImageUrl || imgFailed" class="image-placeholder">
        <el-icon :size="48"><Picture /></el-icon>
      </div>
      <div v-if="recipe.difficulty" class="difficulty-tag" :class="'diff-' + recipe.difficulty">
        {{ difficultyMap[recipe.difficulty] || recipe.difficulty }}
      </div>
      <div
        class="todo-btn"
        :class="{ active: todoItems.some((i) => i.id === recipe.id) }"
        :title="todoItems.some((i) => i.id === recipe.id) ? '已加入待做，点击移除' : '加入待做（近期打算做）'"
        @click.stop.prevent="todo.toggleTodo(recipe)"
      >
        <el-icon :size="18"><Timer /></el-icon>
      </div>
      <div
        class="cart-btn"
        :class="{ active: cartItems.some((i) => i.id === recipe.id) }"
        :title="cartItems.some((i) => i.id === recipe.id) ? '已加入菜谱合集，点击移除' : '加入菜谱合集（一键生成套餐）'"
        @click.stop.prevent="cart.toggle(recipe)"
      >
        <el-icon :size="18"><Collection /></el-icon>
      </div>
    </div>
    <div class="card-body">
      <h3 class="card-title">{{ recipe.title }}</h3>
      <p class="card-desc" v-if="recipe.description">{{ recipe.description }}</p>
      <div class="card-tags" v-if="displayTags.length">
        <el-tag v-for="(tag, idx) in displayTags" :key="tag.id || tag.name || idx" size="small" type="info" effect="plain" class="tag-item">
          {{ tag.name }}
        </el-tag>
      </div>
      <div class="card-meta">
        <span v-if="recipe.cooking_time">
          <el-icon><Timer /></el-icon>
          {{ recipe.cooking_time }}分钟
        </span>
        <span v-if="recipe.servings">
          <el-icon><User /></el-icon>
          {{ recipe.servings }}人份
        </span>
        <span v-if="recipe.estimated_cost">
          <el-icon><Coin /></el-icon>
          ¥{{ recipe.estimated_cost }}
        </span>
        <span v-if="recipe.favorite_count" class="fav-count">
          <el-icon><Star /></el-icon>
          {{ recipe.favorite_count }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useRecipeCartStore } from '../stores/recipeCart'
import { useTodoListStore } from '../stores/todoList'

/**
 * RecipeCard 组件
 * ================
 * 角色：可复用的菜谱卡片组件，在首页、菜谱列表、收藏页等多个页面中使用。
 *
 * 设计决策：
 * - 纯展示组件（Presentational Component）：只接收 recipe prop，不做数据请求
 * - 难度标签用 CSS 类名控制颜色（diff-easy/diff-medium/diff-hard），而非动态 style
 * - 标签最多显示 3 个，避免卡片信息过载
 * - 点击卡片整跳转到菜谱详情页（而非内部嵌套 router-link，减少 DOM 层级）
 * - 封面图 loading="lazy"：列表/横向滑动区只加载视口内的图片，
 *   首页几十张外链封面不再一次性全部请求
 * - 封面图加载失败（外链图挂掉/防盗链）回退本地默认封面，避免裂图
 */
const props = defineProps({
  recipe: { type: Object, required: true },
})

// 菜谱购物车（storeToRefs 保持响应式，避免解包后状态不刷新）
const cart = useRecipeCartStore()
const { items: cartItems } = storeToRefs(cart)
const todo = useTodoListStore()
const { items: todoItems } = storeToRefs(todo)

const difficultyMap = { easy: '简单', medium: '中等', hard: '困难' }

// 外链封面加载失败标记（配合模板展示占位图）
const imgFailed = ref(false)

function onImgError() {
  imgFailed.value = true
}

// 统一标签格式：后端可能返回对象数组或字符串数组，前端都兼容
const displayTags = computed(() => {
  const tags = props.recipe.tags || []
  return tags.slice(0, 3).map(tag => {
    if (typeof tag === 'string') {
      return { id: tag, name: tag }
    }
    return tag
  })
})

// 统一图片地址（相对路径 /static/... 与绝对 https 外链均可直接作为 src）
const displayImageUrl = computed(() => props.recipe.cover_image_url || '')
</script>

<style scoped>
.recipe-card {
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid #ebeef5;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.recipe-card:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08);
  border-color: #dcdfe6;
}

.card-image {
  position: relative;
  width: 100%;
  height: 180px;
  overflow: hidden;
  background: #f5f7fa;
}

.card-image img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.3s;
}

.todo-btn,
.cart-btn {
  position: absolute;
  top: 8px;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.92);
  color: #6b7280;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.16);
  transition: all 0.2s;
  /* 确保不被图片/占位图等盖住，且只响应按钮自身点击 */
  z-index: 5;
  pointer-events: auto;
  /* 移动端触控目标足够大，便于手指点中 */
  border: 2px solid transparent;
  background-clip: padding-box;
}
.todo-btn { right: 52px; }
.cart-btn { right: 8px; }
.todo-btn > *,
.cart-btn > * {
  pointer-events: none;
}
.todo-btn.active,
.cart-btn.active {
  background: #2563eb;
  color: #fff;
}

.recipe-card:hover .card-image img {
  transform: scale(1.05);
}

.image-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #c0c4cc;
  background: linear-gradient(135deg, #f5f7fa 0%, #e8ecf1 100%);
}

.difficulty-tag {
  position: absolute;
  top: 12px;
  left: 12px;
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  color: #fff;
}

.diff-easy { background: #67c23a; }
.diff-medium { background: #e6a23c; }
.diff-hard { background: #f56c6c; }

.card-body {
  padding: 14px 16px 16px;
}

.card-title {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
  margin: 0 0 6px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-desc {
  font-size: 13px;
  color: #909399;
  margin: 0 0 10px;
  line-height: 1.5;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.card-tags {
  margin-bottom: 10px;
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.card-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #909399;
  align-items: center;
  padding-top: 8px;
  border-top: 1px dashed #ebeef5;
}

.card-meta span {
  display: flex;
  align-items: center;
  gap: 4px;
}

.fav-count {
  margin-left: auto;
  color: #f56c6c;
}
</style>