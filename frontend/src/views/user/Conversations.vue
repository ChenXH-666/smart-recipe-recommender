<template>
  <div class="conversations-page">
    <el-card class="header-card" shadow="never">
      <div class="page-header">
        <div class="header-info">
          <h1>AI 对话记录</h1>
        </div>
        <span class="conv-count">共 {{ total }} 条对话</span>
      </div>
    </el-card>

    <div class="content" v-loading="loading" element-loading-text="加载中...">
      <div v-if="items.length" class="conv-grid">
        <div
          v-for="c in items"
          :key="c.id"
          class="conv-card"
          @click="showDetail(c.id)"
        >
          <!-- 顶部：用户提问气泡 + 右上角跳转箭头 -->
          <div class="bubble-header">
            <div class="user-bubble">
              <span class="bubble-text">{{ c.user_message || c.title || '新对话' }}</span>
            </div>
            <div class="arrow-btn" @click.stop="showDetail(c.id)" title="查看详情">
              <el-icon><TopRight /></el-icon>
            </div>
          </div>

          <!-- 中部：AI 回复摘要预览（Markdown 渲染 + 高度截断省略） -->
          <div class="ai-preview">
            <div class="markdown-body" v-html="renderMarkdown(c.ai_reply || '暂无回复内容')"></div>
          </div>

          <!-- 底部：删除勾选圆圈 + 继续对话 + 查看详情按钮 -->
          <div class="card-footer">
            <el-checkbox
              v-model="selectedId"
              :value="c.id"
              class="delete-check"
              @click.stop
              @change="(val) => onDeleteCheck(c, val)"
            >
              <span class="del-tip">删除</span>
            </el-checkbox>
            <div class="footer-actions">
              <el-button type="primary" round size="small" plain @click.stop="continueChat(c.id)">
                <el-icon><ChatDotSquare /></el-icon>继续对话
              </el-button>
              <el-button type="primary" round size="small" @click.stop="showDetail(c.id)">
                查看详情
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <div v-if="items.length === 0 && !loading" class="empty-state">
        <el-icon :size="64"><ChatDotSquare /></el-icon>
        <p>暂无对话记录，去和 AI 助手聊聊吧～</p>
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

    <!-- 对话详情弹窗：保留原实现，完整展示用户提问与 AI 全部回复 -->
    <el-dialog v-model="dialogVisible" title="对话详情" width="740px">
      <div v-if="detailMessages.length" class="msg-list">
        <div v-for="msg in detailMessages" :key="msg.id" :class="['msg', msg.role]">
          <div class="msg-avatar">
            <el-icon v-if="msg.role === 'user'"><User /></el-icon>
            <el-icon v-else><MagicStick /></el-icon>
          </div>
          <div class="msg-bubble">
            <div class="markdown-body" v-html="renderMsg(msg.content)"></div>
            <span class="msg-time">{{ formatDate(msg.created_at) }}</span>
          </div>
        </div>
      </div>
      <div v-else class="empty-inline">
        暂无对话内容
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
/**
 * AI 对话记录页面（卡片网格布局）
 * ==============================
 * 设计模式：会话卡片网格 → 点击卡片/箭头/查看详情打开对话详情（Dialog）
 *
 * 数据模型（AiConversationOut）：
 *   id, title, user_message（首条用户提问）, ai_reply（最后一条 AI 回复）
 *   - 顶部蓝色气泡展示 user_message
 *   - 中部摘要展示 ai_reply（前端截断省略）
 *
 * 交互：
 *   - 点击卡片任意区域/右上角箭头/右下角按钮 → 打开对话详情弹窗（逻辑不变）
 *   - 左下角删除圆圈勾选 → 二次确认 → 删除该条会话（复用原删除接口）
 */
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../../api'
import { useAiChatStore } from '../../stores/aiChat'
import { renderMarkdown } from '../../utils/markdown'

const aiChatStore = useAiChatStore()

const items = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = 12
const loading = ref(false)
const dialogVisible = ref(false)
const detailMessages = ref([])
const selectedId = ref(null)  // 当前勾选待删除的会话 ID

// 渲染消息：去除首尾多余空白/换行后按 Markdown 渲染，避免前后出现空白行
const renderMsg = (t) => renderMarkdown((t || '').trim())

