<template>
  <el-dialog
    :model-value="visible"
    @update:model-value="handleClose"
    title="AI 烹饪助手"
    width="760px"
    align-center
    :close-on-click-modal="false"
    :show-close="true"
  >
    <div class="chat-container">
      <div class="chat-toolbar" v-if="messages.length">
        <el-button size="small" text type="primary" @click="newChat">
          <el-icon><Plus /></el-icon>开始新对话
        </el-button>
      </div>
      <div class="chat-messages" ref="msgContainer">
        <div v-if="messages.length === 0 && !streaming" class="chat-empty">
          <div class="empty-icon">
            <el-icon :size="48"><MagicStick /></el-icon>
          </div>
          <h3>我是你的 AI 烹饪助手</h3>
          <p class="empty-desc">可以帮你：</p>
          <ul>
            <li>根据口味推荐菜谱</li>
            <li>按预算搭配套餐</li>
            <li>回答烹饪技巧问题</li>
            <li>提供食材替代建议</li>
          </ul>
          <div class="quick-tips">
            <el-tag
              v-for="tip in quickTips"
              :key="tip.label"
              class="qt"
              effect="plain"
              @click="sendQuickTip(tip.prompt)"
            >
              {{ tip.label }}
            </el-tag>
          </div>
        </div>
        <div v-for="(msg, idx) in messages" :key="idx" :class="['message', msg.role]">
          <div class="msg-avatar">
            <el-icon v-if="msg.role === 'user'"><User /></el-icon>
            <el-icon v-else><MagicStick /></el-icon>
          </div>
          <div class="msg-body">
            <div class="msg-bubble">
              <!-- 用户与 AI 消息统一用 Markdown 渲染，并去除内容首尾多余空行 -->
              <!-- html 为进列表时预计算的结果：v-for 中的 v-html 若直接调方法，
                   流式期间每个 chunk 触发重渲染都会对所有历史消息重新执行
                   marked.parse + DOMPurify.sanitize，长对话时明显卡顿 -->
              <div class="markdown-body" v-html="msg.html"></div>
            </div>
            <!-- 用户消息支持"任意位置重答"：编辑该条 → 删除其后所有消息并重新生成 -->
            <div v-if="msg.role === 'user' && editingIndex !== idx" class="msg-tools">
              <el-button size="small" text type="primary" :disabled="streaming" @click="startEdit(idx)">
                编辑
              </el-button>
            </div>
            <div v-if="msg.role === 'user' && editingIndex === idx" class="edit-panel">
              <el-input
                v-model="editText"
                type="textarea"
                :rows="2"
                placeholder="修改这条消息"
                @keydown.enter.exact.prevent="confirmEdit"
              />
              <div class="edit-actions">
                <el-button type="primary" size="small" @click="confirmEdit">确认</el-button>
                <el-button size="small" @click="cancelEdit">取消</el-button>
              </div>
            </div>
          </div>
        </div>
        <div v-if="streaming" class="message assistant">
          <div class="msg-avatar">
            <el-icon><MagicStick /></el-icon>
          </div>
          <div class="msg-bubble">
            <div v-if="streamText" class="markdown-body" v-html="renderMsg(streamText)"></div>
            <p v-else>正在思考...</p>
            <span class="typing-cursor">|</span>
          </div>
        </div>
      </div>
      <div class="chat-input">
        <el-input
          ref="chatInputRef"
          v-model="inputText"
          type="textarea"
          :rows="3"
          placeholder="输入你的问题，按 Enter 发送，Shift+Enter 换行..."
          @keydown.enter.exact.prevent="sendMessage"
        />
        <div class="input-actions">
          <el-button v-if="streaming" type="danger" @click="abortStream">
            <el-icon><VideoPause /></el-icon>
            中断
          </el-button>
          <el-button type="primary" :loading="streaming" @click="sendMessage">
            <el-icon><Promotion /></el-icon>
            发送
          </el-button>
        </div>
      </div>
    </div>
  </el-dialog>
</template>

