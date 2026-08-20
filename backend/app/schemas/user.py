"""用户相关 Pydantic Schema —— 注册/登录/信息更新/密码修改"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime


# ---- 注册/登录 ----
class UserRegister(BaseModel):
    username: str = Field(..., min_length=2, max_length=50)
    nickname: Optional[str] = Field(None, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=100)


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserInfo"


# ---- 用户信息 ----
class UserInfo(BaseModel):
    id: int
    username: str
    nickname: Optional[str] = None
    email: str
    avatar_url: Optional[str] = None
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    nickname: Optional[str] = Field(None, max_length=50)
    email: Optional[EmailStr] = None
    avatar_url: Optional[str] = None


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8, max_length=100)


class UserPreferences(BaseModel):
    """用户个性化偏好：cuisines 标签 / diet_tags 忌口过敏 / free_text 自由文本描述"""
    cuisines: List[str] = []
    diet_tags: List[str] = []
    free_text: str = ""