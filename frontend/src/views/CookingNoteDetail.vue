<template>
  <div class="note-detail-page" v-loading="loading">
    <template v-if="note">
      <el-card class="detail-card" shadow="never">
        <div class="note-header">
          <el-avatar :size="48" :src="note.author_avatar_url || undefined" :icon="User" style="background:#2563eb" />
          <div class="note-user">
            <strong>{{ note.username || '匿名用户' }}</strong>
            <span class="note-time">{{ formatDate(note.created_at) }}</span>
          </div>
          <el-tag v-if="note.is_public" type="success" size="small" effect="plain">公开</el-tag>
          <el-tag v-else type="info" size="small" effect="plain">仅自己</el-tag>
          <div class="note-actions" v-if="canEdit">
            <el-button type="primary" size="small" plain @click="openEditDialog">
              <el-icon><Edit /></el-icon>
              编辑
            </el-button>
            <el-button type="danger" size="small" plain @click="handleDelete">
              <el-icon><Delete /></el-icon>
              删除
            </el-button>
          </div>
        </div>

        <h1 class="note-title">{{ note.title }}</h1>

        <div class="note-content markdown-body">
          <!-- 心得正文使用 Markdown 渲染（marked + DOMPurify 净化，防 XSS） -->
          <div v-html="renderMarkdown(note.content)"></div>
        </div>

        <div v-if="note.images && note.images.length" class="note-images">
          <el-image
            v-for="(img, idx) in note.images"
            :key="idx"
            :src="img"
            :preview-src-list="note.images"
            fit="cover"
            class="note-image"
          />
        </div>

        <div class="note-meta">
          <span v-if="note.view_count" class="meta-item">
            <el-icon><View /></el-icon>
            {{ note.view_count }} 次浏览
          </span>
          <span v-if="note.comment_count" class="meta-item">
            <el-icon><ChatDotRound /></el-icon>
            {{ note.comment_count }} 条评论
          </span>
          <router-link
            v-if="note.related_recipe_id"
            class="related-recipe"
            :to="{ name: 'RecipeDetail', params: { id: note.related_recipe_id } }"
          >
            <el-icon><Link /></el-icon>
            关联菜谱：{{ note.related_recipe_title || '...' }}
          </router-link>
        </div>
      </el-card>

      <el-card class="comments-card" shadow="never">
        <template #header>
          <div class="section-header">
            <el-icon><ChatDotRound /></el-icon>
            <h3>评论 ({{ total }})</h3>
          </div>
        </template>

        <div v-if="userStore.isLoggedIn" class="comment-form">
          <el-input
            v-model="commentForm.content"
            type="textarea"
            :rows="3"
            placeholder="写下你的想法..."
            maxlength="1000"
            show-word-limit
          />
          <div class="form-actions">
            <el-button type="primary" @click="submitComment" :loading="submitting">发表评论</el-button>
          </div>
        </div>
        <div v-else class="login-tip">
          <router-link to="/login">登录</router-link> 后即可发表评论
        </div>

        <div v-if="comments.length === 0" class="empty-inline">
          暂无评论，快来发表第一条评论吧～
        </div>

        <div v-for="c in comments" :key="c.id" class="comment-item">
          <div class="comment-header">
            <el-avatar :size="36" :src="c.user_avatar_url || undefined" :icon="User" style="background:#606266" />
            <div class="comment-user">
              <strong>{{ c.username || '匿名用户' }}</strong>
            </div>
            <span class="comment-time">{{ formatDate(c.created_at) }}</span>
            <el-button
              v-if="userStore.user?.id === c.user_id"
              type="danger"
              link
              size="small"
              @click="deleteComment(c.id)"
            >
              删除
            </el-button>
          </div>
          <p class="comment-content">{{ c.content }}</p>
        </div>

        <div class="pagination" v-if="total > pageSize">
          <el-pagination
            background
            layout="prev, pager, next"
            :total="total"
            :page-size="pageSize"
            v-model:current-page="page"
            @current-change="loadComments"
          />
        </div>
      </el-card>
    </template>

    <el-result
      v-else-if="!loading"
      icon="error"
      title="心得不存在或已被删除"
      sub-title="请返回心得列表浏览其他内容"
    >
      <template #extra>
        <el-button type="primary" @click="$router.push('/cooking-notes')">返回心得列表</el-button>
      </template>
    </el-result>

    <!-- 编辑心得对话框 -->
    <!-- v-if + append-to-body：v-if 确保 showEditDialog=false 时对话框从 DOM 移除（彻底关闭），
         append-to-body 将对话框移至 body，隔离组件内 loadNote/submitting 变更引发的重新渲染 -->
    <el-dialog v-if="showEditDialog" v-model="showEditDialog" title="编辑心得" width="640px" :close-on-click-modal="false" append-to-body>
      <el-form :model="editForm" label-width="100px">
        <el-form-item label="标题">
          <el-input v-model="editForm.title" placeholder="给你的心得起个标题" maxlength="200" show-word-limit />
        </el-form-item>
        <el-form-item label="关联菜谱">
          <el-select v-model="editForm.related_recipe_id" placeholder="可选" clearable filterable style="width:100%">
            <el-option v-for="r in recipeOptions" :key="r.id" :label="r.title" :value="r.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="内容">
          <el-input v-model="editForm.content" type="textarea" :rows="8" placeholder="分享你的烹饪体会、小技巧、失败教训..." />
        </el-form-item>
        <el-form-item label="公开分享">
          <el-switch v-model="editForm.is_public" active-text="公开" inactive-text="仅自己" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" @click="submitEdit" :loading="submitting">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '../stores/user'
