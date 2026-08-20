"""AI 对话相关 Pydantic Schema —— 对话请求/推荐请求/消息/会话响应"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class AiChatRequest(BaseModel):
    """AI 对话请求 —— conversation_id 为空时自动创建新会话"""
    message: str = Field(..., min_length=1)
    conversation_id: Optional[int] = None


class RewindEditRequest(BaseModel):
    """重答编辑请求 —— 编辑指定用户消息，并删除其后所有消息（不保留旧分支）"""
    message_id: int = Field(..., ge=1)
    new_content: str = Field(..., min_length=1)


class AiRecommendRequest(BaseModel):
    """智能推荐请求 —— 支持自然语言查询 + 预算 + 餐次筛选"""
    query: str = Field(..., min_length=1)
    budget: Optional[float] = None
    meal_type: Optional[str] = None


class AiMessageOut(BaseModel):
    id: int
    role: str
    content: str
    created_at: datetime

    class Config:
        from_attributes = True


class AiConversationOut(BaseModel):
    """AI 会话列表项 —— 含首条用户提问与最后一条 AI 回复，供卡片摘要展示"""
    id: int
    title: Optional[str] = None
    user_message: Optional[str] = None
    ai_reply: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AiConversationDetailOut(BaseModel):
    """AI 会话详情 —— 含所有历史消息"""
    id: int
    title: Optional[str] = None
    messages: List[AiMessageOut] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True