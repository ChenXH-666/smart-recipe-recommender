"""智能推荐

安全设计：
  - RAG 检索/预算推荐失败均降级到空列表，不阻断主流程
  - 自然语言推荐接口 (/query) 不需要认证，直接返回候选列表
"""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.ai import AiRecommendRequest
from app.core.deps import get_optional_user
from app.services.recommendation_service import (
    get_personalized_rag_recommendations,
    get_personalized_meal_plans,
    get_personalized_prompts,
    get_budget_recommendations,
    rag_recommend_by_query,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/prompts")
def personalized_prompts(
    limit: int = Query(6, ge=1, le=12),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    """个性化"猜你想问"预设备题 —— 基于用户收藏/浏览历史/点评计算

    - 已登录用户：结合其偏好标签生成个性化提问，再用通用预设备题兜底填充
    - 未登录用户：返回通用预设备题列表
    """
    if current_user is None:
        from app.services.recommendation_service import GENERIC_PROMPTS
        return {"items": GENERIC_PROMPTS[:limit]}
    try:
        prompts = get_personalized_prompts(current_user.id, db, limit)
    except Exception as e:
        logger.exception(f"个性化预设备题获取失败: {e}")
        from app.services.recommendation_service import GENERIC_PROMPTS
        prompts = GENERIC_PROMPTS[:limit]
    return {"items": prompts}


@router.get("/personalized")
def personalized_recommend(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    """个性化推荐（统一 RAG 评估逻辑）— 支持可选认证

    - 已登录用户：基于用户偏好画像（收藏/浏览/点评）做 RAG 语义检索推荐
    - 未登录用户：返回空列表，由前端展示热门推荐作为替代
    """
    if current_user is None:
        return {"items": [], "reason": "登录后可获得个性化推荐"}
    from app.utils.recipe_diet import get_restriction_set
    try:
        results = get_personalized_rag_recommendations(
            current_user.id, db, limit,
            restriction_set=get_restriction_set(current_user),
        )
    except Exception as e:
        logger.exception(f"个性化推荐获取失败: {e}")
        results = []
    return {"items": results, "reason": "根据您的收藏和浏览历史，通过语义评估为您推荐"}


@router.get("/meal-plans")
def personalized_meal_plans(
    limit: int = Query(6, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user=Depends(get_optional_user),
):
    """个性化推荐套餐（统一 RAG 评估逻辑）— 支持可选认证

    - 已登录用户：优先推荐包含用户偏好菜谱的公开套餐（RAG 语义评估）
    - 未登录用户：返回热门公开套餐
    """
    try:
        if current_user is None:
            from app.services.recommendation_service import _get_public_plan_list
            results = _get_public_plan_list(db, limit)
        else:
            results = get_personalized_meal_plans(current_user.id, db, limit)
    except Exception as e:
        logger.exception(f"个性化套餐推荐获取失败: {e}")
        results = []
    return {"items": results}


@router.post("/query")
def recommend_by_query(
    data: AiRecommendRequest,
    db: Session = Depends(get_db),
):
    """自然语言智能推荐

    容错：RAG 检索失败降级到空列表，不阻断响应
    """
    try:
        results = rag_recommend_by_query(data.query, db, budget=data.budget, top_k=10)
    except Exception as e:
        logger.exception(f"RAG 推荐检索失败: {e}")
        results = []

    # 如果有预算约束，同时获取预算结果合并
    if data.budget:
        try:
            budget_results = get_budget_recommendations(data.budget, db, data.meal_type)
            # 去重合并：同时按 (type, id) 和 title 去重
            # - (type, id) 防止同一对象被重复添加（修复 D-02 根因）
            # - title 防止不同对象同名导致用户感知重复
            # 关键修复：原代码仅检查 RAG 结果的标题，添加预算结果后未更新集合，
            # 导致预算结果内部同标题的套餐被重复添加
            existing_keys = {(r.get("type"), r["id"]) for r in results}
            existing_titles = {r["title"] for r in results}
            for br in budget_results:
                key = (br.get("type"), br["id"])
                if key not in existing_keys and br["title"] not in existing_titles:
                    results.append(br)
                    existing_keys.add(key)
                    existing_titles.add(br["title"])
        except Exception as e:
            logger.exception(f"预算推荐合并失败: {e}")

    return {"items": results, "query": data.query, "budget": data.budget}
