// 忌口/过敏原标签 → 中文展示
export const DIET_LABELS = {
  seafood: '海鲜/水产',
  nuts: '坚果',
  dairy: '乳制品',
  egg: '鸡蛋',
  gluten: '麸质/面食',
  mushroom: '菌菇',
  soy: '大豆/豆制品',
  allium: '葱蒜',
  spicy: '吃辣',
  meat: '荤食',
  veg: '素食',
}

/** 把忌口标签数组格式化为中文描述，如 ["seafood","veg"] → "海鲜/水产、素食" */
export function formatDietTags(tags) {
  return (tags || [])
    .filter((t) => t)
    .map((t) => DIET_LABELS[t] || t)
    .join('、')
}