import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'

const STORAGE_KEY = 'todo_recipes'

function loadTodo() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
  } catch {
    return []
  }
}

/**
 * 待做清单 —— 独立的"近期打算做"清单（区别于"菜谱合集/一键生成套餐"）。
 * 语义：把下一顿 / 明天 / 后天想做的菜暂存于此，提醒自己近期动手；临近吃饭时再挑。
 * 与收藏、选菜合集相互独立，各自持久化到 localStorage。
 */
export const useTodoListStore = defineStore('todoList', () => {
  const items = ref(loadTodo())
  const count = computed(() => items.value.length)

  function inTodo(id) {
    return items.value.some((i) => i.id === id)
  }

  // 加入/移出待做：重复点击同一菜谱即从待做移除
  function toggleTodo(recipe) {
    if (!recipe || !recipe.id) return
    const idx = items.value.findIndex((i) => i.id === recipe.id)
    if (idx >= 0) {
      items.value.splice(idx, 1)
    } else {
      items.value.push({
        id: recipe.id,
        title: recipe.title,
        cover_image_url: recipe.cover_image_url,
        added_at: Date.now(),
      })
    }
  }

  function remove(id) {
    items.value = items.value.filter((i) => i.id !== id)
  }

  function clear() {
    items.value = []
  }

  watch(
    items,
    (v) => { localStorage.setItem(STORAGE_KEY, JSON.stringify(v)) },
    { deep: true }
  )

  return { items, count, inTodo, toggleTodo, remove, clear }
})