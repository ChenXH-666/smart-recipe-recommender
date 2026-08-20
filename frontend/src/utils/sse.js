/**
 * SSE（Server-Sent Events）流式请求工具
 * ========================
 * 统一封装 AI 对话的 SSE 流式读取逻辑，供 AiChatDialog 使用
 * （fetch + ReadableStream + TextDecoder + data: 协议解析）。
 *
 * 为什么不用 axios？
 *   axios 不支持 response.body.getReader() 流式读取，必须用原生 fetch。
 *
 * SSE 协议（与后端 app/api/ai.py 约定）：
 *   - : keepalive                → 注释行（忽略，后端用于保活防代理超时）
 *   - data: {json-encoded-text}  → 文本 chunk（用 JSON 编码防止换行破坏协议）
 *   - data: [DONE]               → 流结束标记
 *
 * 用法：
 *   const { conversationId } = await streamSSE({
 *     url: '/api/ai/chat',
 *     body: { message: '你好', conversation_id: null },
 *     onChunk: (text) => { ... },
 *     onDone: () => { ... },
 *     signal: abortController.signal,
 *   })
 */
import { getAuthToken } from './auth'

/**
 * 发起 SSE 流式请求并逐 chunk 回调。
 *
 * @param {Object} opts
 * @param {string} opts.url 请求地址（如 /api/ai/chat）
 * @param {Object} opts.body 请求体（将 JSON.stringify）
 * @param {Object} [opts.headers] 额外请求头
 * @param {Function} [opts.onChunk] 文本 chunk 回调：(text: string) => void
 * @param {Function} [opts.onDone] 流结束回调：() => void
 * @param {AbortSignal} [opts.signal] 中断信号（AbortController.signal）
 * @param {number} [opts.connectTimeoutMs=30000] 连接超时（首字节等待时间，默认 30s）
 * @returns {Promise<{conversationId: string|null}>} 会话 ID（从 X-Conversation-Id 响应头获取）
 */
export async function streamSSE({
  url,
  body,
  headers = {},
  onChunk,
  onDone,
  signal,
  connectTimeoutMs = 30000,
}) {
  const token = getAuthToken()
  const finalHeaders = { 'Content-Type': 'application/json', ...headers }
  if (token) finalHeaders['Authorization'] = `Bearer ${token}`

  // 连接超时控制：在收到首字节前若超时则中止请求，避免无限挂起
  // 与外部 signal 合并：任一触发都会中止 fetch
  const timeoutController = new AbortController()
  let timeoutId = null
  let firstByteReceived = false

  const onAbort = () => {
    if (timeoutId) {
      clearTimeout(timeoutId)
      timeoutId = null
    }
  }
  if (signal) signal.addEventListener('abort', onAbort, { once: true })

  if (connectTimeoutMs > 0) {
    timeoutId = setTimeout(() => {
      if (!firstByteReceived) {
        timeoutController.abort()
      }
    }, connectTimeoutMs)
  }

  // 合并外部 signal 与超时 signal
  const mergedSignal = signal
    ? abortAnySignal([signal, timeoutController.signal])
    : timeoutController.signal

  let response
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: finalHeaders,
      body: JSON.stringify(body),
      signal: mergedSignal,
    })
  } catch (e) {
    onAbort()
    // 区分超时中止与用户手动中止，给出更友好的错误信息
    if (timeoutController.signal.aborted && !(signal && signal.aborted)) {
      const err = new Error('连接超时，请检查网络后重试')
      err.name = 'TimeoutError'
      throw err
    }
    throw e
  }

  // 后端通过 X-Conversation-Id 响应头返回会话 ID，供后续多轮对话复用
  const conversationId = response.headers.get('X-Conversation-Id')

  // 非 2xx 响应：读取错误信息后抛出，让调用方 catch 处理
  if (!response.ok) {
    onAbort()
    let errMsg = `请求失败 (${response.status})`
    try {
      const errBody = await response.json()
      errMsg = errBody.message || errBody.detail || errMsg
    } catch (_e) { /* 响应体非 JSON，使用默认错误信息 */ }
    throw new Error(errMsg)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      // 收到首字节后清除连接超时，后续流式传输不再受超时限制
      if (!firstByteReceived) {
        firstByteReceived = true
        if (timeoutId) {
          clearTimeout(timeoutId)
          timeoutId = null
        }
      }

      buffer += decoder.decode(value, { stream: true })
      // 按换行分割，最后一段可能不完整，留到下次拼接
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        // SSE 注释行（以冒号开头）和空行直接跳过
        if (!line || line.startsWith(':')) continue
        if (!line.startsWith('data: ')) continue
        const data = line.slice(6)

        if (data === '[DONE]') {
          if (onDone) onDone()
          return { conversationId }
        }

        // 文本 chunk：后端用 JSON 编码（防止换行破坏 SSE 协议）
        let text
        try {
          text = JSON.parse(data)
        } catch (_e) {
          text = data
        }
        if (onChunk) onChunk(text)
      }
    }
  } finally {
    // 确保 reader 被释放，避免流资源泄漏
    if (timeoutId) clearTimeout(timeoutId)
    try {
      reader.releaseLock()
    } catch (_e) { /* reader 已锁定或已释放，忽略 */ }
  }

  // 流正常结束但未收到 [DONE]：兜底触发 onDone，保证 UI 状态收敛
  if (onDone) onDone()
  return { conversationId }
}

/**
 * 将多个 AbortSignal 合并为一个：任一 abort 则合并信号 abort。
 * 兼容不支持 AbortSignal.any 的环境（如旧版浏览器）。
 */
function abortAnySignal(signals) {
  if (typeof AbortSignal.any === 'function') {
    return AbortSignal.any(signals)
  }
  const controller = new AbortController()
  for (const s of signals) {
    if (s.aborted) {
      controller.abort()
      break
    }
    s.addEventListener('abort', () => controller.abort(), { once: true })
  }
  return controller.signal
}

export default streamSSE
