"""后台管理 —— 仪表盘统计、标签/食材管理、菜谱/套餐审核、用户管理

权限：
  - 写操作（创建/删除/审核/禁用）均要求 role=admin
  - 标签/食材列表查询公开（创建菜谱/套餐时需要）

性能：
  - 列表查询使用 joinedload 避免 N+1
  - 用户列表不返回 password_hash
"""

from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import update

from app.database import get_db
from app.models import Recipe, MealPlan, Tag, Ingredient, User, RecipeTag, RecipeIngredient
from app.schemas.admin import AuditAction, AdminRecipeListOut, AdminMealPlanListOut
from app.schemas.recipe import RecipeDetail, RecipeUpdate
from app.schemas.common import PaginatedResponse, SuccessResponse
from app.core.deps import get_admin_user, get_current_user, get_optional_user
from app.services.rag_service import sync_recipe_to_chroma_by_id, remove_from_chroma

router = APIRouter()


# ---- 仪表盘统计 ----
@router.get("/stats")
def get_stats(db: Session = Depends(get_db), admin=Depends(get_admin_user)):
    """获取后台统计数据 —— 菜谱总数、待审核数、用户数等概览指标"""
    return {
        "total_recipes": db.query(Recipe).filter(Recipe.is_deleted == 0).count(),
        "pending_recipes": db.query(Recipe).filter(Recipe.is_deleted == 0, Recipe.status == "pending").count(),
        "pending_meal_plans": db.query(MealPlan).filter(MealPlan.is_deleted == 0, MealPlan.status == "pending").count(),
        "pending_ingredients": db.query(Ingredient).filter(Ingredient.status == "pending").count(),
        "total_users": db.query(User).count(),
        "total_meal_plans": db.query(MealPlan).filter(MealPlan.is_deleted == 0).count(),
        "total_tags": db.query(Tag).count(),
        "total_ingredients": db.query(Ingredient).count(),
    }


# ---- 标签管理 ----
@router.get("/tags")
def list_tags(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    type: str = Query(None, description="按类型筛选"),
    db: Session = Depends(get_db),
):
    """标签列表（公开，分页，支持按类型筛选）

    排序：按 id 降序（最新标签在前），便于管理员在新增标签后立即在列表顶部看到。
    """
    query = db.query(Tag)
    if type:
        query = query.filter(Tag.type == type)
    total = query.count()
    tags = query.order_by(Tag.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [{"id": t.id, "name": t.name, "type": t.type, "description": t.description} for t in tags],
    }


