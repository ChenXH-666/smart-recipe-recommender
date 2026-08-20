<template>
  <div class="login-page">
    <div class="login-container">
      <div class="login-left">
        <div class="brand">
          <el-icon :size="64" color="#fff"><DishDot /></el-icon>
          <h1>智能菜谱推荐系统</h1>
          <p>基于 AI 大模型的个性化美食推荐平台</p>
        </div>
        <div class="features">
          <div class="feature-item">
            <el-icon :size="20"><Search /></el-icon>
            <span>智能菜谱搜索</span>
          </div>
          <div class="feature-item">
            <el-icon :size="20"><MagicStick /></el-icon>
            <span>AI 对话推荐</span>
          </div>
          <div class="feature-item">
            <el-icon :size="20"><User /></el-icon>
            <span>个性化套餐搭配</span>
          </div>
          <div class="feature-item">
            <el-icon :size="20"><DataAnalysis /></el-icon>
            <span>营养成分分析</span>
          </div>
        </div>
      </div>

      <div class="login-right">
        <div class="login-card">
          <div class="card-header">
            <h2>欢迎登录</h2>
            <p>请输入您的账号信息</p>
          </div>
          <el-form :model="form" :rules="rules" ref="formRef" class="login-form">
            <el-form-item prop="username">
              <el-input
                v-model="form.username"
                placeholder="请输入用户名或邮箱"
                size="large"
                :prefix-icon="User"
              />
            </el-form-item>
            <el-form-item prop="password">
              <el-input
                v-model="form.password"
                type="password"
                placeholder="请输入密码"
                size="large"
                show-password
                :prefix-icon="Lock"
              />
            </el-form-item>
            <el-form-item>
              <el-button
                type="primary"
                size="large"
                :loading="loading"
                @click="handleLogin"
                style="width: 100%; height: 44px; font-size: 16px"
              >
                登 录
              </el-button>
            </el-form-item>
          </el-form>
          <div class="card-footer">
            <span>还没有账号？</span>
            <el-button link type="primary" @click="$router.push('/register')">立即注册</el-button>
          </div>
        </div>
        <p class="copyright">智能菜谱推荐系统 © {{ new Date().getFullYear() }} 毕业设计项目</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '../stores/user'
import { User, Lock } from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const formRef = ref(null)
const loading = ref(false)
const form = reactive({ username: '', password: '' })
const rules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    await userStore.login(form.username, form.password)
    // 优先跳转到来源页（路由守卫未通过时携带的 redirect 参数），否则跳转首页
    const redirect = route.query.redirect
    router.push(typeof redirect === 'string' && redirect.startsWith('/') ? redirect : '/')
  } catch (err) {
    // 登录失败：用户名/密码错误、账号禁用等，API 拦截器已显示 ElMessage.error
    // 这里确保 loading 状态正确恢复，并可以添加额外的用户反馈
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh;
  background: linear-gradient(135deg, #f0f5ff 0%, #e8f0fe 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 20px;
}

.login-container {
  display: flex;
  width: 100%;
  max-width: 960px;
  height: 560px;
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.08);
}

.login-left {
  flex: 1;
  background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%);
  color: #fff;
  padding: 48px 40px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  position: relative;
  overflow: hidden;
}

.login-left::before {
  content: '';
  position: absolute;
  top: -50%;
  right: -50%;
  width: 200%;
  height: 200%;
  background: radial-gradient(circle, rgba(255, 255, 255, 0.08) 0%, transparent 50%);
  animation: rotate 30s linear infinite;
}

@keyframes rotate {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.brand {
  position: relative;
  z-index: 1;
}

.brand h1 {
  font-size: 28px;
  font-weight: 700;
  margin: 16px 0 8px;
  letter-spacing: 1px;
}

.brand p {
  font-size: 14px;
  opacity: 0.85;
  line-height: 1.6;
}

.features {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  position: relative;
  z-index: 1;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 10px;
  background: rgba(255, 255, 255, 0.1);
  padding: 12px 16px;
  border-radius: 6px;
  font-size: 14px;
  backdrop-filter: blur(10px);
}

.login-right {
  flex: 1;
  padding: 40px 56px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.login-card {
  max-width: 360px;
  width: 100%;
  margin: 0 auto;
}

.card-header {
  text-align: center;
  margin-bottom: 32px;
}

.card-header h2 {
  font-size: 26px;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 8px;
}

.card-header p {
  font-size: 14px;
  color: #9ca3af;
}

.login-form {
  margin-bottom: 24px;
}

.login-form :deep(.el-input__wrapper) {
  padding: 4px 12px;
  border-radius: 6px;
  box-shadow: 0 0 0 1px #e5e7eb;
}

.login-form :deep(.el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px #2563eb;
}

.login-form :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px #2563eb;
}

.card-footer {
  text-align: center;
  font-size: 14px;
  color: #6b7280;
}

.copyright {
  text-align: center;
  margin-top: 32px;
  font-size: 12px;
  color: #9ca3af;
}

@media (max-width: 767px) {
  .login-page {
    padding: 12px;
  }
  .login-container {
    flex-direction: column;
    height: auto;
    min-height: 0;
  }
  .login-left {
    padding: 32px 20px;
  }
  .login-right {
    padding: 28px 20px;
  }
  .brand h1 {
    font-size: 24px;
  }
  .features {
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }
  .feature-item {
    padding: 10px 12px;
    font-size: 13px;
  }
}
</style>
