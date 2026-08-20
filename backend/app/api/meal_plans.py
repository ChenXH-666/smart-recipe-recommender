"""套餐接口 —— 套餐 CRUD，支持公开/私有、审核流程

安全设计：
  - 详情接口权限：approved+public 所有人可见；pending/rejected 仅作者/管理员；private 仅作者
  - 套餐内 recipe_id 校验存在性与已审核状态
  - 重复添加同一 recipe_id 时捕获 IntegrityError 返回友好错误
  - 浏览数+1 使用原子 UPDATE
  - 自动记录浏览历史（登录用户）
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from datetime import datetime

from app.database import get_db
from app.models import MealPlan, MealPlanItem, Recipe, RecipeIngredient, UserBrowseHistory
from app.schemas.interaction import (
    MealPlanCreate, MealPlanListOut, MealPlanDetailOut, MealPlanItemOut,
)
from app.schemas.common import PaginatedResponse, SuccessResponse
from app.core.deps import get_current_user, get_optional_user

router = APIRouter()


def _record_browse_history(db: Session, user_id: int | None, meal_plan_id: int):
    """自动记录套餐浏览历史（登录用户，去重避免表膨胀）"""
    if user_id is None:
        return
    now = datetime.now()
    existing = db.query(UserBrowseHistory).filter(
        UserBrowseHistory.user_id == user_id,
        UserBrowseHistory.meal_plan_id == meal_plan_id,
    ).first()
    if existing:
        existing.viewed_at = now
    else:
        db.add(UserBrowseHistory(
            user_id=user_id, meal_plan_id=meal_plan_id, viewed_at=now
        ))


@router.get("", response_model=PaginatedResponse[MealPlanListOut])
def list_meal_plans(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    mine: int = Query(0, description="只看我创建的（含草稿/待审核/已驳回）"),
    status: str = Query(None, description="仅 mine 时有效：按状态筛选"),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    """套餐列表（公开广场 / 我的套餐）

    安全：公开列表仅返回 approved 且 is_public=1 的套餐。
         mine=1 时仅返回当前用户创建的套餐（可见草稿/待审/驳回等全部状态）。
    此前的 is_public 查询参数允许无认证用户枚举他人的私有套餐，
    已移除 —— 私有/待审核套餐只能通过详情接口（作者/管理员）或后台访问。
    """
    if mine:
        if current_user is None:
            return PaginatedResponse(total=0, page=page, page_size=page_size, items=[])
        query = db.query(MealPlan).options(joinedload(MealPlan.creator)).filter(
            MealPlan.is_deleted == 0,
            MealPlan.user_id == current_user.id,
        )
        if status:
            if status not in ("approved", "pending", "rejected", "draft"):
                raise HTTPException(status_code=400, detail="status 值不合法")
            query = query.filter(MealPlan.status == status)
    else:
        query = db.query(MealPlan).options(joinedload(MealPlan.creator)).filter(
            MealPlan.is_deleted == 0,
            MealPlan.status == "approved",
            MealPlan.is_public == 1,
        )

    total = query.count()
    plans = query.order_by(MealPlan.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedResponse(
        total=total, page=page, page_size=page_size,
        items=[MealPlanListOut.model_validate(p) for p in plans],
    )


@router.get("/{plan_id}/shopping-list")
def get_shopping_list(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    """生成套餐购物清单：把套餐内所有菜谱的食材合并、去重、汇总用量，并给出总价。

    权限同套餐详情（公开已审核的套餐所有人可见）。
    """
    plan = (
        db.query(MealPlan)
        .options(
            joinedload(MealPlan.creator),
            joinedload(MealPlan.items).joinedload(MealPlanItem.recipe)
                .joinedload(Recipe.ingredients).joinedload(RecipeIngredient.ingredient),
        )
        .filter(MealPlan.id == plan_id, MealPlan.is_deleted == 0)
        .first()
    )
    if not plan:
        raise HTTPException(status_code=404, detail="套餐不存在")

    is_author = current_user is not None and plan.user_id == current_user.id
    is_admin = current_user is not None and current_user.role == "admin"
    if not is_author and not is_admin:
        if plan.status != "approved" or not plan.is_public:
            raise HTTPException(status_code=404, detail="套餐不存在")

    agg: dict = {}
    total_cost = 0.0
    for item in plan.items:
        recipe = item.recipe
        if not recipe:
            continue
        if recipe.estimated_cost:
            total_cost += float(recipe.estimated_cost)
        for ri in recipe.ingredients:
            ing = getattr(ri, "ingredient", None)
            if not ing or not ing.name:
                continue
            # 单纯归类：同食材搜集各处原始用量字符串，不做克数计算
            raw_list = agg.setdefault(ing.name, [])
            q = (ri.quantity or "").strip()
            if q and q not in raw_list:
                raw_list.append(q)

    items = [
        {"name": name, "raw": raw}
        for name, raw in agg.items()
    ]
    items.sort(key=lambda x: x["name"])
    return {
        "plan_id": plan_id,
        "recipe_count": len(plan.items),
        "total_cost": round(total_cost, 2),
        "items": items,
    }


@router.get("/{plan_id}", response_model=MealPlanDetailOut)
def get_meal_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    """
    套餐详情 —— 使用 joinedload 一次性加载 items→recipe 关联链，避免 N+1。

    权限规则：
      - approved + public：所有人可见
      - pending/rejected：仅作者/管理员可见
      - private（is_public=0）：仅作者可见
      - 软删除：对所有人不可见

    由于 joinedload 已预加载 plan.items[].recipe，通过字典索引 O(1) 匹配
    recipe_title，避免嵌套循环的 O(n*m) 复杂度。
    """
    plan = (
        db.query(MealPlan)
        .options(
            joinedload(MealPlan.creator),
            joinedload(MealPlan.items).joinedload(MealPlanItem.recipe),
        )
        .filter(MealPlan.id == plan_id, MealPlan.is_deleted == 0)
        .first()
    )
    if not plan:
        raise HTTPException(status_code=404, detail="套餐不存在")

    # 权限校验
    is_author = current_user is not None and plan.user_id == current_user.id
    is_admin = current_user is not None and current_user.role == "admin"
    if not is_author and not is_admin:
        if plan.status != "approved" or not plan.is_public:
            raise HTTPException(status_code=404, detail="套餐不存在")

    # 浏览数 +1：仅审核通过的套餐计数（pending/rejected 不算浏览）
    if plan.status == "approved":
        db.execute(
            update(MealPlan).where(MealPlan.id == plan_id).values(view_count=MealPlan.view_count + 1)
        )
    _record_browse_history(db, current_user.id if current_user else None, plan_id)
    db.commit()
    db.refresh(plan)

    result = MealPlanDetailOut.model_validate(plan)
    # 使用 joinedload 已加载的 recipe 关系填充 recipe_title
    for item in result.items:
        mp_item = next((mp for mp in plan.items if mp.recipe_id == item.recipe_id), None)
        if mp_item and mp_item.recipe:
            item.recipe_title = mp_item.recipe.title

    return result


@router.post("", response_model=MealPlanDetailOut, status_code=201)
def create_meal_plan(
    data: MealPlanCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    创建套餐 —— 管理员自动 approved，普通用户进入 pending。
    批量查询关联菜谱，填充 recipe_title，解决 N+1 问题。

    安全：
      - items 必须非空，最多 20 个
      - 每个 recipe_id 必须存在且为 approved + 未删除
      - 重复添加同一 recipe_id 捕获 IntegrityError 返回友好错误
    """
    # 输入校验
    if not data.items:
        raise HTTPException(status_code=400, detail="套餐至少包含一道菜")
    if len(data.items) > 20:
        raise HTTPException(status_code=400, detail="套餐最多包含 20 道菜")

    # 校验所有 recipe_id 是否存在且为 approved + 未删除
    recipe_ids = [item.recipe_id for item in data.items]
    valid_recipes = db.query(Recipe).filter(
        Recipe.id.in_(recipe_ids),
        Recipe.is_deleted == 0,
        Recipe.status == "approved",
    ).all()
    valid_recipe_ids = {r.id for r in valid_recipes}
    invalid_ids = set(recipe_ids) - valid_recipe_ids
    if invalid_ids:
        raise HTTPException(
            status_code=400,
            detail=f"以下菜谱 ID 不存在或未通过审核：{list(invalid_ids)}",
        )

    plan = MealPlan(
        user_id=current_user.id,
        title=data.title,
        description=data.description,
        cover_image_url=data.cover_image_url,
        is_public=1 if data.is_public else 0,
        status=data.status if data.status == "draft" else ("pending" if current_user.role != "admin" else "approved"),
    )
    db.add(plan)
    db.flush()

    try:
        for item in data.items:
            db.add(MealPlanItem(
                meal_plan_id=plan.id,
                recipe_id=item.recipe_id,
                sort_order=item.sort_order,
                note=item.note,
            ))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="套餐内不能重复添加同一菜谱")
    db.refresh(plan)

    # 批量查询所有关联菜谱，填充 recipe_title
    recipes_map = {r.id: r for r in valid_recipes}

    result = MealPlanDetailOut.model_validate(plan)
    for item in result.items:
        recipe = recipes_map.get(item.recipe_id)
        if recipe:
            item.recipe_title = recipe.title

    return result


