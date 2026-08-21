<template>
  <div class="todo-page">
    <div class="todo-head">
      <div>
        <h2>待做清单</h2>
        <p>暂存下一顿 / 近期打算做的菜，收藏是长久想吃，这里是近期要做</p>
      </div>
      <el-button v-if="todo.count" type="danger" plain @click="todo.clear()">清空</el-button>
    </div>

    <div v-if="!todo.count" class="todo-empty">
      <el-icon :size="64"><Timer /></el-icon>
      <p>还没有待做的菜，去菜谱卡片上点时钟图标，把近期想做的先收进来</p>
    </div>

    <div v-else class="todo-grid">
      <div v-for="it in todo.items" :key="it.id" class="todo-card" @click="$router.push('/recipes/' + it.id)">
        <div class="todo-cover">
          <img v-if="it.cover_image_url" :src="it.cover_image_url" :alt="it.title" />
          <div v-else class="cover-placeholder"><el-icon :size="40"><Picture /></el-icon></div>
        </div>
        <div class="todo-info">
          <h3>{{ it.title }}</h3>
        </div>
        <el-button
          size="small"
          type="danger"
          plain
          circle
          class="remove-btn"
          @click.stop="todo.remove(it.id)"
        >
          <el-icon><Close /></el-icon>
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useTodoListStore } from '../../stores/todoList'

const todo = useTodoListStore()
</script>

<style scoped>
.todo-page {
  max-width: 1100px;
}
.todo-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.todo-head h2 {
  margin: 0;
  font-size: 22px;
  color: #1f2937;
}
.todo-head p {
  margin: 4px 0 0;
  font-size: 13px;
  color: #909399;
}
.todo-empty {
  text-align: center;
  padding: 60px 20px;
  color: #909399;
}
.todo-empty p {
  margin-top: 12px;
}
.todo-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 16px;
}
.todo-card {
  position: relative;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #ebeef5;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.2s;
}
.todo-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.08);
}
.todo-cover {
  width: 100%;
  height: 130px;
}
.todo-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.cover-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #c0c4cc;
  background: #f5f7fa;
}
.todo-info {
  padding: 10px 12px;
}
.todo-info h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 500;
  color: #1f2937;
}
.remove-btn {
  position: absolute;
  top: 8px;
  right: 8px;
}
</style>