<script setup>
/**
 * AI 对话组件
 * ============
 * 使用 Element Plus 的 Drawer（抽屉）从右侧滑出，作为 AI 助手的聊天界面。
 *
 * SSE（Server-Sent Events）流式传输设计：
 * =======================================
 * 1. 为什么不用 WebSocket？
 *    - AI 对话是单向流（服务器 → 客户端逐字推送），SSE 更轻量
 *    - 基于 HTTP，无需额外协议握手，与 JWT 认证自然兼容
 *    - 实现简单：fetch + ReadableStream + TextDecoder 即可
 *
 * 2. SSE 解析流程：
 *    a. fetch('/api/ai/chat') 发送 POST 请求
 *    b. 从 response.body 获取 ReadableStream
 *    c. 使用 TextDecoder 将 Uint8Array 解码为字符串
 *    d. 按换行符分割，逐行解析 'data: ...' 格式的 SSE 事件
 *    e. `[DONE]` 标记流结束，将 streamText 追加到 messages 列表
 *
 * 3. 为什么用 fetch 而非 axios？
 *    - axios 不支持 ReadableStream 的 response.body.getReader() 流式读取
 *    - 必须使用原生 fetch API 才能逐 chunk 处理 SSE 数据流
 *
 * 4. 会话管理：
 *    - 首次对话时 conversation_id 为 null，后端自动创建
 *    - 后续对话通过 X-Conversation-Id 响应头返回 conversation_id，保持上下文连续性
 *
 * 5. Markdown 渲染：
 *    - AI 返回的内容通常是 Markdown 格式（列表、加粗、代码块等）
 *    - 使用 marked 库将 Markdown 渲染为 HTML，提升可读性
 *
 * 6. 中断按钮（PRD 6.4 要求）：
 *    - 用户可在流式输出过程中点击"中断"按钮立即停止接收
 *    - 使用 AbortController 取消 fetch 请求
 *    - 已接收的内容会作为完整回复保留在对话列表中
 */
import { ref, watch, nextTick } from 'vue'
import { ElMessage, ElNotification } from 'element-plus'
// Markdown 渲染统一走公共工具（marked + DOMPurify 净化，防 XSS）
import { renderMarkdown } from '../utils/markdown'
// SSE 流式读取与 token 校验统一走公共工具
import { streamSSE } from '../utils/sse'
import { getAuthToken } from '../utils/auth'
import { recommendations, users, ai } from '../api'
import { useAiChatStore } from '../stores/aiChat'

const props = defineProps({ visible: Boolean })
const emit = defineEmits(['update:visible'])

const aiChatStore = useAiChatStore()

const messages = ref([])
const inputText = ref('')
const streaming = ref(false)
const streamText = ref('')
const msgContainer = ref(null)
const chatInputRef = ref(null)
const conversationId = ref(null)
// AbortController：用于中断进行中的 fetch 请求
let abortController = null

// 编辑消息（任意位置重答）状态
const editingIndex = ref(-1)
const editText = ref('')

const quickTips = ref([
  { label: '减脂晚餐', prompt: '帮我推荐几道适合减脂的晚餐，健康又美味' },
  { label: '快手家常菜', prompt: '我想做几道快手家常菜，简单省时' },
  { label: '川菜推荐', prompt: '我想吃川菜，帮我推荐几道正宗又好吃的' },
  { label: '高蛋白食谱', prompt: '帮我推荐几道高蛋白的菜' },
  { label: '50元以内二人餐', prompt: '我想在50元以内做一顿二人餐，帮我搭配' },
])

// 渲染消息：先去除内容首尾的多余空白/换行，再走 Markdown 渲染，避免前后出现空白行
const renderMsg = (t) => renderMarkdown((t || '').trim())

// 包装消息：进入列表时预计算 Markdown HTML（历史消息渲染一次即缓存复用，
// 流式重渲染不再重复解析；流式中的 streamText 仍逐 chunk 渲染，属打字机必要开销）
const withHtml = (m) => ({ ...m, html: renderMsg(m.content) })

// 打开抽屉时加载个性化"猜你想问"预设备题（登录后按用户偏好动态生成）
async function loadQuickTips() {
  try {
    const res = await recommendations.prompts({ limit: 6 })
    if (res.items && res.items.length) quickTips.value = res.items
  } catch (e) {
    console.error(e)
  }
}

