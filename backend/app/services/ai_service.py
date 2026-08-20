"""
AI 对话引擎 —— LLM 调用、流式对话、对话记忆管理

============================================================================
                    AI 服务架构设计说明（面向答辩）
============================================================================

本系统 AI 服务采用 LangChain 框架，实现以下核心功能：

【对话记忆管理】
  采用"内存字典 + 数据库持久化"双层架构：
  1. 内存层：ConversationBufferMemory 字典（_conversation_memories），
     以 conversation_id 为键，存储活跃会话的对话上下文。
     优势：热数据快速访问，无需每次从 DB 加载。
  2. 持久层：AiConversation / AiMessage 表存储完整历史。
     用户切换会话时，load_memory_from_db() 从 DB 恢复到内存。

  这种设计平衡了性能（活跃会话零 DB 开销）和数据可靠性（历史不丢失）。
  内存中的对话记忆在服务重启后会丢失，但可通过 DB 恢复。

【流式响应设计（Server-Sent Events / SSE）】
  chat_stream() 是一个异步生成器（AsyncGenerator），设计要点：
  1. 使用 llm.astream() 进行流式 LLM 调用，逐 token 返回
  2. 每个 token 通过 yield 发送给 FastAPI StreamingResponse
  3. 前端实时渲染打字机效果，提升用户体验
  4. 流式结束后，将完整对话保存到内存和数据库

【RAG 集成】
  每次对话自动检索相关菜谱/心得作为上下文（可开关 use_rag 参数）。
  流程：用户消息 → RAG 检索 top 5 相似文档 → 拼入 System Prompt → LLM 生成

【系统提示词策略】
  SYSTEM_PROMPT 定义了 AI 的角色、能力、回答风格。
  在 RAG 模式下，检索到的文档内容通过 {context} 占位符注入到提示词中，
  使 AI 能够基于实际菜谱知识进行回答。
"""

import logging
from collections import OrderedDict
from typing import AsyncGenerator, List, Dict

from langchain_openai import ChatOpenAI
from langchain_classic.memory import ConversationBufferMemory
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

from app.config import get_settings
from app.services.rag_service import rag_search

logger = logging.getLogger(__name__)
settings = get_settings()

# 对话内存存储 —— 以 conversation_id 为键，存储活跃对话的上下文
# 设计考量：使用进程内字典而非 Redis，适合单机部署场景，
#         多实例部署时需替换为 Redis/DB 共享存储
# 容量控制：使用 OrderedDict 实现 LRU 策略，超过上限时淘汰最久未活跃的
#         会话（历史仍在数据库，切换会话时会从 DB 重新加载，不丢数据），
#         避免长期运行下无界增长导致内存泄漏
_MAX_ACTIVE_MEMORIES = 256
_conversation_memories: "OrderedDict[int, ConversationBufferMemory]" = OrderedDict()


def _get_or_create_memory(conversation_id: int) -> ConversationBufferMemory:
    """
    获取或创建对话记忆 —— 按会话 ID 隔离上下文。

    ConversationBufferMemory 是 LangChain 的内存实现，
    内部维护 chat_memory 存储 user/assistant 消息对。
    最近只保留 10 轮历史发送给 LLM（在 chat_stream 中截断）。

    LRU 淘汰：命中时移动到队尾；超过 256 个活跃会话时淘汰队首
    （最久未活跃的会话，其历史可随时从数据库恢复）。
    """
    memory = _conversation_memories.get(conversation_id)
    if memory is not None:
        _conversation_memories.move_to_end(conversation_id)
        return memory

    memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True,
    )
    _conversation_memories[conversation_id] = memory
    while len(_conversation_memories) > _MAX_ACTIVE_MEMORIES:
        evicted_id, _ = _conversation_memories.popitem(last=False)
        logger.debug(f"活跃会话内存超过 {_MAX_ACTIVE_MEMORIES}，淘汰会话 {evicted_id}（历史仍在数据库）")
    return memory