import { User, Edit, Delete } from '@element-plus/icons-vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { renderMarkdown } from '../utils/markdown'
import { cookingNotes, recipes } from '../api'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const noteId = Number(route.params.id)

const loading = ref(true)
const note = ref(null)
const comments = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 10
const submitting = ref(false)
const commentForm = reactive({ content: '' })

// 编辑相关状态
const showEditDialog = ref(false)
const recipeOptions = ref([])
const editForm = reactive({
  title: '',
  content: '',
  related_recipe_id: null,
  is_public: true,
})

// 只有心得作者才能编辑/删除
const canEdit = computed(() => {
  return userStore.isLoggedIn && note.value && userStore.user?.id === note.value.user_id
})

function formatDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('zh-CN') + ' ' + new Date(d).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

async function loadNote() {
  try {
    note.value = await cookingNotes.detail(noteId)
  } catch (e) {
    note.value = null
  }
}

async function loadComments() {
  try {
    const res = await cookingNotes.comments(noteId, {
      page: page.value, page_size: pageSize,
    })
    comments.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    comments.value = []
    total.value = 0
  }
}

async function submitComment() {
  const content = commentForm.content.trim()
  if (!content) {
    ElMessage.warning('请输入评论内容')
    return
  }
  submitting.value = true
  try {
    await cookingNotes.createComment(noteId, { content })
    commentForm.content = ''
    page.value = 1
    await loadComments()
    if (note.value) note.value.comment_count += 1
  } finally {
    submitting.value = false
  }
}

async function deleteComment(commentId) {
  try {
    await cookingNotes.removeComment(commentId)
    await loadComments()
    if (note.value) note.value.comment_count = Math.max(0, note.value.comment_count - 1)
  } catch (e) {
    // api 拦截器已提示错误
  }
}

// 打开编辑对话框，将当前心得数据填充到表单
function openEditDialog() {
  if (!note.value) return
  editForm.title = note.value.title || ''
  editForm.content = note.value.content || ''
  editForm.related_recipe_id = note.value.related_recipe_id || null
  editForm.is_public = note.value.is_public !== false
  showEditDialog.value = true
}

// 提交编辑
async function submitEdit() {
  if (!editForm.title.trim() || !editForm.content.trim()) {
    ElMessage.warning('标题和内容不能为空')
    return
  }
  submitting.value = true
  try {
    await cookingNotes.update(noteId, editForm)
    // 先关闭对话框（配合 append-to-body 隔离组件内重新渲染），再显示 toast 和刷新数据
    showEditDialog.value = false
    ElMessage.closeAll()  // 清除残留 toast
    ElMessage.success('修改成功')
    // 延迟刷新数据，让 el-dialog 完成关闭动画后再更新 note.value
    setTimeout(() => {
      loadNote()
    }, 300)
  } catch (e) {
    // api 拦截器已提示错误
  } finally {
    submitting.value = false
  }
}