// 载入指定历史会话的消息，并把 conversationId 设为该会话，后续提问自动续接上下文
async function loadConversationMessages(convId) {
  try {
    const res = await users.conversationDetail(convId)
    conversationId.value = convId
    messages.value = (res.messages || []).map(withHtml)
    nextTick(scrollToBottom)
  } catch (e) {
    console.error(e)
  }
}

// 开始一段全新对话：清空本地状态与 AI 助手内存中的上下文
function newChat() {
  newChatCleanup()
  loadQuickTips()
  nextTick(scrollToBottom)
}

// 抽屉打开时初始化对话：
//  - 从“对话记录”页面继续某个会话 → 载入该会话的历史消息
//  - 否则默认开启全新对话（不自动续接最近会话，由用户点“开始新对话”或“继续对话”控制）
async function initOpen() {
  newChatCleanup()
  const targetConvId = aiChatStore.consumeConversationId()
  if (targetConvId) {
    await loadConversationMessages(targetConvId)
  } else {
    loadQuickTips()
  }
  nextTick(scrollToBottom)
}

// 打开抽屉时清理流式与输入状态（供 initOpen 复用）
function newChatCleanup() {
  messages.value = []
  streamText.value = ''
  inputText.value = ''
  streaming.value = false
  conversationId.value = null
  editingIndex.value = -1
  editText.value = ''
}

// handleClose：关闭 Drawer
function handleClose() {
  emit('update:visible', false)
}

// renderMarkdown 由 ../utils/markdown 提供（marked + DOMPurify 净化）

function scrollToBottom() {
  if (msgContainer.value) {
    nextTick(() => {
      msgContainer.value.scrollTop = msgContainer.value.scrollHeight
    })
  }
}

function sendQuickTip(tip) {
  // 点击预设标签：只把问题填入输入框并聚焦，不自动发送，由用户确认后再发送
  inputText.value = tip
  nextTick(() => chatInputRef.value?.focus())
}

// 中断流式输出：保留已接收内容作为完整回复
function abortStream() {
  if (abortController) {
    abortController.abort()
    abortController = null
  }
  if (streaming.value) {
    // 将已接收的流文本作为 AI 回复保留
    if (streamText.value) {
      messages.value.push(withHtml({ role: 'assistant', content: streamText.value + '\n\n_(已中断)_' }))
    }
    streamText.value = ''
    streaming.value = false
    scrollToBottom()
  }
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || streaming.value) return

  const token = getAuthToken()
  if (!token) {
    ElMessage.warning('请先登录后使用 AI 对话')
    return
  }

  messages.value.push(withHtml({ role: 'user', content: text }))
  inputText.value = ''
  streaming.value = true
  streamText.value = ''
  scrollToBottom()

  // 为本次请求创建独立的 AbortController
  abortController = new AbortController()

  try {
    const { conversationId: convId } = await streamSSE({
      url: '/api/ai/chat',
      body: {
        message: text,
        conversation_id: conversationId.value,
      },
      signal: abortController.signal,
      onChunk: (chunk) => {
        streamText.value += chunk
        scrollToBottom()
      },
      onDone: () => {
        // 流结束：将累积的流文本作为 AI 回复保留
        messages.value.push(withHtml({ role: 'assistant', content: streamText.value }))
        streamText.value = ''
        streaming.value = false
        abortController = null
        scrollToBottom()
      },
    })
    // 从响应头获取会话 ID（streamSSE 返回），后续多轮对话复用
    if (convId) conversationId.value = parseInt(convId)
    // 兜底：流自然结束但未触发 onDone 时收敛 UI 状态
    if (streaming.value) {
      if (streamText.value) {
        messages.value.push(withHtml({ role: 'assistant', content: streamText.value }))
      }
      streamText.value = ''
      streaming.value = false
      abortController = null
    }
    // AI 完整回复结束：若抽屉是关闭状态（用户在别的页面），弹通知，点击可回到聊天窗口
    notifyAiFinished()
  } catch (e) {
    // 用户主动中断：abortController.abort() 会抛出 AbortError
    if (e && e.name === 'AbortError') {
      // 已在 abortStream 中处理状态，此处无需重复
      return
    }
    // 记录真实原因到控制台，便于排查（如网络/热重载导致的流中断）
    console.error('AI 流式对话失败:', e)
    messages.value.push(withHtml({ role: 'assistant', content: 'AI 服务暂时不可用，请稍后重试。' }))
    streaming.value = false
    abortController = null
  }
}

