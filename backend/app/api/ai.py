"""AI 助手

安全设计：
  - 创建会话后立即校验 conv.id 是否生成成功
  - 流式响应生成器内部使用独立 session，避免依赖注入 session 被提前关闭
  - 生成器内部捕获所有异常，避免 SSE 中断导致前端无 [DONE] 标记
  - AI 回复保存失败不阻断响应（已发送给客户端的内容无法回滚）
"""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models import AiConversation, AiMessage
from app.schemas.ai import AiChatRequest, RewindEditRequest
from app.schemas.common import SuccessResponse
from app.core.deps import get_current_user
from app.services.ai_service import chat_stream, load_memory_from_db, clear_memory
from app.utils.recipe_diet import get_restriction_set

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/chat")
async def ai_chat(
    data: AiChatRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """流式 AI 对话（SSE）

    安全：
      - 创建会话后立即校验 conv.id，避免后续操作使用 None
      - 生成器内部异常捕获，确保 SSE 始终以 [DONE] 结束
    """
    # 创建或获取会话
    conversation_id = data.conversation_id
    if conversation_id:
        conv = db.query(AiConversation).filter(
            AiConversation.id == conversation_id,
            AiConversation.user_id == current_user.id,
        ).first()
        if not conv:
            raise HTTPException(status_code=404, detail="会话不存在")
    else:
        # 创建新会话
        title = data.message[:50] + ("..." if len(data.message) > 50 else "")
        conv = AiConversation(
            user_id=current_user.id,
            title=title,
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)
        # 防御：检查 conv.id 是否成功生成
        if not conv.id:
            db.rollback()
            raise HTTPException(status_code=500, detail="会话创建失败")
        conversation_id = conv.id

    # 从数据库加载历史消息到内存
    messages = db.query(AiMessage).filter(
        AiMessage.conversation_id == conversation_id
    ).order_by(AiMessage.created_at.asc()).all()
    load_memory_from_db(conversation_id, messages)

    # 保存用户消息（在返回响应前完成，此时 session 仍有效）
    user_msg = AiMessage(
        conversation_id=conversation_id,
        role="user",
        content=data.message,
    )
    db.add(user_msg)
    db.commit()

    # 更新会话标题
    if conv.title is None or conv.title.startswith("新对话"):
        conv.title = data.message[:50] + ("..." if len(data.message) > 50 else "")
        db.commit()

    # 流式响应：生成器内部创建独立 session，避免依赖注入 session 被提前关闭
    # 忌口过滤：将当前用户忌口标签传入，供 RAG 候选剔除触忌口的菜谱
    restriction_set = get_restriction_set(current_user)

    async def event_stream():
        full_response = ""
        try:
            async for chunk in chat_stream(
                data.message,
                conversation_id,
                db=db,
                restriction_set=restriction_set,
            ):
                full_response += chunk
                # SSE 格式：对内容做 JSON 编码防止换行破坏协议
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.exception(f"AI 流式对话失败: {e}")
            err_msg = "（AI 服务暂时不可用，请稍后重试）"
            full_response += err_msg
            yield f"data: {json.dumps(err_msg, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

        # 使用独立 session 保存 AI 回复（保存失败不影响已发送给客户端的响应）
        if not full_response.strip():
            full_response = "（AI 未返回有效内容）"
        sse_db = SessionLocal()
        try:
            ai_msg = AiMessage(
                conversation_id=conversation_id,
                role="assistant",
                content=full_response,
            )
            sse_db.add(ai_msg)
            sse_db.commit()
        except Exception as e:
            logger.exception(f"保存 AI 回复失败: {e}")
            sse_db.rollback()
        finally:
            sse_db.close()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Conversation-Id": str(conversation_id),
        },
    )


@router.post("/conversations/{conv_id}/rewind-edit")
def rewind_edit(
    conv_id: int,
    data: RewindEditRequest,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """重答编辑：编辑指定用户消息，删除其后所有消息，并重建该会话的上下文。

    这是"任意位置重新作答"（方案 B，不保留旧分支）：
      - 只允许编辑 user 消息；
      - 保留该条之前的所有消息，删除该条及其后的所有消息；
      - 重建内存上下文到被编辑消息之前，供前端随后重新发送并生成新回答。
    数据库无需新增分支字段，旧后续消息被物理删除，维护成本低。
    """
    conv = db.query(AiConversation).filter(
        AiConversation.id == conv_id,
        AiConversation.user_id == current_user.id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")

    msgs = db.query(AiMessage).filter(
        AiMessage.conversation_id == conv_id
    ).order_by(AiMessage.created_at.asc(), AiMessage.id.asc()).all()

    target = next((m for m in msgs if m.id == data.message_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="消息不存在")
    if target.role != "user":
        raise HTTPException(status_code=400, detail="只能编辑用户消息")

    idx = msgs.index(target)

    # 删除该条及其后的所有消息（旧后续不保留）
    # 用批量 Query.delete（synchronize_session=False），比逐对象 db.delete 更可靠地落库
    ids_to_delete = [m.id for m in msgs[idx:]]
    if ids_to_delete:
        db.query(AiMessage).filter(
            AiMessage.id.in_(ids_to_delete)
        ).delete(synchronize_session=False)
    db.commit()

    # 重建内存上下文到被编辑消息之前
    clear_memory(conv_id)
    kept = msgs[:idx]
    load_memory_from_db(conv_id, kept)

    return {
        "conversation_id": conv_id,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in kept
        ],
    }


@router.delete("/conversations/{conv_id}", response_model=SuccessResponse)
def delete_conversation(
    conv_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """删除对话会话"""
    conv = db.query(AiConversation).filter(
        AiConversation.id == conv_id,
        AiConversation.user_id == current_user.id,
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")

    clear_memory(conv_id)
    db.delete(conv)
    db.commit()
    return SuccessResponse(message="删除成功")
