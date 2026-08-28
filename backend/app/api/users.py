"""用户中心 —— 个人信息、密码、收藏、浏览历史、AI对话历史

安全设计：
  - record_browse_history 强制要求 recipe_id 或 meal_plan_id 二选一
  - 添加收藏时校验 favorite_id 对应的对象存在、未删除、已审核通过（公开可见）
  - 收藏/取消收藏时使用原子 UPDATE 维护 favorite_count 计数
  - 收藏列表批量查询关联对象，避免 N+1
  - 浏览历史批量查询关联菜谱，避免 N+1
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import update, func
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models import (
    User, UserFavorite, UserBrowseHistory, Recipe, MealPlan,
    AiConversation, AiMessage,
)
from app.schemas.user import UserInfo, UserUpdate, PasswordChange, UserPreferences
from app.schemas.recipe import RecipeListItem, TagInfo
from app.schemas.interaction import MealPlanListOut
from app.schemas.ai import AiConversationOut, AiConversationDetailOut
from app.schemas.common import PaginatedResponse, SuccessResponse
from app.core.deps import get_current_user
from app.core.security import verify_password, hash_password
from app.utils.browse_history import upsert_browse_history

router = APIRouter()


def _delete_favorite_and_sync_count(db: Session, fav: UserFavorite) -> None:
    """
    删除收藏记录并同步递减对应对象的 favorite_count。

    两个取消收藏接口（按记录 ID / 按业务类型+ID）的公共收尾逻辑：
      - favorite_count 使用原子 UPDATE 并带 > 0 条件，防止并发下减成负数
      - 删除记录并提交事务
    """
    if fav.favorite_type == "recipe":
        db.execute(
            update(Recipe)
            .where(Recipe.id == fav.favorite_id, Recipe.favorite_count > 0)
            .values(favorite_count=Recipe.favorite_count - 1)
        )
    else:
        db.execute(
            update(MealPlan)
            .where(MealPlan.id == fav.favorite_id, MealPlan.favorite_count > 0)
            .values(favorite_count=MealPlan.favorite_count - 1)
        )
    db.delete(fav)
    db.commit()


def _validate_favorite_target(db: Session, favorite_type: str, favorite_id: int) -> None:
    """
    校验收藏目标存在性 —— 防止收藏不存在的菜谱/套餐。

    规则：
      - recipe 类型：菜谱必须存在、未删除、已审核通过（公开可见才允许收藏）
      - meal_plan 类型：套餐必须存在、未删除、已审核通过
    """
    if favorite_type == "recipe":
        obj = db.query(Recipe).filter(
            Recipe.id == favorite_id,
            Recipe.is_deleted == 0,
            Recipe.status == "approved",
        ).first()
        if not obj:
            raise HTTPException(status_code=400, detail="菜谱不存在或未通过审核")
    elif favorite_type == "meal_plan":
        obj = db.query(MealPlan).filter(
            MealPlan.id == favorite_id,
            MealPlan.is_deleted == 0,
            MealPlan.status == "approved",
        ).first()
        if not obj:
            raise HTTPException(status_code=400, detail="套餐不存在或未通过审核")


# ---- 个性化偏好 ----
@router.get("/preferences", response_model=UserPreferences)
def get_preferences(current_user=Depends(get_current_user)):
    """获取当前用户的个性化偏好（无则返回空结构）"""
    data = current_user.preferences or {}
    return UserPreferences(
        cuisines=data.get("cuisines", []),
        diet_tags=data.get("diet_tags", []),
        free_text=data.get("free_text", ""),
    )


@router.put("/preferences", response_model=SuccessResponse)
def update_preferences(
    data: UserPreferences,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """保存个性化偏好（菜系标签 + 忌口/过敏原 + 自由文本描述）"""
    current_user.preferences = {
        "cuisines": data.cuisines,
        "diet_tags": data.diet_tags,
        "free_text": data.free_text.strip(),
    }
    db.commit()
    return SuccessResponse(message="偏好已保存")


# ---- 个人信息 ----
@router.put("/profile", response_model=UserInfo)
def update_profile(
    data: UserUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """更新个人信息（昵称、邮箱、头像）—— PRD FR-U03

    安全：
      - 邮箱修改需校验唯一性（与其他用户邮箱冲突时拒绝）
      - 头像 URL 仅做基本长度限制（前端展示，不做白名单限制以保持灵活性）
    """
    if data.nickname is not None:
        current_user.nickname = data.nickname
    if data.email is not None and data.email != current_user.email:
        # 邮箱唯一性校验：检查是否被其他用户占用
        existing = db.query(User).filter(
            User.email == data.email,
            User.id != current_user.id,
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="邮箱已被其他用户注册")
        current_user.email = data.email
    if data.avatar_url is not None:
        current_user.avatar_url = data.avatar_url
    db.commit()
    db.refresh(current_user)
    return UserInfo.model_validate(current_user)


@router.put("/password", response_model=SuccessResponse)
def change_password(
    data: PasswordChange,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """修改密码 —— 需验证原密码，且新密码不能与原密码相同"""
    if not verify_password(data.old_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="原密码错误")
    if data.old_password == data.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与原密码相同")
    current_user.password_hash = hash_password(data.new_password)
    db.commit()
    return SuccessResponse(message="密码修改成功")


# ---- 收藏管理 ----
@router.post("/favorites", response_model=SuccessResponse)
def add_favorite(
    favorite_type: str = Query(..., pattern="^(recipe|meal_plan)$"),
    favorite_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """添加收藏 —— 防重复：已收藏则返回 400；目标对象必须存在且公开可见"""
    # 校验收藏目标存在性
    _validate_favorite_target(db, favorite_type, favorite_id)

    existing = db.query(UserFavorite).filter_by(
        user_id=current_user.id,
        favorite_type=favorite_type,
        favorite_id=favorite_id,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="已收藏")

    fav = UserFavorite(
        user_id=current_user.id,
        favorite_type=favorite_type,
        favorite_id=favorite_id,
    )
    db.add(fav)
    try:
        db.flush()
    except IntegrityError:
        # 并发兜底：同一用户双击收藏按钮时，两个请求都通过了上方的
        # SELECT 查重；第二个 flush 撞 uk_user_fav 唯一约束说明对方已
        # 抢先插入成功。回滚本事务（其中只有这条插入，无其他变更），
        # 按串行路径同样的语义返回 400"已收藏"，避免 500 吓到用户。
        db.rollback()
        raise HTTPException(status_code=400, detail="已收藏")

    # 同步 favorite_count +1（原子 UPDATE）
    if favorite_type == "recipe":
        db.execute(
            update(Recipe).where(Recipe.id == favorite_id).values(
                favorite_count=Recipe.favorite_count + 1
            )
        )
    else:
        db.execute(
            update(MealPlan).where(MealPlan.id == favorite_id).values(
                favorite_count=MealPlan.favorite_count + 1
            )
        )
    db.commit()
    return SuccessResponse(message="收藏成功", id=fav.id)


@router.delete("/favorites/{favorite_id}", response_model=SuccessResponse)
def remove_favorite(
    favorite_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """取消收藏（按收藏记录ID）—— 同步 favorite_count -1"""
    fav = db.query(UserFavorite).filter_by(
        id=favorite_id,
        user_id=current_user.id,
    ).first()
    if not fav:
        raise HTTPException(status_code=404, detail="收藏不存在")

    _delete_favorite_and_sync_count(db, fav)
    return SuccessResponse(message="已取消收藏")


@router.delete("/favorites/by/{item_type}/{item_id}", response_model=SuccessResponse)
def remove_favorite_by_item(
    item_type: str,
    item_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """取消收藏（按业务类型和ID）—— 同步 favorite_count -1"""
    if item_type not in ("recipe", "meal_plan"):
        raise HTTPException(status_code=400, detail="无效的收藏类型")
    fav = db.query(UserFavorite).filter_by(
        user_id=current_user.id,
        favorite_type=item_type,
        favorite_id=item_id,
    ).first()
    if not fav:
        raise HTTPException(status_code=404, detail="收藏不存在")

    _delete_favorite_and_sync_count(db, fav)
    return SuccessResponse(message="已取消收藏")


@router.get("/favorites", response_model=PaginatedResponse)
def get_favorites(
    favorite_type: str = Query("recipe", pattern="^(recipe|meal_plan)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    获取我的收藏列表。

    性能优化：先一次性取出所有收藏记录，再按类型批量查询关联的 recipe/meal_plan，
    避免逐条查询的 N+1 问题。
    """
    query = db.query(UserFavorite).filter_by(
        user_id=current_user.id,
        favorite_type=favorite_type,
    )
    total = query.count()
    favs = query.order_by(UserFavorite.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    items = []
    if favorite_type == "recipe":
        # 批量获取所有关联的菜谱
        recipe_ids = [f.favorite_id for f in favs]
        recipes_map = {}
        if recipe_ids:
            recipe_list = db.query(Recipe).filter(
                Recipe.id.in_(recipe_ids),
                Recipe.is_deleted == 0,
            ).all()
            recipes_map = {r.id: r for r in recipe_list}

        for fav in favs:
            recipe = recipes_map.get(fav.favorite_id)
            if recipe:
                items.append({
                    "favorite_id": fav.id,
                    "type": "recipe",
                    "data": {
                        "id": recipe.id,
                        "title": recipe.title,
                        "cover_image_url": recipe.cover_image_url,
                        "difficulty": recipe.difficulty,
                        "cooking_time": recipe.cooking_time,
                        "estimated_cost": float(recipe.estimated_cost) if recipe.estimated_cost else None,
                        "view_count": recipe.view_count,
                        "favorite_count": recipe.favorite_count,
                        "created_at": recipe.created_at.isoformat() if recipe.created_at else None,
                    },
                })
    else:
        # 批量获取所有关联的套餐
        plan_ids = [f.favorite_id for f in favs]
        plans_map = {}
        if plan_ids:
            plan_list = db.query(MealPlan).filter(
                MealPlan.id.in_(plan_ids),
                MealPlan.is_deleted == 0,
            ).all()
            plans_map = {p.id: p for p in plan_list}

        for fav in favs:
            plan = plans_map.get(fav.favorite_id)
            if plan:
                items.append({
                    "favorite_id": fav.id,
                    "type": "meal_plan",
                    "data": {
                        "id": plan.id,
                        "title": plan.title,
                        "cover_image_url": plan.cover_image_url,
                        "status": plan.status,
                        "favorite_count": plan.favorite_count,
                        "created_at": plan.created_at.isoformat() if plan.created_at else None,
                    },
                })

    return PaginatedResponse(total=total, page=page, page_size=page_size, items=items)


# ---- 浏览历史 ----
@router.post("/history", response_model=SuccessResponse)
def record_browse_history(
    recipe_id: int = Query(None, ge=1),
    meal_plan_id: int = Query(None, ge=1),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """记录浏览历史 —— recipe_id 和 meal_plan_id 必须二选一

    安全：
      - 强制二选一校验，避免脏数据
      - 校验对应对象存在
      - 去重：单用户单对象只保留最近一条记录
    """
    # 二选一校验
    if recipe_id is None and meal_plan_id is None:
        raise HTTPException(
            status_code=400,
            detail="recipe_id 和 meal_plan_id 必须二选一",
        )
    if recipe_id is not None and meal_plan_id is not None:
        raise HTTPException(
            status_code=400,
            detail="recipe_id 和 meal_plan_id 不能同时传",
        )

    # 校验对应对象存在
    if recipe_id is not None:
        obj = db.query(Recipe).filter(
            Recipe.id == recipe_id,
            Recipe.is_deleted == 0,
        ).first()
        if not obj:
            raise HTTPException(status_code=400, detail="菜谱不存在")
    else:
        obj = db.query(MealPlan).filter(
            MealPlan.id == meal_plan_id,
            MealPlan.is_deleted == 0,
        ).first()
        if not obj:
            raise HTTPException(status_code=400, detail="套餐不存在")

    # 去重写入：单用户单对象只保留最近一条记录（公共 upsert，与菜谱详情页共用）
    upsert_browse_history(
        db, current_user.id,
        recipe_id=recipe_id, meal_plan_id=meal_plan_id,
    )
    db.commit()
    return SuccessResponse(message="已记录")


@router.get("/history", response_model=PaginatedResponse)
def get_browse_history(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    获取浏览历史。

    性能优化：先收集所有 recipe_id，批量查询关联菜谱，
    避免在循环中逐条查询的 N+1 问题。
    """
    query = db.query(UserBrowseHistory).filter(UserBrowseHistory.user_id == current_user.id)
    total = query.count()
    histories = query.order_by(UserBrowseHistory.viewed_at.desc()).offset((page - 1) * page_size).limit(page_size).all()

    # 批量获取菜谱
    recipe_ids = [h.recipe_id for h in histories if h.recipe_id]
    recipes_map = {}
    if recipe_ids:
        recipe_list = db.query(Recipe).filter(Recipe.id.in_(recipe_ids)).all()
        recipes_map = {r.id: r for r in recipe_list}

    # 批量获取套餐
    plan_ids = [h.meal_plan_id for h in histories if h.meal_plan_id]
    plans_map = {}
    if plan_ids:
        plan_list = db.query(MealPlan).filter(MealPlan.id.in_(plan_ids)).all()
        plans_map = {p.id: p for p in plan_list}

    items = []
    for h in histories:
        if h.recipe_id:
            recipe = recipes_map.get(h.recipe_id)
            if recipe:
                items.append({
                    "id": h.id,
                    "type": "recipe",
                    "data": {
                        "id": recipe.id,
                        "title": recipe.title,
                        "cover_image_url": recipe.cover_image_url,
                        "difficulty": recipe.difficulty,
                        "estimated_cost": float(recipe.estimated_cost) if recipe.estimated_cost else None,
                        "created_at": recipe.created_at.isoformat() if recipe.created_at else None,
                    },
                    "viewed_at": h.viewed_at.isoformat() if h.viewed_at else None,
                })
        elif h.meal_plan_id:
            plan = plans_map.get(h.meal_plan_id)
            if plan:
                items.append({
                    "id": h.id,
                    "type": "meal_plan",
                    "data": {
                        "id": plan.id,
                        "title": plan.title,
                        "cover_image_url": plan.cover_image_url,
                        "status": plan.status,
                    },
                    "viewed_at": h.viewed_at.isoformat() if h.viewed_at else None,
                })

    return PaginatedResponse(total=total, page=page, page_size=page_size, items=items)


# ---- AI 对话历史 ----
@router.get("/conversations", response_model=PaginatedResponse[AiConversationOut])
def get_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """获取 AI 对话历史列表 —— 按更新时间倒序

    性能优化：原实现 joinedload 拉出每会话的全部消息，只为取首条用户提问
    与最后一条 AI 回复两条摘要——长会话（几十上百条消息）时单页 20 个会话
    要加载上千行。现改为三步批量查询，加载行数与会话长度无关：
      ① 分页取会话（不预加载消息）
      ② 按会话+角色分组聚合 min/max 消息 ID（即首条 user / 末条 assistant）
      ③ 仅按这至多 2×page_size 个 ID 批量取消息内容
    消息 ID 为自增主键、按写入顺序分配，与 created_at 顺序一致，
    故 ID 最小/最大即时间最早/最晚。
    每条会话附带首条用户提问（user_message）与最后一条 AI 回复（ai_reply），
    供前端卡片直接展示气泡与摘要。
    """
    query = db.query(AiConversation).filter(AiConversation.user_id == current_user.id)
    total = query.count()
    convs = (
        query.order_by(AiConversation.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    conv_ids = [c.id for c in convs]
    if conv_ids:
        # ② 每会话分角色的消息 ID 边界：min=首条、max=末条
        role_bounds = {}
        rows = (
            db.query(
                AiMessage.conversation_id,
                AiMessage.role,
                func.min(AiMessage.id),
                func.max(AiMessage.id),
            )
            .filter(AiMessage.conversation_id.in_(conv_ids))
            .group_by(AiMessage.conversation_id, AiMessage.role)
            .all()
        )
        for conv_id, role, min_id, max_id in rows:
            role_bounds[(conv_id, role)] = (min_id, max_id)

        # ③ 只取摘要需要的消息内容：首条 user + 末条 assistant
        wanted_ids = set()
        for conv_id in conv_ids:
            ub = role_bounds.get((conv_id, "user"))
            if ub:
                wanted_ids.add(ub[0])
            ab = role_bounds.get((conv_id, "assistant"))
            if ab:
                wanted_ids.add(ab[1])
        msg_map = {}
        if wanted_ids:
            msg_map = {
                m.id: m
                for m in db.query(AiMessage).filter(AiMessage.id.in_(wanted_ids)).all()
            }

        for c in convs:
            item = AiConversationOut.model_validate(c)
            ub = role_bounds.get((c.id, "user"))
            if ub:
                m = msg_map.get(ub[0])
                if m:
                    item.user_message = m.content
            ab = role_bounds.get((c.id, "assistant"))
            if ab:
                m = msg_map.get(ab[1])
                if m:
                    item.ai_reply = m.content
            items.append(item)

    return PaginatedResponse(
        total=total, page=page, page_size=page_size,
        items=items,
    )


@router.get("/conversations/{conv_id}", response_model=AiConversationDetailOut)
def get_conversation_detail(
    conv_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """获取 AI 对话详情（含所有历史消息）"""
    conv = db.query(AiConversation).filter(
        AiConversation.id == conv_id,
        AiConversation.user_id == current_user.id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    return AiConversationDetailOut.model_validate(conv)
