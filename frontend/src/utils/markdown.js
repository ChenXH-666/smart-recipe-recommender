/**
 * Markdown 安全渲染工具
 * ========================
 * 统一封装 marked + DOMPurify，用于渲染 AI 回复、烹饪心得等富文本内容。
 *
 * 安全设计（PRD 3.2 要求）：
 *   - marked v12 已移除内置 sanitizer，单独使用 marked.parse 会有 XSS 风险
 *     （如 <img onerror=...>、<script> 等恶意标签会原样输出）。
 *   - 因此在 marked.parse 之后追加 DOMPurify.sanitize，剥离所有危险标签与属性。
 *   - 解析失败时退化为 HTML 转义文本，确保永不抛出异常。
 *
 * 使用方式：在 v-html 处调用 renderMarkdown(text)，例如：
 *   <div class="markdown-body" v-html="renderMarkdown(content)"></div>
 */
import { marked } from 'marked'
import DOMPurify from 'dompurify'

// marked 全局配置：仅启用有效选项，避免 marked v12 已废弃选项的告警
marked.setOptions({
  breaks: true, // 换行符转 <br>
  gfm: true, // 启用 GitHub Flavored Markdown（表格、删除线等）
})

/**
 * 将 Markdown 文本渲染为经过净化的安全 HTML。
 * @param {string} text 原始 Markdown 文本
 * @returns {string} 净化后的 HTML 字符串（空输入返回空串）
 */
export function renderMarkdown(text) {
  if (!text) return ''
  try {
    const html = marked.parse(text)
    // DOMPurify 剥离 <script>、on* 事件属性、javascript: 协议等危险内容
    return DOMPurify.sanitize(html, {
      ALLOWED_TAGS: [
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'p', 'br', 'hr', 'span', 'div',
        'strong', 'em', 'del', 's', 'sub', 'sup',
        'ul', 'ol', 'li',
        'blockquote', 'code', 'pre',
        'a', 'img', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
      ],
      ALLOWED_ATTR: ['href', 'src', 'alt', 'title', 'class'],
      ALLOW_DATA_ATTR: false,
    })
  } catch {
    // 兜底：marked 解析失败时退化为转义文本，避免抛出异常中断渲染
    return '<p>' + String(text).replace(/[<>&]/g, (ch) => ({
      '<': '&lt;', '>': '&gt;', '&': '&amp;',
    }[ch])) + '</p>'
  }
}

export default renderMarkdown
