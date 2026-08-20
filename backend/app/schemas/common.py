"""通用 Pydantic Schema —— 分页响应、错误响应、成功响应等可复用结构"""

from pydantic import BaseModel, Field
from typing import TypeVar, Generic, Optional
from datetime import datetime

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """
    通用分页响应 —— 所有列表接口统一使用此结构。
    通过 Generic[T] 支持任意 item 类型，例如：
      PaginatedResponse[RecipeListItem]
      PaginatedResponse[MealPlanListOut]
    """
    total: int
    page: int
    page_size: int
    items: list[T]


class ErrorResponse(BaseModel):
    """通用错误响应"""
    detail: str


class SuccessResponse(BaseModel):
    """通用成功响应 —— 带可选 id 字段，创建/更新操作可返回新创建记录的 ID"""
    message: str = "操作成功"
    id: Optional[int] = None