def _get_llm():
    """
    获取 LLM 实例（工厂函数）。

    使用 SiliconFlow 的 DeepSeek-R1-0528-Qwen3-8B 模型，
    通过 OpenAI 兼容 API 调用。temperature=0.7 在创造性和稳定性之间取得平衡。
    """
    kwargs = {
        "model": settings.LLM_MODEL,
        "temperature": settings.LLM_TEMPERATURE,
        "max_tokens": settings.LLM_MAX_TOKENS,
    }
    if settings.LLM_API_KEY and settings.LLM_API_KEY != "your-api-key-here":
        kwargs["openai_api_key"] = settings.LLM_API_KEY
    if settings.LLM_BASE_URL:
        kwargs["openai_api_base"] = settings.LLM_BASE_URL

    return ChatOpenAI(**kwargs)


def load_memory_from_db(conversation_id: int, messages: List):
    """
    从数据库加载历史消息到内存 —— 用户切换会话时调用。
    清空现有内存并批量添加历史消息，保证上下文连续。
    """
    memory = _get_or_create_memory(conversation_id)
    memory.chat_memory.clear()
    for msg in messages:
        if msg.role == "user":
            memory.chat_memory.add_user_message(msg.content)
        elif msg.role == "assistant":
            memory.chat_memory.add_ai_message(msg.content)


def clear_memory(conversation_id: int):
    """清除指定会话的内存上下文（不影响数据库记录）"""
    _conversation_memories.pop(conversation_id, None)


# 系统提示词 —— 控制 AI 的角色行为和回答风格
SYSTEM_PROMPT = """你是一个友好的AI烹饪助手，专门为用户提供菜谱推荐、烹饪建议和饮食规划。

你的能力包括：
1. 根据用户的需求推荐合适的菜谱
2. 提供烹饪技巧和食材替代建议
3. 帮助用户规划健康合理的膳食搭配
4. 根据预算推荐经济实惠的菜品组合

回答要求：
- 使用中文回复
- 回答要简洁实用，条理清晰
- 推荐菜谱时说明原因和特点
- 如涉及预算，明确列出每道菜的成本
- 以友好、热情的语气与用户交流

{context}"""


def _build_context_from_rag(search_results: List[Dict]) -> str:
    """将 RAG 检索结果拼装为 LLM context 文本"""
    if not search_results:
        return ""

    parts = ["以下是一些与用户问题相关的菜谱和心得：\n"]
    for i, r in enumerate(search_results, 1):
        parts.append(f"--- 参考资料 {i} ---")
        parts.append(r["content"])
        parts.append("")
    return "\n".join(parts)


async def chat_stream(
    message: str,
    conversation_id: int,
    use_rag: bool = True,
) -> AsyncGenerator[str, None]:
    """
    流式 AI 对话 —— 核心异步生成器。

    执行流程：
      1. 获取 LLM 实例和对话记忆
      2. （可选）RAG 检索相关菜谱/心得
      3. 构建消息列表：[SystemPrompt + 历史消息(最近10轮) + 当前用户消息]
      4. 调用 llm.astream() 流式生成，逐 token yield
      5. 流式结束后，将完整对话保存到 memory

    设计考量：
      - 只保留最近 10 轮历史，避免 context 窗口溢出和 token 浪费
      - RAG 失败不影响主流程，降级为纯 LLM 回答
      - 流式输出时逐字符 yield，前端实现打字机效果
    """
    llm = _get_llm()
    memory = _get_or_create_memory(conversation_id)

    # RAG 检索 —— 从向量库获取相关菜谱/心得作为参考上下文
    context = ""
    if use_rag:
        search_results = rag_search(message, top_k=5)
        context = _build_context_from_rag(search_results)

    # 构建消息列表
    system_prompt = SYSTEM_PROMPT.format(context=context)
    messages = [SystemMessage(content=system_prompt)]

    # 添加历史对话（截断最近10轮，避免 token 浪费）
    history = memory.chat_memory.messages
    messages.extend(history[-10:])

    # 添加当前用户消息
    messages.append(HumanMessage(content=message))

    # 流式输出
    full_response = ""
    try:
        async for chunk in llm.astream(messages):
            if chunk.content:
                full_response += chunk.content
                yield chunk.content
    except Exception as e:
        # 完整异常只写日志；对用户仅返回通用提示，
        # 避免把内部 URL / API Key 片段等信息泄露到前端
        logger.exception(f"LLM 调用失败: {e}")
        error_msg = "抱歉，AI 服务暂时不可用，请稍后重试。"
        yield error_msg
        full_response = error_msg

    # 保存到 memory（用于后续对话上下文）
    memory.chat_memory.add_user_message(message)
    memory.chat_memory.add_ai_message(full_response)