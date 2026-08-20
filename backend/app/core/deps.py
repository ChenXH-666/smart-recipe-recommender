"""
依赖注入层 —— FastAPI 用户认证与权限检查

============================================================================
                    三层权限依赖注入设计（面向答辩）
============================================================================

本系统实现了三层权限依赖注入，通过 FastAPI 的 Depends() 机制实现：

  【第一层】get_current_user  → 必须登录（强制认证）
    使用 HTTPBearer(auto_error=True)：无 Authorization header → 403
    token 无效/过期/用户不存在 → 401 Unauthorized。

  【第二层】get_admin_user    → 必须管理员（强制认证 + 角色检查）
    先调用 get_current_user 验证登录状态，
    再检查 role == "admin"。非管理员 → 403 Forbidden。

  【第三层】get_optional_user → 可选登录（可选认证）
    使用独立的 HTTPBearer(auto_error=False) 实例：
    - 无 Authorization header → credentials=None → 返回 None
    - 有 token 但无效/过期 → 返回 None（而非抛异常）
    - token 有效且用户存在 → 返回 User 对象
    用于菜谱详情等场景：登录用户可看到个性化内容，未登录用户也能浏览。

关键注意：
  get_optional_user 与 get_current_user 必须使用不同的 HTTPBearer 实例！
  共享 auto_error=True 的实例会导致未登录用户访问"可选认证"接口时被强制返回 403。
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.security import decode_access_token
from app.models import User

# 强制认证用：无 token → FastAPI 直接返回 401
security_scheme = HTTPBearer(auto_error=True)

# 可选认证用：无 token → credentials 为 None，函数体自行处理
optional_security_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    强制认证 —— 从 JWT Bearer Token 解析当前登录用户。

    验证流程：
      1. 从 Authorization header 提取 token（HTTPBearer 已确保 header 存在且格式正确）
      2. decode_access_token() 验证 JWT 签名和过期时间
      3. 从 payload.sub 获取 user_id
      4. 在数据库中查询用户，验证 is_active=1
      5. 返回完整 User 对象
    """
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="未提供认证令牌")
    token = credentials.credentials
    payload = decode_access_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的认证令牌")

    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="令牌格式不正确")

    user = db.query(User).filter(User.id == int(user_id), User.is_active == 1).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用")

    return user


def get_admin_user(current_user: User = Depends(get_current_user)) -> User:
    """
    管理员权限校验 —— 在 get_current_user 基础上叠加角色检查。
    非管理员用户即使已登录也会收到 403 Forbidden。
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return current_user


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(optional_security_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """
    可选认证 —— 登录了返回 User 对象，未登录/认证失败返回 None。

    使用独立的 HTTPBearer(auto_error=False) 实例：
    - 未提供 token（credentials=None）→ 返回 None
    - token 无效/过期/用户不存在 → 捕获 HTTPException → 返回 None
    - 认证成功 → 返回 User 对象
    """
    if credentials is None:
        return None
    try:
        return get_current_user(credentials, db)
    except HTTPException:
        return None