function formatDate(d) {
  if (!d) return '—'
  const date = new Date(d)
  return date.toLocaleDateString('zh-CN') + ' ' + date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

async function load() {
  loading.value = true
  try {
    const res = await api.get('/users/conversations', { params: { page: page.value, page_size: pageSize } })
    items.value = res.items || []
    total.value = res.total || 0
  } catch (e) {
    // 错误已由全局拦截器提示
  } finally {
    loading.value = false
  }
}

async function showDetail(id) {
  try {
    const res = await api.get(`/users/conversations/${id}`)
    detailMessages.value = res.messages || []
    dialogVisible.value = true
  } catch (e) {
    console.error(e)
  }
}

// 继续对话：打开 AI 抽屉并载入该历史会话，问题可直接续追问
function continueChat(id) {
  aiChatStore.open(id)
}

// 删除会话（勾选左下角圆圈触发）—— PRD FR-A04，调用 DELETE /ai/conversations/:id
// val 为勾选后的值（勾选时等于 conv.id，取消时为 false/undefined），据此判断是否执行删除
async function onDeleteCheck(conv, val) {
  if (!val) {
    selectedId.value = null  // 取消勾选，不做任何事
    return
  }
  selectedId.value = conv.id
  const display = conv.title || conv.user_message || '新对话'
  try {
    await ElMessageBox.confirm(
      `确定要删除会话 "${display}" 吗？删除后无法恢复。`,
      '删除确认',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch {
    selectedId.value = null  // 用户取消，取消勾选
    return
  }
  try {
    await api.delete(`/ai/conversations/${conv.id}`)
    ElMessage.closeAll()  // 清除残留的 ElMessageBox 遮罩和 toast
    ElMessage.success('会话已删除')
    selectedId.value = null
    // 如果当前页只剩一条且不是第一页，删除后回到上一页
    if (items.value.length === 1 && page.value > 1) {
      page.value -= 1
    }
    load()
  } catch (e) {
    // 拦截器已显示错误
    selectedId.value = null
  }
}

onMounted(load)
</script>

<style scoped>
.conversations-page {
  max-width: 1200px;
}

.header-card {
  margin-bottom: 20px;
  border-radius: 12px;
  border: 1px solid #ebeef5;
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.header-info h1 {
  margin: 0;
  font-size: 22px;
  color: #1f2937;
  font-weight: 700;
}

.conv-count {
  color: #2563eb;
  font-size: 14px;
  background: #eff6ff;
  border-radius: 16px;
  padding: 4px 14px;
}

.content {
  min-height: 300px;
}

/* 卡片网格：自适应列数（宽屏 3 列，渐窄自动减少） */
.conv-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
  margin-bottom: 24px;
}

@media (max-width: 1200px) {
  .conv-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 768px) {
  .conv-grid {
    grid-template-columns: 1fr;
  }
}

/* 卡片：白色、大圆角、悬浮阴影，hover 阴影加深 */
.conv-card {
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 2px 12px rgba(31, 41, 55, 0.06);
  padding: 18px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 14px;
  transition: box-shadow 0.25s ease, transform 0.25s ease;
}

.conv-card:hover {
  box-shadow: 0 8px 24px rgba(37, 99, 235, 0.12);
  transform: translateY(-2px);
}

/* 顶部：用户提问气泡 + 跳转箭头 */
.bubble-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.user-bubble {
  flex: 1;
  min-width: 0;
  background: #2563eb;
  color: #fff;
  border-radius: 12px 12px 12px 4px;
  padding: 10px 14px;
  line-height: 1.5;
  font-size: 14px;
}

.bubble-text {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  word-break: break-word;
}

.arrow-btn {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: #eff6ff;
  color: #2563eb;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
}

.arrow-btn:hover {
  background: #2563eb;
  color: #fff;
}

/* 中部：AI 回复摘要预览（浅白圆角容器，Markdown 渲染后按高度截断） */
.ai-preview {
  background: #f8fafc;
  border-radius: 10px;
  padding: 12px 14px;
  color: #6b7280;
  font-size: 13px;
  line-height: 1.6;
  min-height: 66px;
  max-height: 110px;
  overflow: hidden;
  position: relative;
}

/* 底部淡出渐变，暗示内容被截断 */
.ai-preview::after {
  content: '';
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 30px;
  background: linear-gradient(180deg, rgba(248, 250, 252, 0) 0%, #f8fafc 100%);
  pointer-events: none;
}

.ai-preview .markdown-body :deep(p) {
  margin: 2px 0;
  color: #6b7280;
}

.ai-preview .markdown-body :deep(h1),
.ai-preview .markdown-body :deep(h2),
.ai-preview .markdown-body :deep(h3),
.ai-preview .markdown-body :deep(h4) {
  margin: 4px 0 2px;
  font-size: 14px;
  color: #374151;
}

.ai-preview .markdown-body :deep(ul),
.ai-preview .markdown-body :deep(ol) {
  margin: 2px 0;
  padding-left: 18px;
}

.ai-preview .markdown-body :deep(li) {
  margin: 1px 0;
}

.ai-preview .markdown-body :deep(strong) {
  font-weight: 600;
  color: #374151;
}

/* 底部：删除圆圈 + 查看详情按钮 */
.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.footer-actions {
  display: flex;
  gap: 6px;
  align-items: center;
}

.footer-actions .el-button + .el-button {
  margin-left: 0;
}

.delete-check {
  margin-right: 0;
}

.delete-check :deep(.el-checkbox__inner) {
  border-radius: 50%;
  border-color: #c0c4cc;
}

.delete-check :deep(.el-checkbox__inner:hover) {
  border-color: #f56c6c;
}

.delete-check :deep(.el-checkbox__input.is-checked .el-checkbox__inner) {
  background: #f56c6c;
  border-color: #f56c6c;
}

.del-tip {
  font-size: 12px;
  color: #909399;
  margin-left: 4px;
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: #909399;
  background: #fff;
  border-radius: 12px;
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

/* ===== 对话详情弹窗样式（原实现保留） ===== */
.msg-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-height: 60vh;
  overflow-y: auto;
  padding: 8px 4px;
}

.msg {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.msg.user {
  flex-direction: row-reverse;
}

.msg-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
}

.msg.user .msg-avatar {
  background: #2563eb;
}

.msg.assistant .msg-avatar {
  background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
}

.msg-bubble {
  max-width: 75%;
  padding: 12px 14px;
  border-radius: 12px;
  line-height: 1.6;
  font-size: 14px;
}

.msg.user .msg-bubble {
  background: #2563eb;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.msg.assistant .msg-bubble {
  background: #f1f5f9;
  color: #1f2937;
  border-bottom-left-radius: 4px;
}

.msg-bubble p {
  margin: 0 0 4px;
  white-space: pre-wrap;
  word-break: break-word;
}

/* Markdown 渲染样式（适配对话气泡） */
.msg-bubble .markdown-body :deep(h1),
.msg-bubble .markdown-body :deep(h2),
.msg-bubble .markdown-body :deep(h3),
.msg-bubble .markdown-body :deep(h4) {
  margin: 8px 0 6px;
  font-weight: 600;
  line-height: 1.4;
}

.msg-bubble .markdown-body :deep(p) {
  margin: 6px 0;
  white-space: normal;
  word-break: break-word;
}

.msg-bubble .markdown-body :deep(ul),
.msg-bubble .markdown-body :deep(ol) {
  margin: 6px 0;
  padding-left: 22px;
}

.msg-bubble .markdown-body :deep(li) {
  margin: 2px 0;
}

.msg-bubble .markdown-body :deep(strong) {
  font-weight: 600;
}

.msg-bubble .markdown-body :deep(code) {
  background: #eef1f5;
  color: #db2777;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
}

.msg-bubble .markdown-body :deep(pre) {
  background: #1e293b;
  color: #e2e8f0;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 8px 0;
}

.msg-bubble .markdown-body :deep(pre code) {
  background: transparent;
  color: inherit;
  padding: 0;
}

.msg-bubble .markdown-body :deep(blockquote) {
  margin: 8px 0;
  padding: 6px 12px;
  border-left: 3px solid #2563eb;
  background: rgba(37, 99, 235, 0.06);
  color: #6b7280;
}

.msg-bubble .markdown-body :deep(table) {
  border-collapse: collapse;
  margin: 8px 0;
  width: 100%;
  font-size: 13px;
}

.msg-bubble .markdown-body :deep(th),
.msg-bubble .markdown-body :deep(td) {
  border: 1px solid #e5e7eb;
  padding: 6px 10px;
  text-align: left;
}

/* 用户气泡蓝底白字：Markdown 内文字保持白色 */
.msg.user .markdown-body :deep(p),
.msg.user .markdown-body :deep(li),
.msg.user .markdown-body :deep(strong),
.msg.user .markdown-body :deep(h1),
.msg.user .markdown-body :deep(h2),
.msg.user .markdown-body :deep(h3),
.msg.user .markdown-body :deep(h4) {
  color: #fff;
}

.msg.user .markdown-body :deep(code) {
  background: rgba(255, 255, 255, 0.18);
  color: #fff;
}

.msg-time {
  font-size: 11px;
  opacity: 0.6;
  display: block;
  margin-top: 4px;
}

.empty-inline {
  text-align: center;
  padding: 40px 20px;
  color: #909399;
  font-size: 14px;
}

@media (max-width: 767px) {
  .page-header {
    flex-wrap: wrap;
    gap: 10px;
  }
  .card-footer {
    flex-wrap: wrap;
    gap: 10px;
  }
  .footer-actions {
    flex-wrap: wrap;
  }
}
</style>