// 编辑指定用户消息：进入内联编辑态
function startEdit(idx) {
  if (streaming.value) return
  const msg = messages.value[idx]
  if (!msg || msg.role !== 'user') return
  editingIndex.value = idx
  editText.value = msg.content
}

function cancelEdit() {
  editingIndex.value = -1
  editText.value = ''
}

// 确认编辑：先取权威消息 ID，调用后端"重答编辑"（删除其后所有消息），
// 截断本地历史，再自动从该处重新生成回答
async function confirmEdit() {
  const text = editText.value.trim()
  const idx = editingIndex.value
  editingIndex.value = -1
  editText.value = ''
  if (!text || idx < 0) return

  try {
    // 重新拉取权威会话列表，拿到该位置用户消息的真实 id（新发送的消息本地可能没有 id）
    const detail = await users.conversationDetail(conversationId.value)
    const serverMsgs = detail.messages || []
    const target = serverMsgs[idx]
    if (!target || target.role !== 'user') {
      ElMessage.warning('该消息暂不可编辑')
      return
    }
    await ai.rewindEdit(conversationId.value, {
      message_id: target.id,
      new_content: text,
    })
    // 保留该条之前的消息，作为本次重答的上下文
    messages.value = messages.value.slice(0, idx)
    inputText.value = text
    scrollToBottom()
    // 自动从该处重新生成
    sendMessage()
  } catch (e) {
    console.error('重答编辑失败:', e)
    ElMessage.error('修改失败，请稍后再试')
  }
}

// AI 完整回复后提醒：右上角非侵入通知，点击回到聊天窗口（不抢焦点）
function notifyAiFinished() {
  if (props.visible) return // 抽屉正开着，用户在看着，无需提醒
  const last = messages.value[messages.value.length - 1]
  const summary = (last && last.content ? String(last.content) : '')
    .replace(/\s+/g, ' ').slice(0, 60)
  ElNotification({
    title: 'AI 烹饪助手已回复',
    message: summary || 'AI 已完成回复，点击查看',
    type: 'success',
    position: 'top-right',
    duration: 6000,
    onClick: () => {
      aiChatStore.open(conversationId.value)
    },
  })
}

watch(() => props.visible, (val) => {
  if (val) {
    initOpen()
  }
})
</script>

<style scoped>
.chat-container {
  display: flex;
  flex-direction: column;
  height: 68vh;
  min-height: 420px;
  background: #fff;
}

.chat-toolbar {
  display: flex;
  justify-content: flex-end;
  padding: 8px 16px 0;
  border-bottom: none;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px 16px;
  background: #f8fafc;
}

.chat-empty {
  text-align: center;
  padding: 40px 20px;
  color: #606266;
}

.empty-icon {
  width: 80px;
  height: 80px;
  margin: 0 auto 16px;
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%);
  color: #fff;
  border-radius: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.chat-empty h3 {
  margin: 0 0 8px;
  font-size: 18px;
  color: #1f2937;
  font-weight: 600;
}

.empty-desc {
  margin: 0;
  font-size: 14px;
  color: #606266;
}

.chat-empty ul {
  list-style: none;
  padding: 0;
  margin: 12px auto 20px;
  text-align: left;
  display: inline-block;
}

.chat-empty li {
  padding: 4px 0;
  font-size: 13px;
  color: #606266;
  padding-left: 20px;
  position: relative;
}

.chat-empty li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 10px;
  width: 6px;
  height: 6px;
  background: #2563eb;
  border-radius: 50%;
}

.quick-tips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  padding-top: 12px;
}

.qt {
  cursor: pointer;
  transition: all 0.2s;
  font-size: 12px;
  padding: 6px 12px;
}

.qt:hover {
  transform: translateY(-1px);
  border-color: #2563eb;
  color: #2563eb;
}

.message {
  display: flex;
  gap: 10px;
  margin-bottom: 16px;
  align-items: flex-start;
}

