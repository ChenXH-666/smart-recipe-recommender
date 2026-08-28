<template>
  <div class="cooking-notes">
    <el-card class="header-card" shadow="never">
      <div class="page-header">
        <div class="header-info">
          <h1>烹饪心得</h1>
          <p class="subtitle">分享你的烹饪经验、技巧与感悟</p>
        </div>
        <el-button v-if="userStore.isLoggedIn" type="primary" size="large" @click="showCreateDialog = true">
          <el-icon><Edit /></el-icon>
          写心得
        </el-button>
      </div>
    </el-card>

    <el-card class="filter-bar" shadow="never">
      <div class="filter-row">
        <el-select
          v-model="filterRecipeId"
          placeholder="筛选关联菜谱"
          clearable
          filterable
          style="width: 220px"
        >
          <el-option v-for="r in recipeOptions" :key="r.id" :label="r.title" :value="r.id" />
        </el-select>
        <el-checkbox v-if="userStore.isLoggedIn" v-model="filterMine" border>
          只看自己
        </el-checkbox>
        <el-button text @click="resetFilters">重置筛选</el-button>
      </div>
    </el-card>

    <div class="notes-list" v-loading="loading" element-loading-text="加载中...">
      <el-card
        v-for="note in items"
        :key="note.id"
        shadow="never"
        class="note-card"
      >
        <div class="note-header">
          <el-avatar :size="40" :src="note.author_avatar_url || undefined" :icon="User" style="background:#2563eb" />
          <div class="note-user">
            <strong>{{ note.username || '匿名用户' }}</strong>
            <span class="note-time">{{ formatDate(note.created_at) }}</span>
          </div>
          <el-tag v-if="note.is_public" type="success" size="small" effect="plain">公开</el-tag>
          <el-tag v-else type="info" size="small" effect="plain">仅自己</el-tag>
        </div>
        <h3 class="note-title">
          <router-link class="title-link" :to="{ name: 'CookingNoteDetail', params: { id: note.id } }">
            <el-icon><Document /></el-icon>
            {{ note.title }}
          </router-link>
        </h3>
        <div
          class="note-content"
          :class="{ 'note-collapsed': !expandedIds.has(note.id) }"
          :ref="setNoteEl.bind(null, note.id)"
          @click="toggleExpand(note.id)"
        >
          <p>{{ note.content }}</p>
        </div>
        <div class="note-footer">
          <div class="meta-left">
            <span class="meta-item">
              <el-icon><View /></el-icon>
              {{ note.view_count || 0 }} 次浏览
            </span>
            <span class="meta-item comment-link" @click="$router.push(`/cooking-notes/${note.id}`)">
              <el-icon><ChatDotRound /></el-icon>
              {{ note.comment_count || 0 }} 条评论
            </span>
            <span class="meta-item" v-if="note.related_recipe_id">
              关联菜谱：
              <router-link
                class="recipe-link"
                :to="{ name: 'RecipeDetail', params: { id: note.related_recipe_id } }"
              >
                {{ note.related_recipe_title || recipeTitleMap[note.related_recipe_id] || '...' }}
              </router-link>
            </span>
          </div>
          <!-- 仅当内容真的超出 3 行（真实溢出）时才显示展开/收起提示，
               避免“刚好3行但判定可展开”的边界问题 -->
          <span
            class="expand-hint"
            v-if="expandableIds.has(note.id)"
            @click.stop="toggleExpand(note.id)"
          >
            {{ expandedIds.has(note.id) ? '收起' : '展开全文' }}
            <el-icon><ArrowDown v-if="!expandedIds.has(note.id)" /><ArrowUp v-else /></el-icon>
          </span>
        </div>
      </el-card>

      <div v-if="items.length === 0 && !loading" class="empty-state">
        <el-icon :size="64"><DocumentDelete /></el-icon>
        <p>还没有心得分享，快来写第一篇吧～</p>
      </div>
    </div>

    <div class="pagination" v-if="total > pageSize">
      <el-pagination
        background
        layout="prev, pager, next"
        :total="total"
        :page-size="pageSize"
        v-model:current-page="page"
        @current-change="load"
      />
    </div>

    <el-dialog v-if="showCreateDialog" v-model="showCreateDialog" title="分享烹饪心得" width="640px">
      <el-form :model="noteForm" :rules="noteRules" ref="noteFormRef" label-width="100px">
        <el-form-item label="标题" prop="title">
          <el-input v-model="noteForm.title" placeholder="给你的心得起个标题" maxlength="200" show-word-limit />
        </el-form-item>
        <el-form-item label="关联菜谱">
          <el-select v-model="noteForm.related_recipe_id" placeholder="可选" clearable filterable style="width:100%">
            <el-option v-for="r in recipeOptions" :key="r.id" :label="r.title" :value="r.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="内容" prop="content">
          <el-input v-model="noteForm.content" type="textarea" :rows="8" placeholder="分享你的烹饪体会、小技巧、失败教训..." />
        </el-form-item>
        <el-form-item label="公开分享">
          <el-switch v-model="noteForm.is_public" active-text="公开" inactive-text="仅自己" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" @click="submitNote" :loading="submitting">发布</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, nextTick } from 'vue'
