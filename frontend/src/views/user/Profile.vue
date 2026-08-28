<template>
  <div class="profile-page">
    <!-- 顶部：个性展示区（社交主页风格） -->
    <div class="hero">
      <div class="hero-cover"></div>
      <div class="hero-body">
        <el-avatar
          :size="72"
          :src="userStore.user?.avatar_url || undefined"
          :icon="User"
          class="hero-avatar"
        />
        <div class="hero-info">
          <h1>{{ userStore.user?.nickname || userStore.user?.username || '用户' }}</h1>
          <div class="hero-sub">
            <span>@{{ userStore.user?.username }}</span>
            <el-tag v-if="userStore.user?.role === 'admin'" type="danger" size="small" effect="plain">管理员</el-tag>
            <el-tag v-else type="info" size="small" effect="plain">普通用户</el-tag>
            <span class="hero-join">
              <el-icon><Calendar /></el-icon>注册于 {{ formatDate(userStore.user?.created_at) }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- 功能入口：社交主页式入口网格 -->
    <div class="entry-grid">
      <div v-for="e in entries" :key="e.path" class="entry-card" @click="$router.push(e.path)">
        <div class="entry-icon" :style="{ background: e.bg, color: e.color }">
          <el-icon :size="22"><component :is="e.icon" /></el-icon>
        </div>
        <div class="entry-text">
          <div class="entry-name">{{ e.name }}</div>
          <div class="entry-desc">{{ e.desc }}</div>
        </div>
        <el-icon class="entry-arrow"><ArrowRight /></el-icon>
      </div>
    </div>

    <!-- 账号设置 -->
    <el-card class="settings-card" shadow="never">
      <template #header>
        <div class="section-header">
          <el-icon><Setting /></el-icon>
          <h3>账号设置</h3>
        </div>
      </template>
      <el-row :gutter="20">
        <el-col :span="24" :md="12">
          <div class="block-title">修改资料</div>
          <el-form :model="profileForm" :rules="profileRules" ref="profileRef" label-width="90px">
            <el-form-item label="头像 URL">
              <div class="avatar-row">
                <el-avatar
                  :size="48"
                  :src="profileForm.avatar_url || undefined"
                  :icon="User"
                />
                <el-input v-model="profileForm.avatar_url" placeholder="粘贴头像图片 URL" clearable maxlength="500" />
              </div>
            </el-form-item>
            <el-form-item label="昵称" prop="nickname">
              <el-input v-model="profileForm.nickname" placeholder="设置你的昵称" maxlength="50" />
            </el-form-item>
            <el-form-item label="邮箱" prop="email">
              <el-input v-model="profileForm.email" placeholder="邮箱地址" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="updateProfile" :loading="updating">
                <el-icon><Check /></el-icon>保存修改
              </el-button>
            </el-form-item>
          </el-form>
        </el-col>
        <el-col :span="24" :md="12">
          <div class="block-title">修改密码</div>
          <el-form :model="pwdForm" :rules="pwdRules" ref="pwdRef" label-width="90px">
            <el-form-item label="原密码" prop="old_password">
              <el-input v-model="pwdForm.old_password" type="password" show-password placeholder="请输入原密码" />
            </el-form-item>
            <el-form-item label="新密码" prop="new_password">
              <el-input v-model="pwdForm.new_password" type="password" show-password placeholder="至少8位，含字母和数字" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="changePwd" :loading="pwdUpdating">
                <el-icon><Check /></el-icon>修改密码
              </el-button>
            </el-form-item>
          </el-form>
        </el-col>
      </el-row>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useUserStore } from '../../stores/user'
import { User } from '@element-plus/icons-vue'
import { users } from '../../api'
import { ElMessage } from 'element-plus'

const userStore = useUserStore()
const pwdRef = ref(null)
const profileRef = ref(null)
const updating = ref(false)
const pwdUpdating = ref(false)
const pwdForm = reactive({ old_password: '', new_password: '' })
const profileForm = reactive({
  nickname: userStore.user?.nickname || '',
  email: userStore.user?.email || '',
  avatar_url: userStore.user?.avatar_url || '',
})

// 功能入口（社交主页风格编排）
const entries = [
  { name: '待做清单', desc: '近期打算做的菜', icon: 'Timer', color: '#ea580c', bg: '#fff7ed', path: '/user/todo' },
  { name: '我的菜谱', desc: '菜谱与草稿管理', icon: 'KnifeFork', color: '#2563eb', bg: '#eff6ff', path: '/user/my-recipes' },
  { name: '我的套餐', desc: '套餐与草稿管理', icon: 'Calendar', color: '#059669', bg: '#ecfdf5', path: '/user/my-meal-plans' },
  { name: '我的收藏', desc: '我收藏的菜谱', icon: 'Star', color: '#f59e0b', bg: '#fff7ed', path: '/user/favorites' },
  { name: '浏览历史', desc: '我看过的内容', icon: 'Clock', color: '#8b5cf6', bg: '#f5f3ff', path: '/user/history' },
  { name: 'AI对话记录', desc: '与AI助手的对话', icon: 'ChatDotSquare', color: '#ec4899', bg: '#fdf2f8', path: '/user/conversations' },
  { name: '偏好设置', desc: '口味与忌口偏好', icon: 'Operation', color: '#0891b2', bg: '#ecfeff', path: '/user/preferences' },
]