.message.user {
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

.message.user .msg-avatar {
  background: #2563eb;
}

.message.assistant .msg-avatar {
  background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
}

.msg-bubble {
  width: fit-content;
  max-width: 100%;
  min-width: 40px;
  padding: 12px 16px;
  border-radius: 14px;
  line-height: 1.6;
  font-size: 14px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  word-break: break-word;
}

/* 消息主体列：气泡 + 编辑控件（用户消息右对齐，AI 左对齐） */
.msg-body {
  flex: 1 1 auto;
  min-width: 0;
  max-width: 78%;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.message.user .msg-body {
  align-items: flex-end;
}
.message.assistant .msg-body {
  align-items: flex-start;
}
.msg-tools {
  line-height: 1;
}
.msg-tools .el-button {
  padding: 0 4px;
  height: auto;
  font-size: 12px;
}
.edit-panel {
  width: 100%;
  max-width: 320px;
  background: #fff;
  border: 1px solid #d9e2f0;
  border-radius: 8px;
  padding: 8px;
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.08);
}
.edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 8px;
}

.message.user .msg-bubble {
  background: #2563eb;
  color: #fff;
  border-bottom-right-radius: 4px;
}

.message.assistant .msg-bubble {
  background: #fff;
  color: #1f2937;
  border-bottom-left-radius: 4px;
  border: 1px solid #ebeef5;
}

.msg-bubble p {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

/* Markdown 渲染样式 —— 适配聊天气泡内的标题、列表、代码块等 */
/* 用户气泡为蓝底白字，Markdown 内文字保持白色以保证可读性 */
.message.user .markdown-body :deep(p),
.message.user .markdown-body :deep(li),
.message.user .markdown-body :deep(h1),
.message.user .markdown-body :deep(h2),
.message.user .markdown-body :deep(h3),
.message.user .markdown-body :deep(h4),
.message.user .markdown-body :deep(strong),
.message.user .markdown-body :deep(em),
.message.user .markdown-body :deep(blockquote) {
  color: #fff;
}

.message.user .markdown-body :deep(a) {
  color: #bfdbfe;
}

.message.user .markdown-body :deep(code) {
  background: rgba(255, 255, 255, 0.18);
  color: #fff;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  margin: 8px 0 6px;
  font-weight: 600;
  line-height: 1.4;
}

.markdown-body :deep(h1) { font-size: 18px; }
.markdown-body :deep(h2) { font-size: 16px; }
.markdown-body :deep(h3) { font-size: 15px; }
.markdown-body :deep(h4) { font-size: 14px; }

.markdown-body :deep(p) {
  margin: 6px 0;
  word-break: break-word;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 6px 0;
  padding-left: 22px;
}

.markdown-body :deep(li) {
  margin: 2px 0;
}

.markdown-body :deep(strong) {
  font-weight: 600;
  color: #1f2937;
}

.markdown-body :deep(em) {
  font-style: italic;
  color: #6b7280;
}

.markdown-body :deep(code) {
  background: #f1f5f9;
  color: #db2777;
  padding: 2px 6px;
  border-radius: 4px;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
}

.markdown-body :deep(pre) {
  background: #1e293b;
  color: #e2e8f0;
  padding: 12px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 8px 0;
}

.markdown-body :deep(pre code) {
  background: transparent;
  color: inherit;
  padding: 0;
}

.markdown-body :deep(blockquote) {
  margin: 8px 0;
  padding: 6px 12px;
  border-left: 3px solid #2563eb;
  background: #f8fafc;
  color: #6b7280;
}

.markdown-body :deep(table) {
  border-collapse: collapse;
  margin: 8px 0;
  width: 100%;
  font-size: 13px;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid #e5e7eb;
  padding: 6px 10px;
  text-align: left;
}

.markdown-body :deep(th) {
  background: #f8fafc;
  font-weight: 600;
}

.markdown-body :deep(a) {
  color: #2563eb;
  text-decoration: none;
}

.markdown-body :deep(a:hover) {
  text-decoration: underline;
}

.typing-cursor {
  display: inline-block;
  margin-left: 2px;
  animation: blink 1s infinite;
  color: #2563eb;
  font-weight: bold;
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

.chat-input {
  padding: 16px;
  border-top: 1px solid #ebeef5;
  background: #fff;
}

.input-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}

.input-actions .el-button {
  min-width: 96px;
}
</style>
