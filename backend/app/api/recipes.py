"""菜谱相关接口 —— 菜谱的 CRUD、列表搜索、RAG 向量同步

安全设计：
  - 列表接口 status 参数限定为 approved（公开）+ pending/rejected（仅管理员可选）
  - 详情接口对非作者/非管理员用户隐藏未审核菜谱
  - 封面图强制走白名单校验（meishichina/xiachufang/douguo/xiangha + HTTPS）
  - 浏览数+1 使用 UPDATE 语句原子操作，避免并发计数异常
  - 浏览历史自动记录（仅登录用户），单用户单菜谱最近一次浏览时间，避免表膨胀
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, func, desc, asc, update, case
from datetime import datetime, timedelta

from app.database import get_db
from app.models import (
    Recipe, RecipeTag, RecipeStep, RecipeIngredient, Tag, Ingredient,
    UserBrowseHistory, User,
)
from app.schemas.recipe import (
    RecipeCreate, RecipeUpdate, RecipeDetail, RecipeListItem, RecipeSearchParams,
    RecipeIngredientCreate, StepCreate, TagInfo,
)
from app.schemas.common import PaginatedResponse, SuccessResponse
from app.core.deps import get_current_user, get_optional_user
from app.services.rag_service import sync_recipe_to_chroma_by_id, remove_from_chroma
from app.utils.validation import sanitize_recipe_cover, parse_int_list
from app.utils.browse_history import upsert_browse_history

router = APIRouter()

DEFAULT_COVER = "/static/recipe_covers/default.jpg"

# 允许的排序字段白名单，防止 SQL 注入风险
_ALLOWED_SORT_FIELDS = {"created_at", "estimated_cost", "view_count", "favorite_count", "difficulty"}
# 公开列表允许的 status 值
_PUBLIC_STATUS = "approved"


def _get_valid_cover(recipe: Recipe) -> str:
    """获取有效封面：基于白名单校验，不安全则回退默认封面"""
    return sanitize_recipe_cover(recipe.cover_image_url, DEFAULT_COVER)


def _enrich_recipe_list_item(recipe: Recipe) -> RecipeListItem:
    """
    将 ORM 对象转为 API 列表项。

    注意：recipe.tags 返回的是 RecipeTag 关联对象（含 recipe_id/tag_id），
    实际的标签信息(id/name/type)在 RecipeTag.tag 中，因此需要手动转换。
    """
    tag_infos = [
        TagInfo(id=t.tag.id, name=t.tag.name, type=t.tag.type)
        for t in recipe.tags
    ]
    return RecipeListItem(
        id=recipe.id,
        title=recipe.title,
        description=recipe.description,
        cover_image_url=_get_valid_cover(recipe),
        difficulty=recipe.difficulty,
        cooking_time=recipe.cooking_time,
        estimated_cost=recipe.estimated_cost,
        view_count=recipe.view_count,
        favorite_count=recipe.favorite_count,
        status=recipe.status,
        review_comment=recipe.review_comment,
        tags=tag_infos,
        created_at=recipe.created_at,
    )


def _enrich_recipe_detail(recipe: Recipe, restrictions=None) -> RecipeDetail:
    """
    将 ORM 对象转为菜谱详情。

    处理 tags 字段的特殊映射（RecipeTag→Tag→TagInfo），
    其余字段由 Pydantic from_attributes 自动映射。
    restrictions：当前用户的忌口标签集合（可选），用于计算 diet_warnings。
    """
    tag_infos = [
        TagInfo(id=t.tag.id, name=t.tag.name, type=t.tag.type)
        for t in recipe.tags
    ]
    from app.utils.nutrition import compute_recipe_nutrition
    from app.utils.recipe_diet import recipe_diet_warnings
    return RecipeDetail(
        id=recipe.id,
        title=recipe.title,
        description=recipe.description,
        cover_image_url=_get_valid_cover(recipe),
        difficulty=recipe.difficulty,
        cooking_time=recipe.cooking_time,
        servings=recipe.servings,
        estimated_cost=recipe.estimated_cost,
        author_id=recipe.author_id,
        author_nickname=recipe.author_nickname,
        author_avatar_url=recipe.author.avatar_url if recipe.author else None,
        status=recipe.status,
        view_count=recipe.view_count,
        favorite_count=recipe.favorite_count,
        review_comment=recipe.review_comment,
        tags=tag_infos,
        ingredients=recipe.ingredients,
        steps=recipe.steps,
        nutrition=compute_recipe_nutrition(recipe.ingredients),
        diet_warnings=recipe_diet_warnings(recipe, restrictions or set()),
        created_at=recipe.created_at,
        updated_at=recipe.updated_at,
    )


def _validate_cover_image_url(url):
    """校验封面图 URL，不合法则拒绝"""
    if url is None or url == "":
        return
    from app.utils.validation import is_safe_recipe_cover_url
    if not is_safe_recipe_cover_url(url):
        raise HTTPException(
            status_code=400,
            detail={
                "message": "封面图 URL 不合法",
                "detail": "仅允许来自 meishichina.com、xiachufang.com、douguo.com、xiangha.com 的 HTTPS 链接，或本地 /static 路径",
            },
        )


def _record_browse_history(db: Session, user_id: int | None, recipe_id: int):
    """
    自动记录浏览历史（FR-R02 要求）—— 委托公共 upsert 实现。

    策略：
      - 登录用户：记录浏览历史；同一用户对同一菜谱只保留最近一条记录（去重）
      - 未登录用户：不记录
    """
    upsert_browse_history(db, user_id, recipe_id=recipe_id)


@router.get("", response_model=PaginatedResponse[RecipeListItem])
def list_recipes(
    keyword: str = Query(None, description="搜索关键词", max_length=200),
    difficulty: str = Query(None, description="难度筛选：easy/medium/hard，支持逗号分隔多选，如 easy,medium"),
    tag_ids: str = Query(None, description="标签ID，逗号分隔"),
    min_cost: float = Query(None, description="最低预算", ge=0),
    max_cost: float = Query(None, description="最高预算", ge=0),
    sort_by: str = Query(
        "created_at",
        description="排序字段：created_at(时间) / estimated_cost(价格) / view_count / favorite_count / difficulty(难度)",
    ),
    sort_order: str = Query(
        "desc",
        description="排序方向：asc(升序) / desc(降序)",
    ),
    status: str = Query(
        "approved",
        description="状态筛选：approved(公开可见)；管理员可传 pending/rejected",
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    mine: int = Query(0, description="只看我创建的（含草稿/待审核/已驳回）"),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    """菜谱列表与搜索 —— 支持关键词、难度、标签、预算区间多维度筛选，支持按价格/时间排序

    安全约束：
      - 未开启 mine 时 status 仅允许 approved（公开）；其他状态需通过管理后台接口访问
      - difficulty 限定为枚举值
      - tag_ids 使用安全解析避免 ValueError
    """
    # 只看自己的：仅作者可见，展示全部状态（草稿/待审/驳回/已上架）
    if mine:
        if current_user is None:
            return PaginatedResponse(total=0, page=page, page_size=page_size, items=[])
        query = db.query(Recipe).filter(
            Recipe.is_deleted == 0,
            Recipe.author_id == current_user.id,
        )
        if status and status not in ("approved", "pending", "rejected", "draft"):
            raise HTTPException(status_code=400, detail="status 值不合法")
        if status:
            query = query.filter(Recipe.status == status)
    else:
        # 严格限制公开列表只能看 approved
        if status != _PUBLIC_STATUS:
            raise HTTPException(status_code=400, detail={"message": "不允许的 status 值", "detail": None})
        query = db.query(Recipe).filter(
            Recipe.is_deleted == 0,
            Recipe.status == _PUBLIC_STATUS,
        )

    # difficulty 枚举校验（支持逗号分隔多选）
    difficulty_list = []
    if difficulty:
        difficulty_list = [d for d in difficulty.split(",") if d]
        diff_ids = ("easy", "medium", "hard")
        if not all(d in diff_ids for d in difficulty_list):
            raise HTTPException(status_code=400, detail="difficulty 必须为 easy/medium/hard 之一，逗号分隔")

    if keyword:
        query = query.filter(
            or_(
                Recipe.title.contains(keyword),
                Recipe.description.contains(keyword),
            )
        )
    if difficulty_list:
        query = query.filter(Recipe.difficulty.in_(difficulty_list))
    if min_cost is not None:
        query = query.filter(Recipe.estimated_cost >= min_cost)
    if max_cost is not None:
        query = query.filter(Recipe.estimated_cost <= max_cost)
    if tag_ids:
        ids = parse_int_list(tag_ids, max_items=50)
        if ids:
            query = query.join(RecipeTag).filter(RecipeTag.tag_id.in_(ids))

    # 排序字段白名单，防止任意字段排序
    sort_by = sort_by if sort_by in _ALLOWED_SORT_FIELDS else "created_at"
    sort_order = sort_order if sort_order in ("asc", "desc") else "desc"
    if sort_by == "difficulty":
        # 难度按 easy/medium/hard 权重排序（字符串字典序为 easy<hard<medium，不符合直觉）
        sort_column = case(
            (Recipe.difficulty == "easy", 0),
            (Recipe.difficulty == "medium", 1),
            else_=2,
        )
    else:
        sort_column = getattr(Recipe, sort_by)
    query = query.order_by(desc(sort_column) if sort_order == "desc" else asc(sort_column))

    total = query.count()
    recipes = (
        query.options(joinedload(Recipe.tags).joinedload(RecipeTag.tag))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [_enrich_recipe_list_item(r) for r in recipes]
    return PaginatedResponse(total=total, page=page, page_size=page_size, items=items)


@router.get("/hot", response_model=PaginatedResponse[RecipeListItem])
def list_hot_recipes(
    page_size: int = Query(8, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """本周热门菜谱 —— 基于 UserBrowseHistory 统计本周（近7天）浏览次数，
    按本周浏览次数降序返回。若本周无浏览记录则回退到总 view_count 排序。

    返回的 total 字段为数据库中已通过审核且未删除的菜谱总数，用于首页统计展示。"""
    week_ago = datetime.now() - timedelta(days=7)

    # 数据库中的菜谱总数（用于首页统计展示）
    total_recipes = db.query(Recipe).filter(
        Recipe.is_deleted == 0,
        Recipe.status == "approved",
    ).count()

    # 子查询：本周每个菜谱的浏览次数
    weekly_counts = (
        db.query(
            UserBrowseHistory.recipe_id,
            func.count(UserBrowseHistory.id).label("weekly_views"),
        )
        .filter(
            UserBrowseHistory.recipe_id.isnot(None),
            UserBrowseHistory.viewed_at >= week_ago,
        )
        .group_by(UserBrowseHistory.recipe_id)
        .subquery()
    )

    # 先尝试本周有浏览记录的菜谱
    recipes = (
        db.query(Recipe)
        .join(weekly_counts, Recipe.id == weekly_counts.c.recipe_id)
        .filter(Recipe.is_deleted == 0, Recipe.status == "approved")
        .options(joinedload(Recipe.tags).joinedload(RecipeTag.tag))
        .order_by(desc(weekly_counts.c.weekly_views))
        .limit(page_size)
        .all()
    )

    # 回退：本周无浏览记录时按总 view_count 排序
    if not recipes:
        recipes = (
            db.query(Recipe)
            .filter(Recipe.is_deleted == 0, Recipe.status == "approved")
            .options(joinedload(Recipe.tags).joinedload(RecipeTag.tag))
            .order_by(Recipe.view_count.desc())
            .limit(page_size)
            .all()
        )

    items = [_enrich_recipe_list_item(r) for r in recipes]
    return PaginatedResponse(total=total_recipes, page=1, page_size=page_size, items=items)


@router.get("/{recipe_id}", response_model=RecipeDetail)
def get_recipe(
    recipe_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    """
    获取菜谱详情 —— 使用 joinedload 一次性加载标签、食材、步骤，
    避免 N+1 查询问题。

    权限规则：
      - approved 状态：所有人可见
      - pending/rejected 状态：仅作者本人或管理员可见
      - 软删除（is_deleted=1）：对所有人不可见

    副作用：
      - 浏览数 +1（原子 UPDATE，避免并发计数异常）
      - 自动记录浏览历史（登录用户，去重避免表膨胀）
    """
    recipe = (
        db.query(Recipe)
        .options(
            joinedload(Recipe.tags).joinedload(RecipeTag.tag),
            joinedload(Recipe.ingredients).joinedload(RecipeIngredient.ingredient),
            joinedload(Recipe.steps),
        )
        .filter(Recipe.id == recipe_id, Recipe.is_deleted == 0)
        .first()
    )
    if not recipe:
        raise HTTPException(status_code=404, detail="菜谱不存在")

    # 权限校验：非公开菜谱仅作者/管理员可见
    if recipe.status != "approved":
        is_author = current_user is not None and recipe.author_id == current_user.id
        is_admin = current_user is not None and current_user.role == "admin"
        if not (is_author or is_admin):
            raise HTTPException(status_code=404, detail="菜谱不存在")

    # 浏览数 +1：仅审核通过的菜谱计数（pending/rejected 不算浏览，避免未过审内容虚增热度）
    if recipe.status == "approved":
        db.execute(
            update(Recipe).where(Recipe.id == recipe_id).values(view_count=Recipe.view_count + 1)
        )
    # 记录浏览历史（登录用户）
    _record_browse_history(db, current_user.id if current_user else None, recipe_id)
    db.commit()

    # commit（expire_on_commit）会使开头 joinedload 预加载的关系全部过期，
    # 若直接序列化，_enrich 时 tags/ingredients/steps 会退化为逐集合懒加载（N+1）。
    # 这里重新执行一次预加载查询（同一会话内对象身份复用，关系一次性加载回来），
    # 并补上 author 预加载 —— 详情页需要作者头像，原查询遗漏会多一次懒加载。
    recipe = (
        db.query(Recipe)
        .options(
            joinedload(Recipe.author),
            joinedload(Recipe.tags).joinedload(RecipeTag.tag),
            joinedload(Recipe.ingredients).joinedload(RecipeIngredient.ingredient),
            joinedload(Recipe.steps),
        )
        .filter(Recipe.id == recipe_id, Recipe.is_deleted == 0)
        .first()
    )

    from app.utils.recipe_diet import get_restriction_set
    return _enrich_recipe_detail(recipe, get_restriction_set(current_user))


@router.post("", response_model=RecipeDetail, status_code=201)
def create_recipe(
    data: RecipeCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    创建菜谱（需要登录）。
    管理员创建的菜谱自动 approved，普通用户创建的进入 pending 审核流程。
    创建完成后自动同步到 Chroma 向量库以供 RAG 检索。

    安全：
      - 封面图 URL 强制白名单校验
      - difficulty 枚举校验
      - tag_ids 数量限制
    """
    # 封面图白名单校验
    _validate_cover_image_url(data.cover_image_url)
    # difficulty 枚举校验
    if data.difficulty and data.difficulty not in ("easy", "medium", "hard"):
        raise HTTPException(status_code=400, detail="difficulty 必须为 easy/medium/hard")
    # 标签数量限制
    if len(data.tag_ids) > 20:
        raise HTTPException(status_code=400, detail="标签数量不能超过 20 个")

    # 校验 tag_ids 与 ingredient_id 是否存在，避免外键约束触发 500 错误
    if data.tag_ids:
        valid_tag_ids = {t.id for t in db.query(Tag.id).filter(Tag.id.in_(data.tag_ids)).all()}
        invalid_tag_ids = set(data.tag_ids) - valid_tag_ids
        if invalid_tag_ids:
            raise HTTPException(
                status_code=400,
                detail=f"标签 ID 不存在: {sorted(invalid_tag_ids)}",
            )
    if data.ingredients:
        ing_ids = [ing.ingredient_id for ing in data.ingredients]
        valid_ing_ids = {i.id for i in db.query(Ingredient.id).filter(Ingredient.id.in_(ing_ids)).all()}
        invalid_ing_ids = set(ing_ids) - valid_ing_ids
        if invalid_ing_ids:
            raise HTTPException(
                status_code=400,
                detail=f"食材 ID 不存在: {sorted(invalid_ing_ids)}",
            )

    recipe = Recipe(
        title=data.title,
        description=data.description,
        cover_image_url=data.cover_image_url,
        difficulty=data.difficulty,
        cooking_time=data.cooking_time,
        servings=data.servings,
        estimated_cost=data.estimated_cost,
        author_id=current_user.id,
        status=data.status if data.status == "draft" else ("pending" if current_user.role != "admin" else "approved"),
    )
    db.add(recipe)
    db.flush()

    # 标签关联
    for tag_id in data.tag_ids:
        db.add(RecipeTag(recipe_id=recipe.id, tag_id=tag_id))

    # 食材关联
    for ing in data.ingredients:
        db.add(RecipeIngredient(
            recipe_id=recipe.id,
            ingredient_id=ing.ingredient_id,
            quantity=ing.quantity,
            note=ing.note,
            sort_order=ing.sort_order,
        ))

    # 步骤
    for step in data.steps:
        db.add(RecipeStep(
            recipe_id=recipe.id,
            step_number=step.step_number,
            instruction=step.instruction,
            duration=step.duration,
        ))

    db.commit()
    db.refresh(recipe)

    # 同步到向量库（后台执行，失败仅记日志不影响主流程）
    # 仅 approved 状态入向量库：普通用户创建的 pending 菜谱须过审后（审核路由）再同步，
    # 避免未过审内容被 RAG 检索到
    if recipe.status == "approved":
        background_tasks.add_task(sync_recipe_to_chroma_by_id, recipe.id)

    return _enrich_recipe_detail(recipe)


