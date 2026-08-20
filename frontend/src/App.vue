<template>
  <router-view />
</template>

<script setup>
import { onMounted } from 'vue'
import { useUserStore } from './stores/user'

const userStore = useUserStore()

onMounted(() => {
  // 启动时校验登录态：token 过期/无效则静默清除，避免"自动登录成官方小厨但一操作就过期"
  userStore.validateSession()
})
</script>

<!--
  根组件（App.vue）
  ================
  作为 Vue 应用的根组件，仅包含 <router-view /> 用于渲染当前路由对应的页面组件。
  真正的布局由 MainLayout.vue（前台/个人中心/后台管理）或独立页面（登录/注册）提供。

  全局样式（不使用 scoped，作用域为全局）：
  - Reset 样式：移除浏览器默认边距，统一盒模型
  - Element Plus 主题定制：通过 CSS 变量覆盖默认主题色为蓝色系（#2563eb）
  - 公共工具类：.text-primary / .mt-8 等快捷类名
  - 滚动条美化、页面过渡动画等全局视觉优化
-->
<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

html,
body,
#app {
  height: 100%;
}

body {
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Hiragino Sans GB',
    'Microsoft YaHei', Arial, sans-serif;
  background-color: #f0f2f5;
  color: #1f2937;
  font-size: 14px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

a {
  text-decoration: none;
  color: inherit;
}

h1, h2, h3, h4, h5, h6 {
  font-weight: 600;
  color: #1f2937;
}

/* ====== Element Plus 全局主题定制 ====== */
:root {
  --el-color-primary: #2563eb;
  --el-color-primary-light-3: #3b82f6;
  --el-color-primary-light-5: #60a5fa;
  --el-color-primary-light-7: #93c5fd;
  --el-color-primary-light-8: #bfdbfe;
  --el-color-primary-light-9: #eff6ff;
  --el-color-primary-dark-2: #1d4ed8;

  --el-color-success: #22c55e;
  --el-color-warning: #f59e0b;
  --el-color-danger: #ef4444;
  --el-color-info: #64748b;

  --el-border-color: #e5e7eb;
  --el-border-color-light: #f3f4f6;
  --el-border-radius-base: 6px;
  --el-border-radius-small: 4px;

  --el-font-size-base: 14px;
  --el-text-color-primary: #1f2937;
  --el-text-color-regular: #606266;
  --el-text-color-secondary: #909399;
  --el-text-color-placeholder: #c0c4cc;

  --el-fill-color-blank: #ffffff;
  --el-fill-color-light: #f8fafc;
  --el-fill-color-lighter: #f5f7fa;
}

/* el-card 全局默认样式调整 */
.el-card {
  border-radius: 8px;
  border: 1px solid #ebeef5;
}

.el-card__header {
  padding: 16px 20px;
  border-bottom: 1px solid #f0f0f0;
  font-weight: 600;
}

.el-card__body {
  padding: 20px;
}

/* el-button 优化 */
.el-button {
  border-radius: 6px;
  font-weight: 500;
}

/* el-table 优化 */
.el-table {
  border-radius: 6px;
}

.el-table th.el-table__cell {
  background-color: #f8fafc !important;
  color: #1f2937;
  font-weight: 600;
}

/* el-input 优化 */
.el-input__wrapper {
  border-radius: 6px;
}

/* el-select 优化 */
.el-select-dropdown__item.selected {
  color: #2563eb;
  font-weight: 600;
}

/* el-tag 全局 */
.el-tag {
  border-radius: 4px;
  padding: 0 10px;
}

/* el-pagination 对齐 */
.el-pagination.is-background .el-pager li:not(.is-active):hover {
  color: #2563eb;
}

.el-pagination.is-background .el-pager li.is-active {
  background-color: #2563eb;
}

/* el-tabs 主题色同步 */
.el-tabs__item.is-active {
  color: #2563eb;
}

.el-tabs__active-bar {
  background-color: #2563eb;
}

.el-tabs__item:hover {
  color: #2563eb;
}

/* el-dialog 优化 */
.el-dialog {
  border-radius: 8px;
}

.el-dialog__header {
  padding: 18px 24px 14px;
  border-bottom: 1px solid #f0f0f0;
  margin-right: 0;
}

.el-dialog__body {
  padding: 20px 24px;
}

.el-dialog__footer {
  padding: 14px 24px 18px;
  border-top: 1px solid #f0f0f0;
  text-align: right;
}

/* el-drawer 优化 */
.el-drawer__header {
  padding: 16px 20px;
  border-bottom: 1px solid #f0f0f0;
  margin-bottom: 0;
}

.el-drawer__body {
  padding: 0;
}

/* 滚动条美化 */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 4px;
}

::-webkit-scrollbar-thumb {
  background: #d1d5db;
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: #9ca3af;
}

/* 页面过渡 */
.page-fade-enter-active,
.page-fade-leave-active {
  transition: opacity 0.2s ease;
}

.page-fade-enter-from,
.page-fade-leave-to {
  opacity: 0;
}

/* 工具类 */
.text-primary { color: #2563eb; }
.text-success { color: #22c55e; }
.text-warning { color: #f59e0b; }
.text-danger { color: #ef4444; }
.text-muted { color: #9ca3af; }

.m-0 { margin: 0; }
.mt-8 { margin-top: 8px; }
.mt-16 { margin-top: 16px; }
.mb-8 { margin-bottom: 8px; }
.mb-16 { margin-bottom: 16px; }

/* ===================== 移动端适配（全局，级联覆盖 Element Plus 组件） ===================== */
@media (max-width: 767px) {
  html, body {
    /* 避免横向滚动条撑破窄屏布局 */
    overflow-x: hidden;
  }

  /* 弹窗：窄屏下改为近全屏，并让内容区可滚动，避免超出可视区 */
  .el-dialog {
    width: calc(100vw - 24px) !important;
    margin-top: 3vh !important;
    max-height: 94vh;
    display: flex;
    flex-direction: column;
  }
  .el-dialog__body {
    overflow-y: auto;
    padding: 14px 16px;
  }
  .el-dialog__header {
    padding: 14px 16px 12px;
  }
  .el-dialog__footer {
    padding: 12px 16px 14px;
  }
  .el-dialog--center .el-dialog__footer {
    padding: 12px 16px 14px;
  }

  /* 抽屉：窄屏下全宽 */
  .el-drawer {
    width: 100% !important;
  }

  /* 表格：窄屏下允许横向滚动，防止撑破布局 */
  .el-table__body-wrapper {
    overflow-x: auto;
  }

  /* 内联表单：窄屏下每个表单项占满整行，自然换行 */
  .el-form--inline .el-form-item {
    margin-right: 0;
    width: 100%;
    display: block;
  }
  .el-form--inline .el-form-item__content {
    width: 100%;
  }

  /* 分页、底部操作区：窄屏下居中并允许换行 */
  .el-pagination {
    flex-wrap: wrap;
    justify-content: center;
    gap: 4px;
  }
}
</style>