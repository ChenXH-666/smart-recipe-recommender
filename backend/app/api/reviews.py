"""菜谱点评

安全设计：
  - 列表使用 joinedload 预加载 user，避免 N+1 查询
  - 防止重复点评（单用户对单菜谱只能点评一次，未删除的）
  - 仅允许对已审核通过的菜谱点评
  - 软删除策略，保护数据完整性
  - 删除点评时使用原子 UPDATE 维护菜谱统计（如果未来扩展评分均分）
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import update

from app.database import get_db
from app.models import RecipeReview, Recipe
from app.schemas.interaction import ReviewCreate, ReviewOut
from app.schemas.common import PaginatedResponse, SuccessResponse
from app.core.deps import get_current_user

router = APIRouter()


def _enrich_review(r: RecipeReview) -> ReviewOut:
    """将 ORM 对象转为 API 响应，使用预加载的 user 关系"""
    item = ReviewOut.model_validate(r)
    if r.user:
        item.username = r.user.nickname or r.user.username
        item.user_avatar_url = r.user.avatar_url
    return item


@router.post("/recipes/{recipe_id}", response_model=ReviewOut)
def create_review(
    recipe_id: int,
    data: ReviewCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """创建点评

    安全：
      - 菜谱必须存在、未删除、已审核通过
      - 同一用户对同一菜谱只能点评一次（防重复）
      - rating 必须在 1-5 之间（由 Pydantic 校验）
    """
    recipe = db.query(Recipe).filter(
        Recipe.id == recipe_id,
        Recipe.is_deleted == 0,
        Recipe.status == "approved",
    ).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="菜谱不存在或未通过审核")

    # 防重复：同一用户对同一菜谱只能有一条未删除的点评
    existing = db.query(RecipeReview).filter(
        RecipeReview.recipe_id == recipe_id,
        RecipeReview.user_id == current_user.id,
        RecipeReview.is_deleted == 0,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="您已点评过该菜谱，无法重复点评")

    # 至少提供评分或评论内容之一
    if data.rating is None and not data.content:
        raise HTTPException(status_code=400, detail="评分和评论内容不能同时为空")

    review = RecipeReview(
        recipe_id=recipe_id,
        user_id=current_user.id,
        rating=data.rating,
        content=data.content,
    )
    db.add(review)
    db.commit()
    db.refresh(review)

    result = ReviewOut.model_validate(review)
    result.username = current_user.nickname or current_user.username
    result.user_avatar_url = current_user.avatar_url
    return result


@router.get("/recipes/{recipe_id}", response_model=PaginatedResponse[ReviewOut])
def get_reviews(
    recipe_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """获取菜谱的点评列表

    性能：joinedload 预加载 user，避免循环中的 N+1 查询
    """
    # 校验菜谱存在（即便已删除也可以看历史点评，但需提供 recipe_id 有效）
    recipe_exists = db.query(Recipe.id).filter(Recipe.id == recipe_id).first()
    if not recipe_exists:
        raise HTTPException(status_code=404, detail="菜谱不存在")

    query = db.query(RecipeReview).options(
        joinedload(RecipeReview.user)
    ).filter(
        RecipeReview.recipe_id == recipe_id,
        RecipeReview.is_deleted == 0,
    )
    total = query.count()
    reviews = (
        query.order_by(RecipeReview.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [_enrich_review(r) for r in reviews]
    return PaginatedResponse(total=total, page=page, page_size=page_size, items=items)


@router.delete("/{review_id}", response_model=SuccessResponse)
def delete_review(
    review_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """删除点评（软删除）—— 仅作者可删"""
    review = db.query(RecipeReview).filter(
        RecipeReview.id == review_id,
        RecipeReview.user_id == current_user.id,
        RecipeReview.is_deleted == 0,
    ).first()
    if not review:
        raise HTTPException(status_code=404, detail="点评不存在或无权操作")

    review.is_deleted = 1
    db.commit()
    return SuccessResponse(message="删除成功")
