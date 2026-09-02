"""菜谱相关 Pydantic Schema —— 定义菜谱数据的请求/响应结构

本模块涵盖：
  - 标签信息（TagInfo）
  - 食材信息（IngredientInfo, RecipeIngredientOut, RecipeIngredientCreate）
  - 步骤信息（StepInfo, StepCreate）
  - 菜谱 CRUD（RecipeCreate, RecipeUpdate）
  - 菜谱列表/详情响应（RecipeListItem, RecipeDetail）
  - 搜索参数（RecipeSearchParams）
"""

from pydantic import BaseModel, Field, model_validator, field_validator
from typing import Optional, List
from datetime import datetime
from decimal import Decimal


# ---- 标签 ----
class TagInfo(BaseModel):
    id: int
    name: str
    type: Optional[str] = None

    class Config:
        from_attributes = True


# ---- 食材 ----
class IngredientInfo(BaseModel):
    id: int
    name: str
    category: Optional[str] = None

    class Config:
        from_attributes = True


class RecipeIngredientOut(BaseModel):
    id: int
    ingredient: IngredientInfo
    quantity: Optional[str] = None
    note: Optional[str] = None
    sort_order: int

    class Config:
        from_attributes = True


# ---- 步骤 ----
class StepInfo(BaseModel):
    step_number: int
    instruction: str
    # image_url: Optional[str] = None  # 步骤图片功能，暂不启用
    duration: Optional[int] = None

    class Config:
        from_attributes = True


class StepCreate(BaseModel):
    step_number: int
    instruction: str = Field(..., min_length=1, max_length=2000)
    # image_url: Optional[str] = None  # 步骤图片功能，暂不启用
    duration: Optional[int] = None


# ---- 菜谱 CRUD ----
class RecipeCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    cover_image_url: Optional[str] = Field(None, max_length=500)
    difficulty: Optional[str] = None
    cooking_time: Optional[int] = Field(None, ge=1, le=1440)
    servings: Optional[int] = Field(None, ge=1, le=100)
    estimated_cost: Optional[Decimal] = Field(None, ge=0, le=100000, description="预估成本（元）")
    tag_ids: List[int] = []
    ingredients: List["RecipeIngredientCreate"] = []
    steps: List[StepCreate] = []
    # 可选：draft=存草稿（允许不完整）。为空则按后端默认（管理员 approved / 普通用户 pending）
    status: Optional[str] = None

    @field_validator("difficulty", mode="before")
    @classmethod
    def _normalize_difficulty(cls, v):
        """difficulty 是 MySQL ENUM('easy','medium','hard') 列，空字符串会被数据库拒绝。
        前端表单未选择难度时会提交 ""，这里统一转换为 None。"""
        if v in ("", None):
            return None
        return v

    @model_validator(mode="after")
    def _validate_required_fields(self):
        """菜谱必须至少包含一条食材和一条步骤，否则视为不完整（草稿除外）"""
        if getattr(self, "status", None) == "draft":
            return self
        if not self.ingredients:
            raise ValueError("至少需要添加一条食材")
        if not self.steps:
            raise ValueError("至少需要添加一条烹饪步骤")
        # 步骤 instruction 不能为空
        for i, s in enumerate(self.steps, 1):
            if not s.instruction or not s.instruction.strip():
                raise ValueError(f"第 {i} 步的描述不能为空")
        # 食材 ingredient_id 必须存在
        for i, ing in enumerate(self.ingredients, 1):
            if not ing.ingredient_id:
                raise ValueError(f"第 {i} 条食材未选择具体食材")
        return self


class RecipeIngredientCreate(BaseModel):
    ingredient_id: int
    quantity: Optional[str] = None
    note: Optional[str] = None
    sort_order: int = 0


class RecipeUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    cover_image_url: Optional[str] = Field(None, max_length=500)
    difficulty: Optional[str] = None
    cooking_time: Optional[int] = Field(None, ge=1, le=1440)
    servings: Optional[int] = Field(None, ge=1, le=100)
    estimated_cost: Optional[Decimal] = Field(None, ge=0, le=100000, description="预估成本（元）")
    tag_ids: Optional[List[int]] = None
    ingredients: Optional[List["RecipeIngredientCreate"]] = None
    steps: Optional[List[StepCreate]] = None
    # 可选：draft=存为草稿（跳过完整性校验）
    status: Optional[str] = None

    @field_validator("difficulty", mode="before")
    @classmethod
    def _normalize_difficulty(cls, v):
        """difficulty 是 MySQL ENUM('easy','medium','hard') 列，空字符串会被数据库拒绝。
        前端表单未选择难度时会提交 ""，这里统一转换为 None。"""
        if v in ("", None):
            return None
        return v

    @model_validator(mode="after")
    def _validate_update_fields(self):
        """更新时如果提供了 ingredients/steps，则不能为空列表（防止清空所有食材/步骤）；草稿除外"""
        if getattr(self, "status", None) == "draft":
            return self
        if self.ingredients is not None and len(self.ingredients) == 0:
            raise ValueError("食材不能为空，至少需要保留一条食材")
        if self.steps is not None and len(self.steps) == 0:
            raise ValueError("步骤不能为空，至少需要保留一条步骤")
        if self.steps is not None:
            for i, s in enumerate(self.steps, 1):
                if not s.instruction or not s.instruction.strip():
                    raise ValueError(f"第 {i} 步的描述不能为空")
        if self.ingredients is not None:
            for i, ing in enumerate(self.ingredients, 1):
                if not ing.ingredient_id:
                    raise ValueError(f"第 {i} 条食材未选择具体食材")
        return self


class RecipeListItem(BaseModel):
    """菜谱列表项（精简）—— 仅包含列表页需要的字段，不含食材/步骤等大字段"""
    id: int
    title: str
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    difficulty: Optional[str] = None
    cooking_time: Optional[int] = None
    estimated_cost: Optional[Decimal] = None
    view_count: int
    favorite_count: int
    status: Optional[str] = None
    tags: List[TagInfo] = []
    # 审核意见（驳回原因）—— 驳回状态下作者可见；非作者仅能访问 approved 状态，无泄露风险
    review_comment: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class RecipeDetail(BaseModel):
    """菜谱详情（完整）—— 含标签、食材、步骤、作者等全部信息"""
    id: int
    title: str
    description: Optional[str] = None
    cover_image_url: Optional[str] = None
    difficulty: Optional[str] = None
    cooking_time: Optional[int] = None
    servings: Optional[int] = None
    estimated_cost: Optional[Decimal] = None
    author_id: Optional[int] = None
    author_nickname: Optional[str] = None
    author_avatar_url: Optional[str] = None
    status: str
    view_count: int
    favorite_count: int
    # 审核意见（驳回原因）—— pending/rejected 仅作者/管理员可访问详情，无泄露风险
    review_comment: Optional[str] = None
    tags: List[TagInfo] = []
    ingredients: List[RecipeIngredientOut] = []
    steps: List[StepInfo] = []
    # 估算营养（整份）：{kcal, protein, fat, carbs}；无食材营养数据时为 None
    nutrition: Optional[dict] = None
    # 命中当前用户忌口的食材名（未登录或无忌口为空列表）
    diet_warnings: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class RecipeSearchParams(BaseModel):
    keyword: Optional[str] = None
    difficulty: Optional[str] = None
    tag_ids: Optional[str] = None  # 逗号分隔
    max_cost: Optional[float] = None
    status: str = "approved"
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)