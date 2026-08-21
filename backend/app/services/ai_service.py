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
from app.services.rag_service import rag_search, build_recipe_pool_context

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
    if settings.LLM_PROVIDER == "mimo":
        # MiMo mimo-v2.5 / mimo-v2.5-pro 默认开启深度思考（返回 reasoning_content 推理链）。
        # 这里自动关闭，只返回最终答案。注意：thinking 是 MiMo 非标准 OpenAI 参数，
        # 必须走 extra_body（用 model_kwargs 会被当成 create() 顶层参数，触发 TypeError）。
        # 该分支仅当 LLM_PROVIDER=mimo 时生效，切换回 SiliconFlow 天然不会误传。
        kwargs["extra_body"] = {"thinking": {"type": "disabled"}}

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
# ⚠ 缓存友好设计：此提示词必须保持【完全静态、逐字节一致】，不得插入任何
#   动态内容（时间、随机文本、RAG 上下文等）。动态内容一律放到请求末尾的
#   用户消息里，从而保证本段成为稳定前缀，最大化 LLM 提供商的提示词缓存命中率，
#   降低单轮对话的输入成本。
SYSTEM_PROMPT = """你是"食慧家"智能菜谱推荐助手，只推荐系统菜谱库中真实存在的菜谱，为用户提供菜谱推荐、烹饪建议、预算规划和膳食搭配。

【强制性规则 —— 必须逐条遵守】
1. 只能推荐"参考资料"中出现的菜谱，严禁编造或推荐参考资料之外的菜名。
2. 每一道菜的食材、做法、预估成本必须严格依据参考资料标注的内容，
   不得自行改写用料、杜撰价格或篡改做法。
3. 回答中出现的任何菜名、食材、价格、步骤，都必须能在参考资料中找到对应依据。
4. 若参考资料不足、检索不到相关菜谱、或无法满足用户需求时，
   如实说明"当前菜谱库中没有符合条件的菜品"，绝不硬凑或虚构。
5. 涉及预算时，只按参考资料的"预估成本"逐道累计，给出总价并提示是否在预算内；
   不要自己估算没有依据的菜价。在不超过预算的前提下，应尽量"用足预算"：
   通常应使总价达到预算的约 90%~100%，办法是增加菜品数量或选择库内成本更高的
   合理搭配来让菜单更丰盛，避免出现"预算很大却只用了很少"的空泛组合；
   若确实无法逼近预算，应在总价旁说明原因。

【能力】
- 根据用户需求推荐合适的菜谱
- 提供烹饪技巧和食材替代建议
- 帮助用户规划健康合理的膳食搭配
- 根据预算推荐经济实惠的菜品组合

【回答要求】
- 使用中文回复
- 回答要简洁实用，条理清晰
- 推荐菜谱时说明原因和特点
- 以友好、热情的语气与用户交流"""


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


# 判断用户是否在为"他人"做菜 —— 此时不应硬性按用户本人忌口拦截
# 启发式匹配，覆盖常见表达；命中说明意图是为别人下厨/请客/招待。
_FOR_OTHERS_PATTERNS = [
    "给别人", "给朋友", "为朋友", "给同事", "做给",
    "给父母", "给爸妈", "给老人", "给长辈",
    "给小孩", "给孩子", "给小朋友",
    "给爷爷奶奶", "请客", "招待", "宴请",
    "客人", "朋友来做", "来家里吃饭", "来家里做客",
]


def _is_cooking_for_others(message: str) -> bool:
    """粗略判断用户是否在为他人做菜（命中任一模式即视为是）"""
    m = message or ""
    return any(p in m for p in _FOR_OTHERS_PATTERNS)


async def chat_stream(
    message: str,
    conversation_id: int,
    use_rag: bool = True,
    db=None,
    restriction_set=None,
) -> AsyncGenerator[str, None]:
    """
    流式 AI 对话 —— 核心异步生成器。

    执行流程：
      1. 获取 LLM 实例和对话记忆
      2. （可选）RAG 检索相关菜谱，按菜谱去重 + 剔除用户忌口后构建候选池上下文
      3. 构建消息列表：[SystemPrompt(静态前缀) + 历史消息(最近10轮) + 当前用户消息(含上下文尾部)]
      4. 调用 llm.astream() 流式生成，逐 token yield
      5. 流式结束后，将完整对话保存到 memory

    设计考量：
      - 只保留最近 10 轮历史，避免 context 窗口溢出和 token 浪费
      - 系统提示词保持静态稳定前缀以便提示词缓存命中；动态内容放用户消息尾部
      - RAG 失败不影响主流程，降级为纯 LLM 回答
      - restriction_set：当前用户忌口标签集合，RAG 候选会先被程序剔除触忌口的菜谱
      - db：用于加载候选菜谱与忌口过滤；为空时退回旧的分块拼接逻辑
      - 流式输出时逐字符 yield，前端实现打字机效果
    """
    llm = _get_llm()
    memory = _get_or_create_memory(conversation_id)

    # RAG 检索 —— 召回较多候选，按菜谱去重并剔除用户忌口后，输出紧凑候选池
    # 若用户在为他人做菜（消息命中"给…/请客/招待"等表达），不硬性拦截其本人忌口
    context = ""
    if use_rag and db is not None:
        context = build_recipe_pool_context(
            db,
            message,
            restriction_set=restriction_set,
            relax_restriction=_is_cooking_for_others(message),
        )
    elif use_rag:
        # 兜底：无 db 时退回旧的分块拼接（仅测试/异常场景）
        search_results = rag_search(message, top_k=settings.RAG_TOP_K * 2)
        context = _build_context_from_rag(search_results)

    # 构建消息列表 —— 缓存友好顺序：
    #   系统提示词（完全静态、稳定前缀）→ 历史 → 动态内容（RAG 上下文 + 用户问题）
    #   动态内容全部放末尾，保证稳定前缀逐字节一致，最大化提示词缓存命中率
    messages = [SystemMessage(content=SYSTEM_PROMPT)]

    # 添加历史对话（截断最近10轮，避免 token 浪费）
    history = memory.chat_memory.messages
    messages.extend(history[-10:])

    # 当前用户消息；RAG 上下文并入用户消息尾部（若检索到结果）
    user_content = message
    if context:
        user_content = (
            "参考资料（菜谱库检索结果，请只基于这些资料推荐，"
            "食材、做法、价格均以此为准，不要在资料之外编造菜品）：\n\n"
            f"{context}\n\n"
            f"用户问题：{message}"
        )
    messages.append(HumanMessage(content=user_content))

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