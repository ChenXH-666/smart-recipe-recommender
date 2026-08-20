import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import zhCn from 'element-plus/dist/locale/zh-cn.mjs'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import App from './App.vue'
import router from './router'

/**
 * 应用启动入口（main.js）
 * ========================
 * 启动顺序：创建 Vue 实例 → 注册 Pinia 状态管理 → 注册路由 → 注册 Element Plus UI 库 → 挂载
 *
 * 架构决策说明（答辩用）：
 * - Pinia：Vue 3 官方推荐的状态管理方案，替代 Vuex，TypeScript 支持更好
 * - Element Plus：选择它作为 UI 框架是因为：
 *   1. 国内使用广泛，中文文档完善，适合毕业设计
 *   2. 组件丰富（表格、表单、对话框、抽屉等），能覆盖后台管理 + 前台展示需求
 *   3. 支持按需导入和全局主题定制（在 App.vue 中通过 CSS 变量覆盖默认样式）
 * - 图标方案：全局注册所有 @element-plus/icons-vue 图标，模板中直接使用 <el-icon> 组件
 *   无需逐个 import，降低开发心智负担
 */
const app = createApp(App)
const pinia = createPinia()

// 注册插件
app.use(pinia)
app.use(router)
// Element Plus 中文语言包
app.use(ElementPlus, { locale: zhCn })

// 全局注册所有 Element Plus 图标（不必在每个组件中逐个 import）
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.mount('#app')