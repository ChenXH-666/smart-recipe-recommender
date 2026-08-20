import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'

const STORAGE_KEY = 'recipe_cart'

function loadCart() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
  } catch {
    return []
  }
}

/**
 * 菜谱购物车 —— 浏览时"加购"菜谱，随后一键生成套餐。
 * 持久化到 localStorage，刷新不丢失。
 */
export const useRecipeCartStore = defineStore('recipeCart', () => {
  const items = ref(loadCart())
  const count = computed(() => items.value.length)

  function inCart(id) {
    return items.value.some((i) => i.id === id)
  }

  // 加购/取消：重复点击同一个菜谱即从购物车移除
  function toggle(recipe) {
    if (!recipe || !recipe.id) return
    const idx = items.value.findIndex((i) => i.id === recipe.id)
    if (idx >= 0) {
      items.value.splice(idx, 1)
    } else {
      items.value.push({
        id: recipe.id,
        title: recipe.title,
        cover_image_url: recipe.cover_image_url,
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

  return { items, count, inCart, toggle, remove, clear }
})