@router.put("/{plan_id}", response_model=MealPlanDetailOut)
def update_meal_plan(
    plan_id: int,
    data: MealPlanCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    更新套餐 —— 仅创建者可操作。
    采用"删旧插新"策略更新关联项，批量填充 recipe_title。

    安全：与 create 一致的输入校验
    """
    # 输入校验
    if not data.items:
        raise HTTPException(status_code=400, detail="套餐至少包含一道菜")
    if len(data.items) > 20:
        raise HTTPException(status_code=400, detail="套餐最多包含 20 道菜")

    plan = db.query(MealPlan).filter(
        MealPlan.id == plan_id,
        MealPlan.user_id == current_user.id,
        MealPlan.is_deleted == 0,
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="套餐不存在或无权操作")

    # 校验所有 recipe_id
    recipe_ids = [item.recipe_id for item in data.items]
    valid_recipes = db.query(Recipe).filter(
        Recipe.id.in_(recipe_ids),
        Recipe.is_deleted == 0,
        Recipe.status == "approved",
    ).all()
    valid_recipe_ids = {r.id for r in valid_recipes}
    invalid_ids = set(recipe_ids) - valid_recipe_ids
    if invalid_ids:
        raise HTTPException(
            status_code=400,
            detail=f"以下菜谱 ID 不存在或未通过审核：{list(invalid_ids)}",
        )

    plan.title = data.title
    plan.description = data.description
    plan.cover_image_url = data.cover_image_url
    plan.is_public = 1 if data.is_public else 0
    # 状态流转：草稿保持草稿；管理员更新后仍 approved；普通用户更新后须重新过审（pending）
    if getattr(data, "status", None) == "draft":
        plan.status = "draft"
    elif current_user.role == "admin":
        plan.status = "approved"
    else:
        plan.status = "pending"

    # 清除旧明细，添加新的
    db.query(MealPlanItem).filter(MealPlanItem.meal_plan_id == plan.id).delete()
    try:
        for item in data.items:
            db.add(MealPlanItem(
                meal_plan_id=plan.id,
                recipe_id=item.recipe_id,
                sort_order=item.sort_order,
                note=item.note,
            ))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="套餐内不能重复添加同一菜谱")
    db.refresh(plan)

    # 批量查询关联菜谱，填充 recipe_title
    recipes_map = {r.id: r for r in valid_recipes}

    result = MealPlanDetailOut.model_validate(plan)
    for item in result.items:
        recipe = recipes_map.get(item.recipe_id)
        if recipe:
            item.recipe_title = recipe.title

    return result


@router.delete("/{plan_id}", response_model=SuccessResponse)
def delete_meal_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """软删除套餐 —— 仅创建者可操作"""
    plan = db.query(MealPlan).filter(
        MealPlan.id == plan_id,
        MealPlan.user_id == current_user.id,
        MealPlan.is_deleted == 0,
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="套餐不存在或无权操作")

    plan.is_deleted = 1
    db.commit()
    return SuccessResponse(message="删除成功")
