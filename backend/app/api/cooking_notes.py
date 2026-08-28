"""烹饪心得

安全设计：
  - 列表/详情使用 joinedload 预加载 user/recipe，避免 N+1 查询
  - 浏览数+1 使用原子 UPDATE 语句，避免并发计数异常
  - 心得评论同样使用 joinedload(CookingNoteComment.user) 优化查询
  - 软删除策略，保护数据完整性
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, update

from app.database import get_db
from app.models import CookingNote, CookingNoteComment
from app.schemas.interaction import (
    CookingNoteCreate,
    CookingNoteUpdate,
    CookingNoteOut,
    CookingNoteCommentCreate,
    CookingNoteCommentOut,
)
from app.schemas.common import PaginatedResponse, SuccessResponse
from app.core.deps import get_current_user, get_optional_user
from app.services.rag_service import sync_cooking_note_to_chroma_by_id, remove_from_chroma

router = APIRouter()


def _enrich_note(note: CookingNote) -> CookingNoteOut:
    """将 ORM 对象转为 API 响应，使用预加载的 user/recipe 关系"""
    item = CookingNoteOut.model_validate(note)
    if note.user:
        item.username = note.user.nickname or note.user.username
        item.author_avatar_url = note.user.avatar_url
    if note.recipe:
        item.related_recipe_title = note.recipe.title
    return item


def _enrich_comment(c: CookingNoteComment) -> CookingNoteCommentOut:
    """将 ORM 评论对象转为 API 响应，使用预加载的 user 关系"""
    item = CookingNoteCommentOut.model_validate(c)
    if c.user:
        item.username = c.user.nickname or c.user.username
        item.user_avatar_url = c.user.avatar_url
    return item


@router.get("", response_model=PaginatedResponse[CookingNoteOut])
def list_notes(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    mine: bool = Query(False, description="仅看自己发布的心得"),
    recipe_id: int = Query(None, ge=1, description="仅看指定菜谱关联的心得"),
    current_user=Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    """心得列表 —— 默认公开；登录后额外展示自己发布的私密心得；支持按作者/菜谱筛选

    性能：joinedload 预加载 user/recipe，避免循环中的 N+1 查询
    """
    query = db.query(CookingNote).options(
        joinedload(CookingNote.user),
        joinedload(CookingNote.recipe),
    ).filter(CookingNote.is_deleted == 0)

    if mine:
        if current_user is None:
            raise HTTPException(status_code=401, detail="请先登录")
        query = query.filter(CookingNote.user_id == current_user.id)
    else:
        # 未登录只看公开；登录后额外可见自己的私密心得
        filters = [CookingNote.is_public == 1]
        if current_user is not None:
            filters.append(CookingNote.user_id == current_user.id)
        query = query.filter(or_(*filters))

    if recipe_id is not None:
        query = query.filter(CookingNote.related_recipe_id == recipe_id)

    total = query.count()
    notes = (
        query.order_by(CookingNote.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [_enrich_note(n) for n in notes]
    return PaginatedResponse(total=total, page=page, page_size=page_size, items=items)


@router.get("/{note_id}", response_model=CookingNoteOut)
def get_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    """获取心得详情 —— 公开心得可见；作者本人也可查看自己的私密心得

    权限规则：
      - 公开心得：所有人可见
      - 私密心得：仅作者可见
      - 软删除：对所有人不可见

    副作用：
      - 浏览数 +1（原子 UPDATE，避免并发计数异常）
    """
    note = (
        db.query(CookingNote)
        .options(
            joinedload(CookingNote.user),
            joinedload(CookingNote.recipe),
        )
        .filter(
            CookingNote.id == note_id,
            CookingNote.is_deleted == 0,
        )
        .first()
    )
    if not note:
        raise HTTPException(status_code=404, detail="心得不存在")

    is_author = current_user is not None and note.user_id == current_user.id
    if not note.is_public and not is_author:
        raise HTTPException(status_code=404, detail="心得不存在")

    # 浏览数 +1：原子 UPDATE，避免并发计数异常
    db.execute(
        update(CookingNote).where(CookingNote.id == note_id).values(
            view_count=CookingNote.view_count + 1
        )
    )
    db.commit()
    db.refresh(note)

    return _enrich_note(note)


@router.post("", response_model=CookingNoteOut, status_code=201)
def create_note(
    data: CookingNoteCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """创建心得"""
    # 校验关联菜谱存在且未删除（如果传了 related_recipe_id）
    if data.related_recipe_id is not None:
        from app.models import Recipe
        recipe = db.query(Recipe).filter(
            Recipe.id == data.related_recipe_id,
            Recipe.is_deleted == 0,
        ).first()
        if not recipe:
            raise HTTPException(status_code=400, detail="关联菜谱不存在")

    note = CookingNote(
        user_id=current_user.id,
        title=data.title,
        content=data.content,
        related_recipe_id=data.related_recipe_id,
        images=data.images,
        is_public=1 if data.is_public else 0,
    )
    db.add(note)
    db.commit()
    db.refresh(note)

    # 仅公开心得入向量库（后台执行，不阻塞创建响应）—— 私密心得内容
    # 不应被 RAG 检索后经由 AI 引用给其他用户
    if note.is_public:
        background_tasks.add_task(sync_cooking_note_to_chroma_by_id, note.id)

    return _enrich_note(note)


@router.put("/{note_id}", response_model=CookingNoteOut)
def update_note(
    note_id: int,
    data: CookingNoteUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """更新心得"""
    note = db.query(CookingNote).filter(
        CookingNote.id == note_id,
        CookingNote.user_id == current_user.id,
        CookingNote.is_deleted == 0,
    ).first()
    if not note:
        raise HTTPException(status_code=404, detail="心得不存在或无权操作")

    # 如果修改了关联菜谱，校验其存在性
    new_recipe_id = data.related_recipe_id
    if new_recipe_id is not None:
        from app.models import Recipe
        recipe = db.query(Recipe).filter(
            Recipe.id == new_recipe_id,
            Recipe.is_deleted == 0,
        ).first()
        if not recipe:
            raise HTTPException(status_code=400, detail="关联菜谱不存在")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(note, key, value)
    db.commit()
    db.refresh(note)

    # 向量库一致性（后台执行，不阻塞更新响应）：公开心得同步更新；
    # 改为私密的立即移除既有分块，防止旧的公开分块仍可被 RAG 检索到
    if note.is_public:
        background_tasks.add_task(sync_cooking_note_to_chroma_by_id, note.id)
    else:
        background_tasks.add_task(remove_from_chroma, "cooking_note", note.id)

    return _enrich_note(note)


@router.delete("/{note_id}", response_model=SuccessResponse)
def delete_note(
    note_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """删除心得（软删除），并从向量库移除分块避免 RAG 检索到已删除内容"""
    note = db.query(CookingNote).filter(
        CookingNote.id == note_id,
        CookingNote.user_id == current_user.id,
        CookingNote.is_deleted == 0,
    ).first()
    if not note:
        raise HTTPException(status_code=404, detail="心得不存在或无权操作")

    note.is_deleted = 1
    db.commit()

    background_tasks.add_task(remove_from_chroma, "cooking_note", note.id)

    return SuccessResponse(message="删除成功")


# ═══════════════════════════════════════════════════════════════════════════
# 心得评论
# ═══════════════════════════════════════════════════════════════════════════


@router.get("/{note_id}/comments", response_model=PaginatedResponse[CookingNoteCommentOut])
def list_comments(
    note_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    """获取心得的评论列表

    权限：
      - 公开心得：所有人可见评论
      - 私密心得：仅作者本人可见评论（与详情页权限一致）

    性能：joinedload 预加载 user，避免循环中的 N+1 查询
    """
    note = db.query(CookingNote).filter(
        CookingNote.id == note_id,
        CookingNote.is_deleted == 0,
    ).first()
    if not note:
        raise HTTPException(status_code=404, detail="心得不存在")
    # 私密心得仅作者本人可查看评论
    is_author = current_user is not None and note.user_id == current_user.id
    if not note.is_public and not is_author:
        raise HTTPException(status_code=404, detail="心得不存在")

    query = db.query(CookingNoteComment).options(
        joinedload(CookingNoteComment.user)
    ).filter(
        CookingNoteComment.note_id == note_id,
        CookingNoteComment.is_deleted == 0,
    )
    total = query.count()
    comments = (
        query.order_by(CookingNoteComment.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = [_enrich_comment(c) for c in comments]
    return PaginatedResponse(total=total, page=page, page_size=page_size, items=items)


@router.post("/{note_id}/comments", response_model=CookingNoteCommentOut, status_code=201)
def create_comment(
    note_id: int,
    data: CookingNoteCommentCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """发表评论

    权限：
      - 公开心得：所有登录用户可评论
      - 私密心得：仅作者本人可评论（与详情页权限一致）
    """
    note = db.query(CookingNote).filter(
        CookingNote.id == note_id,
        CookingNote.is_deleted == 0,
    ).first()
    if not note:
        raise HTTPException(status_code=404, detail="心得不存在")
    # 私密心得仅作者本人可评论
    is_author = note.user_id == current_user.id
    if not note.is_public and not is_author:
        raise HTTPException(status_code=404, detail="心得不存在")

    comment = CookingNoteComment(
        note_id=note_id,
        user_id=current_user.id,
        content=data.content,
    )
    db.add(comment)

    # 评论数 +1：原子 UPDATE
    db.execute(
        update(CookingNote).where(CookingNote.id == note_id).values(
            comment_count=CookingNote.comment_count + 1
        )
    )
    db.commit()
    db.refresh(comment)

    result = CookingNoteCommentOut.model_validate(comment)
    result.username = current_user.nickname or current_user.username
    result.user_avatar_url = current_user.avatar_url
    return result


@router.delete("/comments/{comment_id}", response_model=SuccessResponse)
def delete_comment(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """删除评论（仅评论作者可删）

    安全：使用原子 UPDATE 防止 comment_count 出现负数
    """
    comment = db.query(CookingNoteComment).filter(
        CookingNoteComment.id == comment_id,
        CookingNoteComment.user_id == current_user.id,
        CookingNoteComment.is_deleted == 0,
    ).first()
    if not comment:
        raise HTTPException(status_code=404, detail="评论不存在或无权操作")

    comment.is_deleted = 1
    # 原子 UPDATE 防止并发导致 comment_count 为负
    db.execute(
        update(CookingNote)
        .where(CookingNote.id == comment.note_id, CookingNote.comment_count > 0)
        .values(comment_count=CookingNote.comment_count - 1)
    )
    db.commit()
    return SuccessResponse(message="删除成功")