import { useRoute } from 'vue-router'
import { useUserStore } from '../stores/user'
import { User } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { cookingNotes, recipes } from '../api'

const userStore = useUserStore()
const route = useRoute()
const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 10
const loading = ref(false)
const expandedIds = ref(new Set())  // 记录当前展开的笔记 ID
const expandableIds = ref(new Set())  // 记录真实存在内容溢出（超3行）的笔记 ID
const noteEls = {}  // 记录每条笔记的内容 DOM（非响应式，仅用于测量）

// 收集每条笔记的 DOM 节点引用
function setNoteEl(id, el) {
  if (el) noteEls[id] = el
  else delete noteEls[id]
}

/**
 * 测量每条笔记内容是否真的超过 3 行（真实溢出）。
 * 判据改为运行时检测 scrollHeight/clientHeight，取代原先依赖字符数的粗略判断，
 * 从而避免“内容刚好 3 行能显示完，却误显示展开全文”的边界问题。
 */
function measureOverflow() {
  nextTick(() => {
    const expandable = new Set()
    for (const idStr in noteEls) {
      const el = noteEls[idStr]
      if (el && el.scrollHeight > el.clientHeight + 2) expandable.add(Number(idStr))
    }
    expandableIds.value = expandable
  })
}
const showCreateDialog = ref(false)
const submitting = ref(false)
const noteFormRef = ref(null)
const recipeOptions = ref([])
const filterMine = ref(false)
const filterRecipeId = ref(null)
const recipeTitleMap = computed(() => {
  const map = {}
  recipeOptions.value.forEach((r) => { map[r.id] = r.title })
  return map
})
const noteForm = reactive({
  title: '',
  content: '',
  related_recipe_id: null,
  is_public: true,
})
const noteRules = {
  title: [{ required: true, message: '请输入标题', trigger: 'blur' }],
  content: [{ required: true, message: '请输入内容', trigger: 'blur' }],
}

function formatDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('zh-CN') + ' ' + new Date(d).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

/**
 * 展开/收起切换
 * 使用 Set 而非 Boolean 来管理状态，方便同时展开多个笔记。
 * 仅对真实存在溢出的笔记才产生可感知的效果。
 */
function toggleExpand(id) {
  if (!expandableIds.value.has(id)) return  // 内容未溢出，无需展开
  if (expandedIds.value.has(id)) {
    expandedIds.value.delete(id)
  } else {
    expandedIds.value.add(id)
  }
}

async function load() {
  loading.value = true
  try {
    const params = { page: page.value, page_size: pageSize }
    if (filterMine.value) params.mine = 1
    if (filterRecipeId.value) params.recipe_id = filterRecipeId.value
    const res = await cookingNotes.list(params)
    items.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    // 错误已由全局拦截器提示
  } finally {
    loading.value = false
    measureOverflow()  // 列表渲染后测量真实溢出
  }
}

function resetFilters() {
  filterMine.value = false
  filterRecipeId.value = null
}

watch([filterMine, filterRecipeId], () => {
  page.value = 1
  load()
})

// 加载菜谱选项（供发表心得时选择关联菜谱），后端限制 page_size 最大为 50
// 错误静默处理：加载失败不影响心得列表的展示
async function loadRecipes() {
  try {
    const res = await recipes.list({ page_size: 50 })
    recipeOptions.value = res.items || []
    // 若从菜谱详情"相关心得"跳转而来（?recipe_id=xx），且该菜谱不在下拉里，按 id 补齐标题
    if (filterRecipeId.value && !recipeOptions.value.some((r) => r.id === filterRecipeId.value)) {
      try {
        const r = await recipes.detail(filterRecipeId.value)
        recipeOptions.value.push({ id: r.id, title: r.title })
      } catch (e) { /* 忽略 */ }
    }
  } catch (e) { console.error(e) }
}

