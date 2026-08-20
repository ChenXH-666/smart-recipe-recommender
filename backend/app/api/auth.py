"""认证：注册、登录

安全设计：
  - 密码强度校验：最少 8 位，必须包含字母和数字（防弱密码）
  - 用户名/邮箱唯一性校验（依赖数据库 UNIQUE 约束 + 业务层预检）
  - 登录失败统一返回"用户名或密码错误"，避免用户名枚举攻击
  - bcrypt 哈希存储（core/security.py），禁止明文
  - JWT 24 小时有效期，HS256 签名
  - 限流防爆破：登录 10次/分钟/IP，注册 5次/分钟/IP（core/rate_limit.py）
"""

import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas.user import UserRegister, UserLogin, TokenResponse, UserInfo
from app.schemas.common import SuccessResponse
from app.core.security import hash_password, verify_password, create_access_token
from app.core.deps import get_current_user
from app.core.rate_limit import rate_limit

router = APIRouter()

# 用于时序攻击防护的假密码哈希 —— 用户不存在时执行一次假验证，避免时间差异泄露用户存在性。
# 使用 hash_password 生成合法格式的 bcrypt 哈希，确保 verify_password 正常返回 False。
_DUMMY_PASSWORD_HASH = hash_password("timing-attack-dummy-password")


def _validate_password_strength(password: str) -> None:
    """
    密码强度校验 —— PRD 3.2 节要求"对密码强度做基本校验"

    规则：
      - 长度 ≥ 8
      - 必须包含至少一个字母
      - 必须包含至少一个数字
    """
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="密码长度至少 8 位")
    if not re.search(r"[A-Za-z]", password):
        raise HTTPException(status_code=400, detail="密码必须包含至少一个字母")
    if not re.search(r"\d", password):
        raise HTTPException(status_code=400, detail="密码必须包含至少一个数字")


def _validate_username(username: str) -> None:
    """用户名格式校验：仅允许字母、数字、下划线、中文，2-50 字符"""
    if not username or len(username) < 2 or len(username) > 50:
        raise HTTPException(status_code=400, detail="用户名长度需为 2-50 字符")
    # 允许中文、字母、数字、下划线
    if not re.match(r"^[\u4e00-\u9fa5A-Za-z0-9_]+$", username):
        raise HTTPException(status_code=400, detail="用户名仅允许中文、字母、数字、下划线")


@router.post("/register", response_model=SuccessResponse,
             dependencies=[Depends(rate_limit(5, 60, "register"))])
def register(data: UserRegister, db: Session = Depends(get_db)):
    """用户注册

    安全：
      - 用户名格式校验（防注入字符）
      - 密码强度校验（防弱密码）
      - 用户名/邮箱唯一性校验
      - 密码 bcrypt 哈希存储
    """
    # 用户名校验
    _validate_username(data.username)
    # 密码强度校验
    _validate_password_strength(data.password)

    # 检查用户名是否已存在
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(status_code=400, detail="邮箱已被注册")

    user = User(
        username=data.username,
        nickname=data.nickname,
        email=data.email,
        password_hash=hash_password(data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return SuccessResponse(message="注册成功", id=user.id)


@router.post("/login", response_model=TokenResponse,
             dependencies=[Depends(rate_limit(10, 60, "login"))])
def login(data: UserLogin, db: Session = Depends(get_db)):
    """用户登录

    安全：
      - 统一返回"用户名或密码错误"，避免用户名枚举
      - 禁用账户登录拒绝
      - 成功后签发 JWT
      - 支持用户名或邮箱登录（PRD 6.2.2：用户名/邮箱 + 密码）
    """
    # PRD 6.2.2 要求登录支持用户名或邮箱
    # 含 @ 视为邮箱登录，否则按用户名查询
    if "@" in data.username:
        user = db.query(User).filter(User.email == data.username).first()
    else:
        user = db.query(User).filter(User.username == data.username).first()
    # 始终执行密码验证（即使用户不存在），避免时序攻击泄露用户存在性
    if user is None:
        # 用户不存在时执行一次假验证，避免时间差异泄露用户存在性
        verify_password(data.password, _DUMMY_PASSWORD_HASH)
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not user.is_active:
        raise HTTPException(status_code=401, detail="账号已被禁用")

    token = create_access_token(data={"sub": str(user.id)})
    return TokenResponse(
        access_token=token,
        user=UserInfo.model_validate(user),
    )


@router.get("/me", response_model=UserInfo)
def get_me(current_user: User = Depends(get_current_user)):
    """获取当前用户信息"""
    return UserInfo.model_validate(current_user)
