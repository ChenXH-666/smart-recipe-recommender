"""后台管理相关 Pydantic Schema —— 审核操作、管理员菜谱/套餐列表"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field


class AuditAction(BaseModel):
    """审核操作 —— action 只能是 approve 或 reject"""
    action: str = Field(..., pattern="^(approve|reject)$")
    comment: Optional[str] = Field(None, max_length=500)


class AdminRecipeListOut(BaseModel):
    """管理员菜谱列表 —— 比普通列表多出 author_name/status 及审核追踪字段"""
    id: int
    title: str
    author_id: Optional[int] = None
    author_name: str = ""
    status: str
    estimated_cost: Optional[float] = None
    view_count: int
    favorite_count: int
    created_at: datetime
    updated_at: datetime
    review_comment: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    reviewer_name: str = ""

    class Config:
        from_attributes = True


class AdminMealPlanListOut(BaseModel):
    """管理员套餐列表 —— 比普通列表多出 creator_name/review_comment 及审核追踪字段"""
    id: int
    title: str
    user_id: int
    creator_name: str = ""
    status: str
    review_comment: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    reviewer_name: str = ""
    created_at: datetime

    class Config:
        from_attributes = True