onMounted(() => {
  // 支持 ?recipe_id=xx 直接筛选关联菜谱（从菜谱详情"相关烹饪心得"进入）
  const qid = route.query.recipe_id
  if (qid) filterRecipeId.value = Number(qid)
  load()
  loadRecipes()
})

async function submitNote() {
  const valid = await noteFormRef.value.validate().catch(() => false)
  if (!valid) return
  submitting.value = true
  try {
    await cookingNotes.create(noteForm)
    ElMessage.success('心得发布成功')
    // 先关闭对话框，延迟重置表单与刷新列表，避免状态更新打断 el-dialog 的关闭
    showCreateDialog.value = false
    setTimeout(() => {
      noteForm.title = ''
      noteForm.content = ''
      noteForm.related_recipe_id = null
      noteForm.is_public = true
      noteFormRef.value?.clearValidate()
      page.value = 1
      load()
    }, 300)
  } catch (e) {
    // api 拦截器已提示错误
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  load()
  loadRecipes()
})
</script>

<style scoped>
.cooking-notes {
  max-width: 900px;
}

.header-card {
  margin-bottom: 16px;
  border-radius: 8px;
  border: 1px solid #ebeef5;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.header-info h1 {
  margin: 0 0 4px;
  font-size: 22px;
  color: #1f2937;
  font-weight: 700;
}

.header-info .subtitle {
  margin: 0;
  color: #909399;
  font-size: 13px;
}

.notes-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin-bottom: 24px;
}

.note-card {
  border-radius: 8px;
  border: 1px solid #ebeef5;
  transition: all 0.2s;
}

.note-card:hover {
  border-color: #bfdbfe;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.06);
}

.note-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.note-user {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.note-user strong {
  font-size: 14px;
  color: #1f2937;
  font-weight: 500;
}

.note-time {
  font-size: 12px;
  color: #909399;
}

.note-title {
  font-size: 17px;
  margin: 0 0 10px;
  font-weight: 600;
}

.title-link {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #1f2937;
  text-decoration: none;
  transition: color 0.2s;
}

.title-link:hover {
  color: #2563eb;
}

.note-content {
  color: #4b5563;
  line-height: 1.7;
  font-size: 14px;
  cursor: pointer;
  user-select: text;
}

.note-content p {
  margin: 0;
}

/* 折叠状态下用 max-height + overflow 截断为 3 行。
   相较于 -webkit-line-clamp，此方式能让 scrollHeight 正确反映内容高度，
   从而在运行时准确判断是否存在真实溢出（决定是否显示"展开全文"）。 */
.note-collapsed {
  max-height: 5.1em;  /* 3 行 × 行高 1.7 */
  overflow: hidden;
}

.note-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed #ebeef5;
  font-size: 12px;
  color: #909399;
}

.meta-item {
  display: flex;
  align-items: center;
  gap: 4px;
}
.comment-link {
  cursor: pointer;
  color: #2563eb;
  transition: opacity 0.2s;
}
.comment-link:hover {
  opacity: 0.75;
}

.expand-hint {
  display: flex;
  align-items: center;
  gap: 4px;
  color: #2563eb;
  cursor: pointer;
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: #909399;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #ebeef5;
}

.empty-state p {
  margin-top: 12px;
  font-size: 14px;
}

.pagination {
  display: flex;
  justify-content: center;
  padding: 16px 0;
}

.filter-bar {
  margin-bottom: 16px;
  border-radius: 8px;
  border: 1px solid #ebeef5;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.meta-left {
  display: flex;
  align-items: center;
  gap: 16px;
}

.recipe-link {
  color: #2563eb;
  text-decoration: none;
}

.recipe-link:hover {
  text-decoration: underline;
}

@media (max-width: 767px) {
  .page-header {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }
  .page-header .el-button {
    width: 100%;
    margin-left: 0;
  }
  /* 筛选栏纵向堆叠，内联宽度控件占满整行避免溢出 */
  .filter-row {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
  }
  .filter-row > * {
    width: 100% !important;
  }
  /* 底部元信息和展开提示换行 */
  .note-footer {
    flex-wrap: wrap;
    gap: 8px;
  }
  .meta-left {
    flex-wrap: wrap;
    gap: 10px;
  }
}
</style>