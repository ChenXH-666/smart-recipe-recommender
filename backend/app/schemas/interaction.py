"""互动相关 Pydantic Schema —— 点评/心得/套餐的请求/响应结构

本模块涵盖三个互动功能的数据模型：
  - 菜谱点评（ReviewCreate / ReviewOut）
  - 烹饪心得（CookingNoteCreate / CookingNoteUpdate / CookingNoteOut）
  - 套餐规划（MealPlanCreate / MealPlanItemCreate / MealPlanListOut / MealPlanDetailOut）
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# ---- 菜谱点评 ----
class ReviewCreate(BaseModel):
    rating: Optional[int] = Field(None, ge=1, le=5)
    content: Optional[str] = None


class ReviewOut(BaseModel):
    id: int
    recipe_id: int
    user_id: int
    username: str = ""
    user_avatar_url: Optional[str] = None
    rating: Optional[int] = None
    content: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---- 烹饪心得 ----
class CookingNoteCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1, max_length=10000)
    related_recipe_id: Optional[int] = None
    images: Optional[List[str]] = None
    is_public: bool = True


class CookingNoteUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = Field(None, min_length=1, max_length=10000)
    related_recipe_id: Optional[int] = None
    images: Optional[List[str]] = None
    is_public: Optional[bool] = None


class CookingNoteOut(BaseModel):
    id: int
    user_id: int
    username: str = ""
    author_avatar_url: Optional[str] = None
    title: str
    content: str
    related_recipe_id: Optional[int] = None
    related_recipe_title: Optional[str] = None
    images: Optional[List[str]] = None
    is_public: bool
    view_count: int
    comment_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class CookingNoteCommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000)


class CookingNoteCommentOut(BaseModel):
    id: int
    note_id: int
    user_id: int
    username: str = ""
    user_avatar_url: Optional[str] = None
    content: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ---- 套餐 ----
class MealPlanItemCreate(BaseModel):
    recipe_id: int
    sort_order: int = 0
    note: Optional[str] = Field(None, max_length=255)


class MealPlanCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    cover_image_url: Optional[str] = Field(None, max_length=500)
    is_public: bool = True
    items: List["MealPlanItemCreate"] = Field(default_factory=list)
    # 可选：draft=存草稿（允许空菜品）。为空则按后端默认（管理员 approved / 普通用户 pending）
    status: Optional[str] = None


class MealPlanItemOut(BaseModel):
    id: int
    recipe_id: int
    recipe_title: str = ""
    sort_order: int
    note: Optional[str] = None

    class Config:
        from_attributes = True


class MealPlanListOut(BaseModel):
    id: int
    user_id: int
    title: str
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    is_public: bool
    status: str
    favorite_count: int
    view_count: int
    author_nickname: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class MealPlanDetailOut(BaseModel):
    id: int
    user_id: int
    title: str
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    is_public: bool
    status: str
    favorite_count: int
    view_count: int
    author_nickname: Optional[str] = None
    items: List[MealPlanItemOut] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True