@router.post("/tags", response_model=SuccessResponse)
def create_tag(
    name: str = Query(..., max_length=50),
    type: str = Query(None, max_length=50),
    description: str = Query(None, max_length=255),
    db: Session = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """创建标签 —— 需要管理员权限，防重复（name+type 唯一）"""
    if db.query(Tag).filter(Tag.name == name, Tag.type == type).first():
        raise HTTPException(status_code=400, detail="标签已存在")
    tag = Tag(name=name, type=type, description=description)
    db.add(tag)
    db.commit()
    return SuccessResponse(message="创建成功", id=tag.id)


@router.put("/tags/{tag_id}", response_model=SuccessResponse)
def update_tag(
    tag_id: int,
    name: str = Query(None, max_length=50),
    type: str = Query(None, max_length=50),
    description: str = Query(None, max_length=255),
    db: Session = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """更新标签 —— 需要管理员权限（PRD FR-A06 要求支持改）"""
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    # 防重复：检查 name+type 是否与其他标签冲突
    if name is not None or type is not None:
        new_name = name or tag.name
        new_type = type if type is not None else tag.type
        existing = db.query(Tag).filter(
            Tag.name == new_name,
            Tag.type == new_type,
            Tag.id != tag_id,
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="标签名+类型已存在")
    if name is not None:
        tag.name = name
    if type is not None:
        tag.type = type
    if description is not None:
        tag.description = description
    db.commit()
    return SuccessResponse(message="更新成功")


@router.delete("/tags/{tag_id}", response_model=SuccessResponse)
def delete_tag(
    tag_id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """删除标签 —— 先清理 recipe_tags 关联行，避免外键违约或孤儿数据"""
    tag = db.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    # 标签是装饰性维度，可安全从所有菜谱上摘除
    db.query(RecipeTag).filter(RecipeTag.tag_id == tag_id).delete()
    db.delete(tag)
    db.commit()
    return SuccessResponse(message="删除成功")


# ---- 食材管理 ----
@router.get("/ingredients")
def list_ingredients(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    category: str = Query(None, description="按分类筛选"),
    status: str = Query(None, description="状态筛选：pending/rejected/all（仅管理员可见，默认只返回已审核通过的）"),
    keyword: str = Query(None, description="按名称模糊搜索"),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    """食材列表（分页）。

    权限与状态规则：
      - 默认（不传 status）：仅返回 approved 食材，公开 —— 创建菜谱/套餐的下拉选择使用
      - status=pending/rejected/all：仅管理员可用，供食材审核页与食材管理页使用
    """
    # 管理员专属的状态视图：非管理员请求会被拒绝，防止未审核食材流入公开下拉
    if status is not None:
        if current_user is None or current_user.role != "admin":
            raise HTTPException(status_code=403, detail="仅管理员可按状态查看食材")
        if status not in ("pending", "approved", "rejected", "all"):
            raise HTTPException(status_code=400, detail="status 必须为 pending/approved/rejected/all")

    query = db.query(Ingredient)
    if status is None:
        query = query.filter(Ingredient.status == "approved")
    elif status != "all":
        query = query.filter(Ingredient.status == status)
    if category:
        query = query.filter(Ingredient.category == category)
    if keyword and keyword.strip():
        query = query.filter(Ingredient.name.like(f"%{keyword.strip()}%"))
    total = query.count()
    ingredients = query.order_by(Ingredient.id.desc()).offset((page - 1) * page_size).limit(page_size).all()

    # 管理员视图补充提交人昵称（公开视图不返回 submitted_by，避免信息泄露）
    submitter_map = {}
    if status is not None:
        submitter_ids = {i.submitted_by for i in ingredients if i.submitted_by}
        if submitter_ids:
            rows = db.query(User.id, User.nickname, User.username).filter(User.id.in_(submitter_ids)).all()
            submitter_map = {r.id: (r.nickname or r.username) for r in rows}

    items = []
    for i in ingredients:
        item = {
            "id": i.id,
            "name": i.name,
            "category": i.category,
            "image_url": i.image_url,
            "status": i.status,
            "created_at": i.created_at,
        }
        if status is not None:
            item["submitted_by"] = i.submitted_by
            item["submitter_name"] = submitter_map.get(i.submitted_by, "")
        items.append(item)

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": items,
    }


@router.post("/ingredients", response_model=SuccessResponse)
def create_ingredient(
    name: str = Query(..., max_length=100),
    category: str = Query(None, max_length=50),
    image_url: str = Query(None, max_length=500),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """创建/提交食材 —— 需要登录。

    与菜谱/套餐一致的审核模式：
      - 管理员创建：直接 approved（原行为，食材管理页使用）
      - 普通用户提交：进入 pending，等待管理员在「食材审核」页审核
    防重复（name 唯一）。
    """
    if db.query(Ingredient).filter(Ingredient.name == name).first():
        raise HTTPException(status_code=400, detail="食材已存在")
    is_admin = current_user.role == "admin"
    ing = Ingredient(
        name=name,
        category=category,
        image_url=image_url,
        status="approved" if is_admin else "pending",
        submitted_by=None if is_admin else current_user.id,
    )
    db.add(ing)
    db.commit()
    return SuccessResponse(
        message="创建成功" if is_admin else "提交成功，等待管理员审核",
        id=ing.id,
    )


@router.post("/ingredients/{ingredient_id}/audit", response_model=SuccessResponse)
def audit_ingredient(
    ingredient_id: int,
    data: AuditAction,
    db: Session = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """审核用户提交的食材 —— 管理员执行 approve/reject 操作。

    驳回的食材不再出现在创建菜谱的食材下拉中；
    审核通过的食材对所有人可见（可被选入菜谱）。
    """
    ing = db.query(Ingredient).filter(Ingredient.id == ingredient_id).first()
    if not ing:
        raise HTTPException(status_code=404, detail="食材不存在")

    ing.status = "approved" if data.action == "approve" else "rejected"
    db.commit()
    return SuccessResponse(message=f"已{'通过' if data.action == 'approve' else '驳回'}")


@router.put("/ingredients/{ingredient_id}", response_model=SuccessResponse)
def update_ingredient(
    ingredient_id: int,
    name: str = Query(None, max_length=100),
    category: str = Query(None, max_length=50),
    image_url: str = Query(None, max_length=500),
    db: Session = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """更新食材 —— 需要管理员权限（PRD FR-A07 要求支持改）"""
    ing = db.query(Ingredient).filter(Ingredient.id == ingredient_id).first()
    if not ing:
        raise HTTPException(status_code=404, detail="食材不存在")
    if name is not None and name != ing.name:
        if db.query(Ingredient).filter(Ingredient.name == name, Ingredient.id != ingredient_id).first():
            raise HTTPException(status_code=400, detail="食材名已存在")
        ing.name = name
    if category is not None:
        ing.category = category
    if image_url is not None:
        ing.image_url = image_url
    db.commit()
    return SuccessResponse(message="更新成功")


@router.delete("/ingredients/{ingredient_id}", response_model=SuccessResponse)
def delete_ingredient(
    ingredient_id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """删除食材 —— 若被菜谱引用则阻止删除，避免破坏菜谱食材数据"""
    ing = db.query(Ingredient).filter(Ingredient.id == ingredient_id).first()
    if not ing:
        raise HTTPException(status_code=404, detail="食材不存在")
    # 食材被菜谱引用时不可删除（删除会破坏菜谱成分数据）
    ref_count = db.query(RecipeIngredient).filter(
        RecipeIngredient.ingredient_id == ingredient_id
    ).count()
    if ref_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"该食材被 {ref_count} 个菜谱引用，无法删除，请先移除关联后再试",
        )
    db.delete(ing)
    db.commit()
    return SuccessResponse(message="删除成功")


# ---- 菜谱审核 ----
@router.get("/recipes/pending", response_model=PaginatedResponse[AdminRecipeListOut])
def list_pending_recipes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str = Query("pending"),
    keyword: str = Query(None, description="按标题模糊搜索"),
    db: Session = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """
    待审核菜谱列表 —— 管理员查看所有指定状态的菜谱。
    支持按 status 筛选（pending/approved/rejected）和标题关键字搜索。

    性能：使用 joinedload(Recipe.author) 避免 N+1 查询
    """
    # status 枚举校验
    if status not in ("pending", "approved", "rejected"):
        raise HTTPException(status_code=400, detail="status 必须为 pending/approved/rejected")

    query = db.query(Recipe).options(joinedload(Recipe.author)).filter(
        Recipe.is_deleted == 0,
        Recipe.status == status,
    )
    if keyword and keyword.strip():
        query = query.filter(Recipe.title.like(f"%{keyword.strip()}%"))
    total = query.count()
    recipes = query.order_by(Recipe.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for r in recipes:
        item = AdminRecipeListOut.model_validate(r)
        item.author_name = r.author.nickname or r.author.username if r.author else ""
        item.reviewer_name = r.reviewer.nickname or r.reviewer.username if r.reviewer else ""
        items.append(item)

    return PaginatedResponse(total=total, page=page, page_size=page_size, items=items)


@router.post("/recipes/{recipe_id}/audit", response_model=SuccessResponse)
def audit_recipe(
    recipe_id: int,
    data: AuditAction,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """
    审核菜谱 —— 管理员执行 approve/reject 操作。
    记录审核人、审核意见、审核时间，用于审核追踪。

    向量库一致性（后台任务执行，Embedding 耗时不再阻塞审核响应）：
      - approve：菜谱入库向量库，供 RAG 检索（普通用户创建时 pending 未同步，此处补齐）
      - reject：从向量库移除分块，避免被驳回内容继续参与 RAG
    """
    recipe = db.query(Recipe).filter(
        Recipe.id == recipe_id,
        Recipe.is_deleted == 0,
    ).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="菜谱不存在")

    # reject 必须填写驳回意见
    if data.action == "reject" and not data.comment:
        raise HTTPException(status_code=400, detail="驳回时必须填写驳回意见")

    recipe.status = "approved" if data.action == "approve" else "rejected"
    recipe.reviewer_id = admin.id
    recipe.review_comment = data.comment
    recipe.reviewed_at = datetime.now()
    db.commit()

    # 审核通过 → 后台同步入向量库；驳回 → 后台移除分块（失败仅记日志，不影响审核结果）
    if data.action == "approve":
        background_tasks.add_task(sync_recipe_to_chroma_by_id, recipe.id)
    else:
        background_tasks.add_task(remove_from_chroma, "recipe", recipe.id)

    return SuccessResponse(message=f"已{'批准' if data.action == 'approve' else '驳回'}")


@router.delete("/recipes/{recipe_id}", response_model=SuccessResponse)
def admin_delete_recipe(
    recipe_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """管理员删除菜谱（软删除），并从向量库移除分块保持 RAG 一致性"""
    recipe = db.query(Recipe).filter(Recipe.id == recipe_id, Recipe.is_deleted == 0).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="菜谱不存在")
    recipe.is_deleted = 1
    db.commit()

    background_tasks.add_task(remove_from_chroma, "recipe", recipe.id)

    return SuccessResponse(message="删除成功")


# ---- 套餐审核 ----
@router.get("/meal-plans/pending", response_model=PaginatedResponse[AdminMealPlanListOut])
def list_pending_meal_plans(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str = Query("pending"),
    keyword: str = Query(None, description="按标题模糊搜索"),
    db: Session = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """待审核套餐列表（使用 joinedload 避免 N+1），支持状态筛选和标题关键字搜索"""
    if status not in ("pending", "approved", "rejected"):
        raise HTTPException(status_code=400, detail="status 必须为 pending/approved/rejected")

    query = db.query(MealPlan).options(joinedload(MealPlan.creator)).filter(
        MealPlan.is_deleted == 0,
        MealPlan.status == status,
    )
    if keyword and keyword.strip():
        query = query.filter(MealPlan.title.like(f"%{keyword.strip()}%"))
    total = query.count()
    plans = query.order_by(MealPlan.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for p in plans:
        item = AdminMealPlanListOut.model_validate(p)
        item.creator_name = p.creator.nickname or p.creator.username if p.creator else ""
        item.reviewer_name = p.reviewer.nickname or p.reviewer.username if p.reviewer else ""
        items.append(item)

    return PaginatedResponse(total=total, page=page, page_size=page_size, items=items)


@router.post("/meal-plans/{plan_id}/audit", response_model=SuccessResponse)
def audit_meal_plan(
    plan_id: int,
    data: AuditAction,
    db: Session = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """审核套餐 —— 记录审核人、意见、时间"""
    plan = db.query(MealPlan).filter(
        MealPlan.id == plan_id,
        MealPlan.is_deleted == 0,
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="套餐不存在")

    if data.action == "reject" and not data.comment:
        raise HTTPException(status_code=400, detail="驳回时必须填写驳回意见")

    plan.status = "approved" if data.action == "approve" else "rejected"
    plan.reviewer_id = admin.id
    plan.review_comment = data.comment
    plan.reviewed_at = datetime.now()
    db.commit()

    return SuccessResponse(message=f"已{'批准' if data.action == 'approve' else '驳回'}")


@router.delete("/meal-plans/{plan_id}", response_model=SuccessResponse)
def admin_delete_meal_plan(
    plan_id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """管理员删除套餐（软删除）"""
    plan = db.query(MealPlan).filter(MealPlan.id == plan_id, MealPlan.is_deleted == 0).first()
    if not plan:
        raise HTTPException(status_code=404, detail="套餐不存在")
    plan.is_deleted = 1
    db.commit()
    return SuccessResponse(message="删除成功")


# ---- 用户管理 ----
@router.get("/users")
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str = Query(None, description="按用户名/昵称/邮箱模糊搜索"),
    db: Session = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """用户列表（管理员）—— 不返回 password_hash，支持关键字搜索"""
    from sqlalchemy import or_, func as sa_func
    query = db.query(User)
    if keyword:
        kw = f"%{keyword.strip()}%"
        query = query.filter(
            or_(
                User.username.like(kw),
                User.nickname.like(kw),
                User.email.like(kw),
            )
        )
    total = query.count()
    users = query.order_by(User.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    items = [{
        "id": u.id,
        "username": u.username,
        "nickname": u.nickname,
        "email": u.email,
        "avatar_url": u.avatar_url,
        "role": u.role,
        "is_active": u.is_active,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    } for u in users]

    return PaginatedResponse(total=total, page=page, page_size=page_size, items=items)


@router.post("/users/{user_id}/toggle-active", response_model=SuccessResponse)
def toggle_user_active(
    user_id: int,
    db: Session = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """启用/禁用用户 —— 不能禁用管理员账户，不能禁用自己"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.role == "admin":
        raise HTTPException(status_code=400, detail="不能禁用管理员")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="不能禁用自己的账户")
    user.is_active = 1 if user.is_active == 0 else 0
    db.commit()
    return SuccessResponse(message="操作成功")


@router.post("/users/{user_id}/role", response_model=SuccessResponse)
def update_user_role(
    user_id: int,
    role: str = Query(..., pattern="^(user|admin)$"),
    db: Session = Depends(get_db),
    admin=Depends(get_admin_user),
):
    """调整用户角色（PRD FR-A05）"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == admin.id and role != "admin":
        raise HTTPException(status_code=400, detail="不能撤销自己的管理员权限")
    user.role = role
    db.commit()
    return SuccessResponse(message="角色已更新")