const profileRules = {
  nickname: [
    { required: true, message: '请输入昵称', trigger: ['blur', 'change'] },
    { max: 50, message: '昵称不能超过 50 个字符', trigger: ['blur', 'change'] },
  ],
  email: [
    { required: true, message: '请输入邮箱地址', trigger: ['blur', 'change'] },
    { type: 'email', message: '请输入有效的邮箱地址', trigger: ['blur', 'change'] },
  ],
}
const pwdRules = {
  old_password: [{ required: true, message: '请输入原密码', trigger: ['blur', 'change'] }],
  new_password: [
    {
      required: true,
      validator: (rule, value, callback) => {
        if (!value) callback(new Error('请输入新密码'))
        else if (value.length < 8) callback(new Error('密码长度至少 8 位'))
        else if (!/[A-Za-z]/.test(value)) callback(new Error('密码必须包含至少一个字母'))
        else if (!/\d/.test(value)) callback(new Error('密码必须包含至少一个数字'))
        else callback()
      },
      trigger: ['blur', 'change'],
    },
  ],
}

function formatDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('zh-CN')
}

async function updateProfile() {
  if (!profileRef.value) return
  try {
    await profileRef.value.validate()
  } catch {
    return
  }
  updating.value = true
  try {
    const res = await users.updateProfile({
      nickname: profileForm.nickname,
      email: profileForm.email,
      avatar_url: profileForm.avatar_url,
    })
    userStore.user = { ...userStore.user, ...res }
    localStorage.setItem('user', JSON.stringify(userStore.user))
    ElMessage.closeAll()
    ElMessage.success('资料更新成功')
    profileRef.value.clearValidate()
  } catch (e) {
  } finally {
    updating.value = false
  }
}

async function changePwd() {
  if (pwdForm.old_password && pwdForm.new_password && pwdForm.old_password === pwdForm.new_password) {
    ElMessage.warning('新密码不能与原密码相同')
    return
  }
  const valid = await pwdRef.value.validate().catch(() => false)
  if (!valid) return
  pwdUpdating.value = true
  try {
    await users.changePassword(pwdForm)
    ElMessage.closeAll()
    ElMessage.success('密码修改成功')
    pwdRef.value?.resetFields()
  } catch (e) {
  } finally {
    pwdUpdating.value = false
  }
}
</script>

<style scoped>
.profile-page {
  max-width: 1100px;
}

/* 顶部个性区 */
.hero {
  border-radius: 16px;
  overflow: hidden;
  background: #fff;
  border: 1px solid #ebeef5;
  box-shadow: 0 4px 16px rgba(37, 99, 235, 0.06);
  margin-bottom: 20px;
}
.hero-cover {
  height: 40px;
  background: linear-gradient(120deg, #1d4ed8 0%, #3b82f6 45%, #60a5fa 100%);
  border-radius: 16px 16px 0 0;
}
.hero-body {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 22px 24px 28px;
}
.hero-avatar {
  width: 72px !important;
  height: 72px !important;
  border: 4px solid #fff;
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
  flex-shrink: 0;
}
.hero-info {
  padding-bottom: 0;
  margin-bottom: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  height: 72px;
}
.hero-info h1 {
  margin: 0 0 6px;
  font-size: 22px;
  color: #111827;
  font-weight: 700;
}
.hero-sub {
  display: flex;
  align-items: center;
  gap: 10px;
  color: #6b7280;
  font-size: 13px;
  flex-wrap: wrap;
}
.hero-join {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

/* 功能入口网格 */
.entry-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 14px;
  margin-bottom: 20px;
}
.entry-card {
  display: flex;
  align-items: center;
  gap: 14px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 14px;
  padding: 16px 18px;
  cursor: pointer;
  transition: all 0.2s;
}
.entry-card:hover {
  transform: translateY(-3px);
  box-shadow: 0 8px 22px rgba(37, 99, 235, 0.10);
  border-color: #bfdbfe;
}
.entry-icon {
  width: 46px;
  height: 46px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.entry-text {
  flex: 1;
  min-width: 0;
}
.entry-name {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
}
.entry-desc {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}
.entry-arrow {
  color: #c0c4cc;
}

/* 账号设置 */
.settings-card {
  border-radius: 14px;
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
.block-title {
  font-size: 13px;
  font-weight: 600;
  color: #6b7280;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px dashed #ebeef5;
}
.avatar-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}
.avatar-row .el-input {
  flex: 1;
}

@media (max-width: 767px) {
  .hero-body {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
  .hero-info {
    height: auto;
  }
  .avatar-row {
    align-items: flex-start;
  }
}
</style>