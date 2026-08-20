"""智能推荐

安全设计：
  - 会话创建后立即校验 conv.id 是否生成成功
  - 流式响应生成器内部使用独立 session，避免依赖注入 session 被提前关闭
  - RAG 检索/预算推荐失败均降级到空列表，不阻断主流程
  - AI 对话失败仍返回候选结果，并发送兜底提示消息
  - 非自然语言推荐接口 (/query) 不需要认证，但流式推荐 /stream-recommend 需要登录
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.schemas.ai import AiRecommendRequest
from app.core.deps import get_current_user, get_optional_user
from app.services.recommendation_service import (
    get_personalized_rag_recommendations,
    get_personalized_meal_plans,
    get_personalized_prompts,
    get_budget_recommendations,
    rag_recommend_by_query,
)
from app.services.ai_service import chat_stream
from app.models import AiConversation, AiMessage

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


@router.get("/by-budget")
def recommend_by_budget(
    budget: float = Query(..., gt=0, description="预算金额（元）"),
    meal_type: str = Query(None, description="餐次类型"),
    db: Session = Depends(get_db),
):
    """预算推荐"""
    try:
        results = get_budget_recommendations(budget, db, meal_type)
    except Exception as e:
        logger.exception(f"预算推荐获取失败: {e}")
        results = []
    return {"items": results, "budget": budget, "reason": f"在 {budget} 元预算范围内为您找到 {len(results)} 个选项"}


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


@router.post("/stream-recommend")
async def stream_recommend(
    data: AiRecommendRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """流式智能推荐（SSE）

    性能优化（修复 ERR_ABORTED）：
      - 候选检索（RAG + 预算）移入 event_stream 生成器内部执行，
        避免在返回 StreamingResponse 前长时间阻塞导致客户端/代理超时中断。
      - 生成器首先 yield 一条 keepalive 注释（: keepalive\\n\\n），让客户端立即收到首字节，
        确认连接已建立，避免浏览器 net::ERR_ABORTED。
      - 生成器内部使用独立 SessionLocal，避免依赖注入 session 生命周期问题。

    容错说明：
      - RAG 检索失败：降级到空列表，仍返回 [DONE] 结束流
      - AI 对话失败：仍返回候选菜谱，发送兜底提示后 [DONE]
    安全：
      - 创建会话后立即校验 conv.id 是否生成成功
      - 生成器内部异常捕获，确保 SSE 始终以 [DONE] 结束
    """

    # 拼提示词让 LLM 生成推荐语
    prompt = f"用户需求：{data.query}"
    if data.budget:
        prompt += f"\n预算限制：{data.budget}元以内"
    prompt += "\n\n请根据候选列表给出推荐，推荐中包含具体菜名、成本、推荐理由。"

    # 创建会话并保存用户消息（在返回响应前完成）
    conv = AiConversation(
        user_id=current_user.id,
        title=f"推荐：{data.query[:30]}",
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    # 防御：检查 conv.id 是否成功生成
    if not conv.id:
        db.rollback()
        raise HTTPException(status_code=500, detail="会话创建失败")

    user_msg = AiMessage(
        conversation_id=conv.id,
        role="user",
        content=prompt,
    )
    db.add(user_msg)
    db.commit()

    conversation_id = conv.id
    # 捕获请求参数到闭包，避免在生成器中引用 data 对象
    query = data.query
    budget = data.budget
    meal_type = data.meal_type

    async def event_stream():
        # 1) 立即发送 keepalive 注释 —— 让客户端收到首字节，确认连接已建立
        #    SSE 注释行以冒号开头，客户端会忽略，不影响 data: 协议解析
        yield ": keepalive\n\n"

        # 2) 候选检索（RAG + 预算）—— 移入生成器内执行
        #    使用独立 session，避免 Depends(get_db) 在流式响应期间的生命周期不确定性
        results = []
        sse_db = SessionLocal()
        try:
            try:
                results = rag_recommend_by_query(query, sse_db, budget=budget, top_k=10)
            except Exception as e:
                logger.exception(f"推荐检索失败: {e}")
                results = []

            # 预算约束下补充预算内候选
            if budget:
                try:
                    budget_results = get_budget_recommendations(budget, sse_db, meal_type)
                    # 去重合并：同时按 (type, id) 和 title 去重（修复 D-02）
                    existing_keys = {(r.get("type"), r["id"]) for r in results}
                    existing_titles = {r["title"] for r in results}
                    for br in budget_results:
                        key = (br.get("type"), br["id"])
                        if key not in existing_keys and br["title"] not in existing_titles:
                            results.append(br)
                            existing_keys.add(key)
                            existing_titles.add(br["title"])
                except Exception as e:
                    logger.exception(f"预算推荐获取失败: {e}")
        finally:
            sse_db.close()

        # 3) 下发候选列表
        yield f"data: [CANDIDATES]{json.dumps(results, ensure_ascii=False)}\n\n"

        # 4) 流式推送 AI 推荐语
        full_response = ""
        try:
            async for chunk in chat_stream(prompt, conversation_id, use_rag=False):
                full_response += chunk
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.exception(f"AI 流式对话失败: {e}")
            # AI 对话失败不阻断候选结果返回
            fallback_msg = "（抱歉，AI 服务暂时不可用，以上为基于关键词的推荐结果）"
            full_response += fallback_msg
            yield f"data: {json.dumps(fallback_msg, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

        # 5) 使用独立 session 保存 AI 回复
        if not full_response.strip():
            full_response = "（AI 服务暂不可用）"
        save_db = SessionLocal()
        try:
            ai_msg = AiMessage(
                conversation_id=conversation_id,
                role="assistant",
                content=full_response,
            )
            save_db.add(ai_msg)
            save_db.commit()
        except Exception as e:
            logger.exception(f"保存 AI 回复失败: {e}")
            save_db.rollback()
        finally:
            save_db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲，确保流式即时推送
            "X-Conversation-Id": str(conversation_id),
        },
    )
