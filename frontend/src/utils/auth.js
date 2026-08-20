/**
 * 认证工具函数
 * ========================
 * 统一封装 JWT token 的本地存储读取与格式校验，避免在多个组件中重复实现。
 *
 * token 存储位置：localStorage.token（由 stores/user.js 在登录成功时写入）
 * 校验规则：JWT 由 3 段以 '.' 分隔的非空字符串组成（header.payload.signature）
 */

/**
 * 校验 token 是否为合法的 JWT 格式（3 段以 . 分隔的非空字符串）。
 * 注意：仅做格式校验，不验证签名与过期时间（由后端完成）。
 * @param {string} token
 * @returns {boolean}
 */
export function isValidJwt(token) {
  if (!token || typeof token !== 'string') return false
  const parts = token.split('.')
  return parts.length === 3 && parts.every((p) => p.length > 0)
}

/**
 * 从 localStorage 读取有效 token；若不存在或格式非法则返回空串并清理脏数据。
 * @returns {string}
 */
export function getAuthToken() {
  const token = localStorage.getItem('token')
  if (!isValidJwt(token)) {
    if (token) localStorage.removeItem('token')
    return ''
  }
  return token
}

export default { isValidJwt, getAuthToken }