// 删除心得（带确认对话框）
// 拆分为两段 try/catch：第一段捕获用户取消，第二段处理 API 调用
// 避免删除成功后路由跳转打断 ElMessageBox 遮罩清理动画导致遮罩残留
async function handleDelete() {
  try {
    await ElMessageBox.confirm('确定要删除这篇心得吗？删除后无法恢复。', '删除确认', {
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch (e) {
    return  // 用户点击取消，不进行删除
  }
  try {
    await cookingNotes.remove(noteId)
    ElMessage.closeAll()  // 清除残留的 ElMessageBox 遮罩和 toast
    ElMessage.success('删除成功')
    // 延迟跳转，确保 ElMessageBox 的遮罩层已完全清理
    setTimeout(() => {
      router.push('/cooking-notes')
    }, 100)
  } catch (e) {
    // api 报错（拦截器已处理）
  }
}

// 加载菜谱选项（供编辑时选择关联菜谱）
async function loadRecipes() {
  try {
    const res = await recipes.list({ page_size: 50 })
    recipeOptions.value = res.items || []
  } catch (e) { console.error(e) }
}

onMounted(async () => {
  loading.value = true
  await loadNote()
  if (note.value) {
    await loadComments()
    // 预加载菜谱选项，供编辑对话框使用
    if (canEdit.value) loadRecipes()
  }
  loading.value = false
})
</script>

<style scoped>
.note-detail-page {
  max-width: 900px;
}

.detail-card {
  margin-bottom: 16px;
  border-radius: 8px;
  border: 1px solid #ebeef5;
}

.note-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.note-user {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.note-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

.note-user strong {
  font-size: 15px;
  color: #1f2937;
  font-weight: 500;
}

.note-time {
  font-size: 13px;
  color: #909399;
}

.note-title {
  font-size: 22px;
  font-weight: 700;
  color: #1f2937;
  margin: 0 0 16px;
  line-height: 1.4;
}

.note-content {
  color: #4b5563;
  line-height: 1.8;
  font-size: 15px;
  margin-bottom: 16px;
}

.note-content p {
  margin: 0;
  white-space: pre-wrap;
}

/* Markdown 渲染样式（心得正文） */
.note-content.markdown-body :deep(p) {
  margin: 8px 0;
  word-break: break-word;
}
.note-content.markdown-body :deep(h1),
.note-content.markdown-body :deep(h2),
.note-content.markdown-body :deep(h3),
.note-content.markdown-body :deep(h4) {
  margin: 14px 0 8px;
  font-weight: 600;
  color: #1f2937;
}
.note-content.markdown-body :deep(h1) { font-size: 20px; }
.note-content.markdown-body :deep(h2) { font-size: 18px; }
.note-content.markdown-body :deep(h3) { font-size: 16px; }
.note-content.markdown-body :deep(ul),
.note-content.markdown-body :deep(ol) {
  margin: 8px 0;
  padding-left: 24px;
}
.note-content.markdown-body :deep(li) { margin: 3px 0; }
.note-content.markdown-body :deep(strong) { font-weight: 600; color: #1f2937; }
.note-content.markdown-body :deep(em) { font-style: italic; color: #6b7280; }
.note-content.markdown-body :deep(code) {
  background: #f1f5f9;
  color: #db2777;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
}
.note-content.markdown-body :deep(pre) {
  background: #1e293b;
  color: #e2e8f0;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 10px 0;
}
.note-content.markdown-body :deep(pre code) {
  background: transparent;
  color: inherit;
  padding: 0;
}
.note-content.markdown-body :deep(blockquote) {
  margin: 10px 0;
  padding: 6px 12px;
  border-left: 3px solid #2563eb;
  background: #f8fafc;
  color: #6b7280;
}
.note-content.markdown-body :deep(table) {
  border-collapse: collapse;
  margin: 10px 0;
  width: 100%;
  font-size: 14px;
}
.note-content.markdown-body :deep(th),
.note-content.markdown-body :deep(td) {
  border: 1px solid #e5e7eb;
  padding: 6px 10px;
  text-align: left;
}
.note-content.markdown-body :deep(th) { background: #f8fafc; font-weight: 600; }
.note-content.markdown-body :deep(a) { color: #2563eb; text-decoration: none; }
.note-content.markdown-body :deep(a:hover) { text-decoration: underline; }
.note-content.markdown-body :deep(img) { max-width: 100%; border-radius: 6px; }

.note-images {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.note-image {
  width: 160px;
  height: 160px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #ebeef5;
}

.note-meta {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  padding-top: 16px;
  border-top: 1px dashed #ebeef5;
  font-size: 13px;
  color: #909399;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.related-recipe {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #2563eb;
  text-decoration: none;
}

.related-recipe:hover {
  text-decoration: underline;
}

.comments-card {
  border-radius: 8px;
  border: 1px solid #ebeef5;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}

.section-header h3 {
  margin: 0;
}

.comment-form {
  margin-bottom: 20px;
}

.form-actions {
  margin-top: 12px;
  text-align: right;
}

.login-tip {
  margin-bottom: 20px;
  padding: 12px 16px;
  background: #f5f7fa;
  border-radius: 6px;
  font-size: 14px;
  color: #606266;
}

.login-tip a {
  color: #2563eb;
  text-decoration: none;
}

.empty-inline {
  text-align: center;
  padding: 32px 0;
  color: #909399;
  font-size: 14px;
}

.comment-item {
  padding: 16px 0;
  border-bottom: 1px solid #f0f2f5;
}

.comment-item:last-child {
  border-bottom: none;
}

.comment-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}

.comment-user {
  flex: 1;
}

.comment-user strong {
  font-size: 14px;
  color: #1f2937;
  font-weight: 500;
}

.comment-time {
  font-size: 12px;
  color: #909399;
}

.comment-content {
  margin: 0 0 0 46px;
  color: #4b5563;
  line-height: 1.7;
  font-size: 14px;
  white-space: pre-wrap;
}

.pagination {
  display: flex;
  justify-content: center;
  padding-top: 16px;
}

@media (max-width: 767px) {
  .note-header {
    flex-wrap: wrap;
  }
  .note-actions {
    margin-left: 0;
    width: 100%;
  }
  .comment-header {
    flex-wrap: wrap;
    gap: 8px;
  }
  .comment-time {
    margin-left: 0;
    width: 100%;
  }
}
</style>