@router.put("/{recipe_id}", response_model=RecipeDetail)
def update_recipe(
    recipe_id: int,
    data: RecipeUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    更新菜谱 —— 仅作者可操作。
    采用"先删后插"策略更新标签、食材、步骤关联数据，
    代码简单且避免了逐条比对的复杂性。

    安全：
      - 封面图白名单校验
      - difficulty 枚举校验
      - 编辑后自动重新同步向量库（先删后插，幂等）
    """
    recipe = db.query(Recipe).filter(
        Recipe.id == recipe_id,
        Recipe.is_deleted == 0,
        Recipe.author_id == current_user.id,
    ).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="菜谱不存在或无权操作")

    # 封面图白名单校验
    _validate_cover_image_url(data.cover_image_url)
    # difficulty 枚举校验
    if data.difficulty and data.difficulty not in ("easy", "medium", "hard"):
        raise HTTPException(status_code=400, detail="difficulty 必须为 easy/medium/hard")
    # 标签数量限制
    if data.tag_ids is not None and len(data.tag_ids) > 20:
        raise HTTPException(status_code=400, detail="标签数量不能超过 20 个")

    # 校验 tag_ids 与 ingredient_id 是否存在（与 create 一致，避免外键约束触发 500 错误）
    if data.tag_ids is not None:
        valid_tag_ids = {t.id for t in db.query(Tag.id).filter(Tag.id.in_(data.tag_ids)).all()}
        invalid_tag_ids = set(data.tag_ids) - valid_tag_ids
        if invalid_tag_ids:
            raise HTTPException(
                status_code=400,
                detail=f"标签 ID 不存在: {sorted(invalid_tag_ids)}",
            )
    if data.ingredients is not None:
        ing_ids = [ing.ingredient_id for ing in data.ingredients]
        valid_ing_ids = {i.id for i in db.query(Ingredient.id).filter(Ingredient.id.in_(ing_ids)).all()}
        invalid_ing_ids = set(ing_ids) - valid_ing_ids
        if invalid_ing_ids:
            raise HTTPException(
                status_code=400,
                detail=f"食材 ID 不存在: {sorted(invalid_ing_ids)}",
            )

    # 更新基础字段
    update_data = data.model_dump(exclude_unset=True, exclude={"tag_ids", "ingredients", "steps", "status"})
    for key, value in update_data.items():
        setattr(recipe, key, value)

    # 状态流转：草稿保持草稿；管理员更新后仍直接 approved；普通用户更新后须重新过审（pending）
    if data.status == "draft":
        recipe.status = "draft"
    elif current_user.role == "admin":
        recipe.status = "approved"
    else:
        recipe.status = "pending"

    # 更新标签（删旧插新）
    if data.tag_ids is not None:
        db.query(RecipeTag).filter(RecipeTag.recipe_id == recipe.id).delete()
        for tag_id in data.tag_ids:
            db.add(RecipeTag(recipe_id=recipe.id, tag_id=tag_id))

    # 更新食材（删旧插新）
    if data.ingredients is not None:
        db.query(RecipeIngredient).filter(RecipeIngredient.recipe_id == recipe.id).delete()
        for ing in data.ingredients:
            db.add(RecipeIngredient(
                recipe_id=recipe.id,
                ingredient_id=ing.ingredient_id,
                quantity=ing.quantity,
                note=ing.note,
                sort_order=ing.sort_order,
            ))

    # 更新步骤（删旧插新）
    if data.steps is not None:
        db.query(RecipeStep).filter(RecipeStep.recipe_id == recipe.id).delete()
        for step in data.steps:
            db.add(RecipeStep(
                recipe_id=recipe.id,
                step_number=step.step_number,
                instruction=step.instruction,
                duration=step.duration,
            ))

    db.commit()
    db.refresh(recipe)

    # 同步到向量库（后台执行）：仅 approved 菜谱参与 RAG；pending/rejected 编辑后不同步，
    # 待审核通过时由审核路由统一同步
    if recipe.status == "approved":
        background_tasks.add_task(sync_recipe_to_chroma_by_id, recipe.id)

    return _enrich_recipe_detail(recipe)


@router.delete("/{recipe_id}", response_model=SuccessResponse)
def delete_recipe(
    recipe_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    软删除菜谱 —— 仅作者可操作。
    使用 is_deleted=1 标记而非物理删除，保护数据完整性。
    同时从向量库移除对应分块，避免 RAG 继续推荐已删除内容。
    """
    recipe = db.query(Recipe).filter(
        Recipe.id == recipe_id,
        Recipe.is_deleted == 0,
        Recipe.author_id == current_user.id,
    ).first()
    if not recipe:
        raise HTTPException(status_code=404, detail="菜谱不存在或无权操作")

    recipe.is_deleted = 1
    db.commit()

    # 从向量库移除（后台执行，失败不影响删除主流程，可通过 rebuild 修复）
    background_tasks.add_task(remove_from_chroma, "recipe", recipe.id)

    return SuccessResponse(message="删除成功")
