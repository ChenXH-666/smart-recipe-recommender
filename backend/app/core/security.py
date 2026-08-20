"""
认证安全模块 —— 密码哈希、JWT 令牌签发与验证

============================================================================
                      安全设计说明（面向答辩）
============================================================================

【密码处理 —— bcrypt】
  使用 passlib 的 bcrypt 算法进行密码哈希。
  bcrypt 是业界标准的密码哈希算法，内置盐值（salt）和自适应成本因子。

  ⚠️ bcrypt 72 字节截断问题：
  bcrypt 的最大输入长度为 72 字节（UTF-8 编码后）。
  对于超长密码（如某些密码管理器生成的 64+ 字符随机密码），
  超出 72 字节的部分会被截断。因此在 hash_password() 和 verify_password()
  中，我们显式截断到 72 字节以保证哈希和验证的一致性。

【JWT 令牌流程】
  1. 用户登录 → 服务端验证密码 → create_access_token() 生成 JWT
     - payload 中包含 sub(user_id) 和 exp(过期时间)
     - 使用 HS256 算法 + JWT_SECRET_KEY 签名
  2. 客户端携带 Bearer Token 请求 → deps.py 中的 get_current_user() 验证
     - decode_access_token() 解码并验证签名和过期时间
     - 从 claims 中提取 user_id → 查数据库确认用户存在且未禁用
  3. JWT 有效期默认 24 小时，适合长时间登录体验
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from passlib.context import CryptContext
from jose import jwt, JWTError

from app.config import get_settings

settings = get_settings()

# 密码哈希上下文 —— bcrypt 算法，schemes 列表支持算法平滑升级
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """
    对密码进行 bcrypt 哈希。

    步骤：
      1. UTF-8 编码原始密码
      2. 截断到 72 字节（bcrypt 输入上限，超出部分会被算法忽略）
      3. 调用 passlib 的 hash() 方法生成带 salt 的哈希值
    """
    password_bytes = password.encode("utf-8")
    truncated_password = password_bytes[:72].decode("utf-8", errors="ignore")
    return pwd_context.hash(truncated_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证明文密码是否与哈希值匹配。
    同样进行 72 字节截断以保证与 hash_password 的一致性。
    """
    password_bytes = plain_password.encode("utf-8")
    truncated_password = password_bytes[:72].decode("utf-8", errors="ignore")
    return pwd_context.verify(truncated_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    创建 JWT 访问令牌。

    参数：
      data: 要编码的数据字典，必须包含 "sub"（subject，即 user_id）
      expires_delta: 可选的自定义过期时间，默认使用配置的 24 小时

    返回：签名的 JWT 字符串
    """
    to_encode = data.copy()
    # 防御性转换：python-jose 3.5.0 要求 payload 中的 "sub" 必须是字符串
    if "sub" in to_encode and not isinstance(to_encode["sub"], str):
        to_encode["sub"] = str(to_encode["sub"])
    # datetime.utcnow() 在 Python 3.12 起已废弃，改用时区感知的 now(timezone.utc)
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    """
    解码并验证 JWT 令牌。

    返回值：
      成功 → 包含 sub、exp 等字段的字典
      失败（过期、签名错误等）→ None
    """
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        return None