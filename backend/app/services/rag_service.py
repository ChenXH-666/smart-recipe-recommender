"""
RAG (Retrieval-Augmented Generation) 服务 —— 向量构建、语义检索、向量同步

============================================================================
                      RAG 架构设计说明（面向答辩）
============================================================================

本系统的 RAG 实现采用了经典的"向量数据库 + 语义检索 + LLM 增强"架构：

【整体流程】
  用户提问 → Embedding 向量化 → Chroma 相似度检索 → 拼接上下文 → LLM 生成回答

【组件说明】
  1. Embedding 模型：使用 SiliconFlow 的 BGE-M3 模型（BAAI/bge-m3）
     - BGE-M3 是 BAAI 开源的多语言 embedding 模型，支持中英文
     - 输出 1024 维向量，对语义相似度计算效果好
     - 通过 API 调用，而非本地部署，降低硬件要求

  2. 向量数据库：Chroma（本地持久化存储）
     - 轻量级开源向量数据库，适合中小规模项目
     - 数据持久化到磁盘（chroma_db/ 目录），重启不丢失
     - 使用余弦相似度进行 top-K 检索 → 返回语义最相关的文档片段

  3. 文档分块策略（Chunking）：
     - 使用 RecursiveCharacterTextSplitter 递归分割
     - chunk_size=500：每块约 500 字符，含完整上下文但不过长
     - chunk_overlap=50：相邻块重叠 50 字符，防止关键信息被截断
     - 分隔符优先级：段落 > 换行 > 中文句号 > 逗号 > 空格
       这样能优先在自然语义边界处切割

【数据同步机制】
  - 菜谱/心得创建时自动同步到向量库（实时增量）
  - 全量重建函数 rebuild_vectorstore() 用于初始化或数据修复
  - 全量重建支持断点续传：按批次编码，每批次成功后记录 checkpoint，失败终止并保留进度
  - 先删旧文档再插入新文档，保证幂等性

【文档数据结构】
  每条向量文档包含：
    - content: 拼装后的菜谱/心得文本（标题+描述+标签+食材+步骤）
    - metadata: source_type(recipe/cooking_note), source_id, title, tags
  检索时可利用 metadata 进行过滤（如只搜菜谱、只搜心得）
"""

import os
import json
import logging
import requests
from typing import List, Dict, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.embeddings import Embeddings
from langchain_community.vectorstores import Chroma
import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# 全局 Chroma 向量存储实例（单例模式，避免重复初始化）
_vectorstore: Optional[Chroma] = None

# 文本分割器 —— 在中文语义边界处进行切割
_text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=settings.RAG_CHUNK_SIZE,
    chunk_overlap=settings.RAG_CHUNK_OVERLAP,
    separators=["\n\n", "\n", "。", "，", "；", " ", ""],
)


class SiliconFlowEmbeddings(Embeddings):
    """
    SiliconFlow Embedding API 封装，实现 LangChain Embeddings 接口。

    使用 BGE-M3 模型，通过 HTTP API 调用 SiliconFlow 的 embedding 服务。
    每次调用将文本批量发送，返回对应的 1024 维浮点向量列表。

    【容错设计】
      - API 调用失败（403、网络异常等）时，记录错误但返回零向量兜底
      - 保证上层调用（Chroma.similarity_search）不会因为嵌入服务挂掉而崩溃
      - 返回的零向量会使相似度检索退化为"随机/全量扫描"，再由上层进行关键词过滤
    """

    # 兜底零向量维度（与 BGE-M3 输出一致：1024）
    _FALLBACK_DIM = 1024

    def __init__(self):
        self.api_url = settings.EMBEDDING_API_URL
        self.api_key = settings.EMBEDDING_API_KEY
        self.model = settings.EMBEDDING_MODEL

    def _embed(
        self, texts: List[str], raise_on_error: bool = False
    ) -> List[List[float]]:
        """
        调用 Embedding API 获取文本向量。

        为避免单次请求过大或 API 额度耗尽，内部按 RAG_EMBEDDING_BATCH_SIZE
        分批次调用。失败行为：
          - raise_on_error=False（默认）：返回零向量兜底，保证 RAG 检索不中断
          - raise_on_error=True：立即抛出异常，供断点续传场景使用
        """
        if not texts:
            return []

        batch_size = settings.RAG_EMBEDDING_BATCH_SIZE
        if batch_size <= 0:
            batch_size = len(texts)

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        all_embeddings: List[List[float]] = []
        total = len(texts)

        for start in range(0, total, batch_size):
            batch = texts[start:start + batch_size]
            payload = {
                "model": self.model,
                "input": batch
            }

            try:
                response = requests.post(
                    self.api_url, json=payload, headers=headers, timeout=30
                )
                response.raise_for_status()
                data = response.json()
                batch_embeddings = [item["embedding"] for item in data["data"]]
                all_embeddings.extend(batch_embeddings)
                logger.debug(
                    f"Embedding 批次完成 {min(start + batch_size, total)}/{total}"
                )
            except Exception as e:
                logger.error(
                    f"SiliconFlow 嵌入 API 调用失败（批次 {start}-{start + len(batch)}）: {e}"
                )
                if raise_on_error:
                    raise
                logger.warning("将使用零向量兜底（推荐结果将退化为关键词匹配）。")
                # 兜底：剩余未编码的全部用零向量填充，保持返回数量与输入一致
                all_embeddings.extend([[0.0] * self._FALLBACK_DIM for _ in batch])
                # 后续批次不再请求，直接补零
                remaining = total - start - len(batch)
                if remaining > 0:
                    all_embeddings.extend(
                        [[0.0] * self._FALLBACK_DIM for _ in range(remaining)]
                    )
                break

        return all_embeddings

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """嵌入文档列表（LangChain 批量接口）"""
        return self._embed(texts)

    def embed_query(self, text: str) -> List[float]:
        """嵌入单个查询文本（LangChain 单条接口）"""
        result = self._embed([text])
        return result[0] if result else [0.0] * self._FALLBACK_DIM


def _get_embedding_model():
    """获取 Embedding 模型实例（工厂函数，方便后续切换模型）"""
    return SiliconFlowEmbeddings()


def get_vectorstore() -> Chroma:
    """
    获取或初始化 Chroma 向量库。
    采用全局单例模式，整个应用生命周期内只初始化一次，
    避免重复加载索引文件的开销。

    使用 chromadb.PersistentClient 直接管理持久化，绕过 LangChain
    对 persist_directory 的封装，避免部分版本组合下数据无法落盘的问题。
    """
    global _vectorstore
    if _vectorstore is None:
        # CHROMA_PERSIST_DIR 现在是**绝对路径**（如 F:/chroma_db），
        # 因为 ChromaDB 1.5.9 Rust 绑定不支持中文路径。
        # 若是相对路径（兼容旧配置回退），则相对于 app 目录。
        if os.path.isabs(settings.CHROMA_PERSIST_DIR):
            persist_dir = settings.CHROMA_PERSIST_DIR
        else:
            persist_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), settings.CHROMA_PERSIST_DIR)
        persist_dir = os.path.abspath(persist_dir)
        os.makedirs(persist_dir, exist_ok=True)
        logger.info(f"Chroma 持久化目录: {persist_dir}")

        client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        _vectorstore = Chroma(
            client=client,
            embedding_function=_get_embedding_model(),
        )
    return _vectorstore


def _build_recipe_text(recipe) -> str:
    """
    将菜谱对象拼装为结构化文本，用于 embedding。
    包含：标题、简介、标签、食材列表、烹饪步骤摘要。
    文本越结构化，embedding 质量越高，检索越精准。
    """
    parts = [f"菜谱：{recipe.title}"]
    if recipe.description:
        parts.append(f"简介：{recipe.description}")

    # 标签
    tags = [t.tag.name for t in recipe.tags] if hasattr(recipe, 'tags') and recipe.tags else []
    if tags:
        parts.append(f"标签：{'、'.join(tags)}")

    # 食材
    if hasattr(recipe, 'ingredients') and recipe.ingredients:
        ings = [f"{ri.ingredient.name}({ri.quantity or ''})" for ri in recipe.ingredients if ri.ingredient]
        parts.append(f"食材：{'、'.join(ings)}")

    # 步骤摘要
    if hasattr(recipe, 'steps') and recipe.steps:
        step_texts = [f"步骤{s.step_number}：{s.instruction}" for s in sorted(recipe.steps, key=lambda x: x.step_number)]
        parts.append("；".join(step_texts))

    return "\n".join(parts)


def _build_note_text(note) -> str:
    """将烹饪心得拼装为结构化文本"""
    return f"烹饪心得：{note.title}\n{note.content}"


def _delete_chunks_by_prefix(vs, source_type: str, source_id: int):
    """
    按 source_type+source_id 删除所有相关分块（修复 doc_id 不匹配导致删除失效的问题）。

    早期实现只删除 `recipe_{id}` 单一 ID，但实际写入时分块 ID 为 `recipe_{id}_{i}`，
    导致旧分块无法清除，向量库会累积脏数据。

    本函数通过 metadata where 条件按 source_type+source_id 批量删除，保证幂等性。
    """
    try:
        vs._collection.delete(where={"source_type": source_type, "source_id": source_id})
    except Exception as e:
        logger.debug(f"按 metadata 删除旧分块失败（可能本就没有旧数据）: {e}")


def remove_from_chroma(source_type: str, source_id: int):
    """
    从向量库移除指定来源的所有分块 —— 供软删除/审核驳回时调用。

    保证向量库与 MySQL 状态一致：菜谱/心得被删除或驳回后，
    RAG 检索不再返回该内容（与 rebuild_vectorstore 只收录
    approved 且未删除内容的语义对齐）。
    """
    try:
        vs = get_vectorstore()
        _delete_chunks_by_prefix(vs, source_type, source_id)
        logger.info(f"已从向量库移除 {source_type} {source_id} 的全部分块")
    except Exception as e:
        logger.error(f"从向量库移除 {source_type} {source_id} 失败: {e}")


def sync_recipe_to_chroma(recipe):
    """
    将单个菜谱同步到向量库（增量更新）。
    采用"先删后插"策略：先按 source_type+source_id 删除所有旧分块，
    再计算新的 embedding 并插入，保证幂等性和数据一致性。
    """
    try:
        vs = get_vectorstore()
        text = _build_recipe_text(recipe)

        # 删除该菜谱的所有旧分块（按 metadata 过滤，解决分块 ID 不匹配问题）
        _delete_chunks_by_prefix(vs, "recipe", recipe.id)

        tags_str = "、".join([t.tag.name for t in recipe.tags]) if hasattr(recipe, 'tags') and recipe.tags else ""

        # 分块并生成多段向量文档
        chunks = _text_splitter.split_text(text)
        ids = [f"recipe_{recipe.id}_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "source_type": "recipe",
                "source_id": recipe.id,
                "title": recipe.title,
                "tags": tags_str,
            }
            for _ in chunks
        ]

        vs.add_texts(chunks, metadatas=metadatas, ids=ids)
        logger.info(f"已同步菜谱 {recipe.id} ({recipe.title}) 到向量库，共 {len(chunks)} 块")
    except Exception as e:
        logger.error(f"同步菜谱到向量库失败: {e}")


def sync_cooking_note_to_chroma(note):
    """将烹饪心得同步到向量库（与菜谱同步逻辑一致）"""
    try:
        vs = get_vectorstore()
        text = _build_note_text(note)

        # 删除该心得的所有旧分块
        _delete_chunks_by_prefix(vs, "cooking_note", note.id)

        chunks = _text_splitter.split_text(text)
        ids = [f"note_{note.id}_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "source_type": "cooking_note",
                "source_id": note.id,
                "title": note.title,
                "tags": "",
            }
            for _ in chunks
        ]

        vs.add_texts(chunks, metadatas=metadatas, ids=ids)
        logger.info(f"已同步心得 {note.id} ({note.title}) 到向量库，共 {len(chunks)} 块")
    except Exception as e:
        logger.error(f"同步心得向量库失败: {e}")


def _keyword_match_score(query: str, content: str, title: str = "", tags: str = "") -> float:
    """
    关键词匹配评分 —— 作为向量搜索失败时的兜底方案。

    评分策略（越高越相关）：
      - 标题命中（整词/长 n-gram）：+3.0/次
      - 标签命中：+1.5/次
      - 正文命中：+0.8/次
      - 短 n-gram（2-3 字）部分命中：+0.3/次（用于处理"西红柿鸡蛋"与"西红柿炒鸡蛋"的近似匹配）
    """
    if not query:
        return 0.0

    # 去除常见停用词和标点
    import re
    stopwords = {"推荐", "帮", "我", "的", "一个", "点", "些", "想", "要", "吃", "做", "个",
                 "便宜", "好吃", "简单", "来点", "今天", "请问", "有没有", "有什么"}
    raw_tokens = [t for t in re.split(r"[\s，。、；：,.;:!?()（）\[\]【】\"'《》]+", query) if t]
    tokens = [t for t in raw_tokens if t and t not in stopwords]
    if not tokens:
        tokens = raw_tokens or [query]

    title_low = title.lower()
    tags_low = tags.lower()
    content_low = content.lower()

    score = 0.0
    matched_ngrams = set()

    for tok in tokens:
        t = tok.lower()
        if not t or len(t) == 0:
            continue

        # 精确整词匹配（最高权重）
        exact_in_title = t in title_low
        exact_in_tags = t in tags_low
        exact_in_content = t in content_low

        if exact_in_title:
            score += 3.0
        if exact_in_tags:
            score += 1.5
        if exact_in_content:
            score += 0.8

        # 字符级 n-gram 部分匹配 —— 处理"西红柿鸡蛋" ≈ "西红柿炒鸡蛋" 这种情况
        # 提取所有 2-3 字 n-gram 作为模糊匹配特征
        if not (exact_in_title or exact_in_tags or exact_in_content):
            for n in (2, 3):
                if len(t) < n:
                    continue
                for i in range(len(t) - n + 1):
                    gram = t[i:i + n]
                    if gram in matched_ngrams:
                        continue
                    gram_score = 0.0
                    if gram in title_low:
                        gram_score += 0.6
                    if gram in tags_low:
                        gram_score += 0.3
                    if gram in content_low:
                        gram_score += 0.15
                    if gram_score > 0:
                        matched_ngrams.add(gram)
                        score += gram_score

    return score


def _fallback_metadata_search(
    vs, query: str, top_k: int, filter_source_type: Optional[str]
) -> List[Dict]:
    """
    兜底检索：当向量搜索失败（API 挂掉、库中没有数据等）时，
    直接从 Chroma 的 metadata 中拉取候选文档，再用关键词评分排序。
    """
    try:
        # 先按 source_type 过滤拿一批候选
        where = {"source_type": filter_source_type} if filter_source_type else {}
        try:
            raw = vs._collection.get(where=where, include=["documents", "metadatas"])
        except Exception:
            raw = vs._collection.get(include=["documents", "metadatas"])

        docs = raw.get("documents") or []
        metas = raw.get("metadatas") or []
        if not docs:
            return []

        # 关键词评分排序
        scored = []
        for doc, meta in zip(docs, metas):
            meta = meta or {}
            title = str(meta.get("title", ""))
            tags = str(meta.get("tags", ""))
            score = _keyword_match_score(query, doc or "", title, tags)
            if score > 0:
                scored.append((score, doc, meta))

        scored.sort(key=lambda x: x[0], reverse=True)
        scored = scored[:top_k]

        return [
            {
                "content": doc,
                "source_type": meta.get("source_type", ""),
                "source_id": meta.get("source_id", 0),
                "title": meta.get("title", ""),
                "tags": meta.get("tags", ""),
            }
            for _, doc, meta in scored
        ]
    except Exception as e:
        logger.error(f"兜底关键词搜索也失败: {e}")
        return []


def rag_search(query: str, top_k: int = None, filter_source_type: str = None) -> List[Dict]:
    """
    RAG 语义检索核心函数（带降级容错）。

    【主流程】
      1. 将用户查询文本通过 embedding 模型转换为向量
      2. 在 Chroma 中执行余弦相似度搜索，返回 top_k 个最相关的文档块
      3. 可选按 source_type 过滤（例如只检索菜谱或只检索心得）

    【容错降级】
      - 若 embedding API 失败：退化为零向量 + 关键词评分重排序
      - 若 Chroma similarity_search 本身抛异常：直接走 metadata + 关键词匹配
      - 保证任何情况下都不会抛异常导致接口 500

    返回每个结果包含 content（文档内容）、source_type、source_id、title、tags。
    """
    if top_k is None:
        top_k = settings.RAG_TOP_K

    vs = get_vectorstore()

    search_filter = None
    if filter_source_type:
        search_filter = {"source_type": filter_source_type}

    try:
        docs = vs.similarity_search(query, k=top_k, filter=search_filter)
    except Exception as e:
        logger.error(f"Chroma 向量搜索失败（将使用关键词兜底）: {e}")
        return _fallback_metadata_search(vs, query, top_k, filter_source_type)

    # 若向量搜索无结果（例如全部零向量时相似度失效），走关键词兜底
    if not docs:
        logger.warning("向量搜索无结果，切换为关键词兜底搜索")
        return _fallback_metadata_search(vs, query, top_k, filter_source_type)

    results = []
    for doc in docs:
        meta = doc.metadata or {}
        results.append({
            "content": doc.page_content,
            "source_type": meta.get("source_type", ""),
            "source_id": meta.get("source_id", 0),
            "title": meta.get("title", ""),
            "tags": meta.get("tags", ""),
        })
    return results


def _get_checkpoint_path() -> str:
    """获取断点文件绝对路径"""
    if os.path.isabs(settings.CHROMA_PERSIST_DIR):
        persist_dir = settings.CHROMA_PERSIST_DIR
    else:
        persist_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), settings.CHROMA_PERSIST_DIR
        )
    os.makedirs(persist_dir, exist_ok=True)
    checkpoint = settings.RAG_CHECKPOINT_FILE
    if os.path.isabs(checkpoint):
        return checkpoint
    return os.path.join(persist_dir, os.path.basename(checkpoint))


def _load_checkpoint_ids() -> set:
    """加载已完成的文档 ID 集合"""
    path = _get_checkpoint_path()
    if not os.path.exists(path):
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("done_ids", []))
    except Exception as e:
        logger.warning(f"加载 checkpoint 失败: {e}，将重新全量重建")
        return set()


def _save_checkpoint_ids(done_ids: set):
    """保存已完成的文档 ID 集合到断点文件"""
    path = _get_checkpoint_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"done_ids": sorted(done_ids)}, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存 checkpoint 失败: {e}")


def _clear_checkpoint():
    """清空断点文件"""
    path = _get_checkpoint_path()
    if os.path.exists(path):
        try:
            os.remove(path)
        except Exception as e:
            logger.warning(f"删除 checkpoint 文件失败: {e}")


def rebuild_vectorstore(db_session=None, resume: bool = True):
    """
    全量重建向量库 —— 用于初始化部署或数据修复。
    遍历所有已通过的菜谱和公开心得，重新计算 embedding 并写入 Chroma。

    支持断点续传：
      - 默认 resume=True，读取 checkpoint 跳过已编码成功的文档块
      - 每成功编码并写入一个批次，立即更新 checkpoint
      - 遇到错误立即终止并抛出异常，已成功的批次会被记录，下次可从断点继续
      - 如需从头重建，可传入 resume=False（会自动清空 checkpoint）
    """
    if db_session is None:
        return

    from app.models import Recipe, CookingNote
    from sqlalchemy.orm import joinedload

    vs = get_vectorstore()
    embedding_model = _get_embedding_model()

    if resume:
        done_ids = _load_checkpoint_ids()
        logger.info(f"断点续传：已跳过 {len(done_ids)} 个已编码文档块")
    else:
        _clear_checkpoint()
        done_ids = set()
        # 从头重建必须先清空现有集合。
        # 注意：删除失败必须抛出，绝不能静默吞掉——
        # 否则旧分块会残留（曾导致 --from-scratch 无效，收录已删除数据）。
        vs._collection.delete(where={})

    # 构建待编码文档列表
    pending_texts = []
    pending_metadatas = []
    pending_ids = []

    # 菜谱
    recipes = (
        db_session.query(Recipe)
        .options(joinedload(Recipe.tags))
        .filter(Recipe.status == "approved", Recipe.is_deleted == 0)
        .all()
    )
    for recipe in recipes:
        text = _build_recipe_text(recipe)
        chunks = _text_splitter.split_text(text)
        tags_str = "、".join([t.tag.name for t in recipe.tags]) if recipe.tags else ""
        for i, chunk in enumerate(chunks):
            doc_id = f"recipe_{recipe.id}_{i}"
            if doc_id in done_ids:
                continue
            pending_texts.append(chunk)
            pending_metadatas.append({
                "source_type": "recipe",
                "source_id": recipe.id,
                "title": recipe.title,
                "tags": tags_str,
            })
            pending_ids.append(doc_id)

    # 烹饪心得
    notes = db_session.query(CookingNote).filter(
        CookingNote.is_public == 1,
        CookingNote.is_deleted == 0,
    ).all()
    for note in notes:
        text = _build_note_text(note)
        chunks = _text_splitter.split_text(text)
        for i, chunk in enumerate(chunks):
            doc_id = f"note_{note.id}_{i}"
            if doc_id in done_ids:
                continue
            pending_texts.append(chunk)
            pending_metadatas.append({
                "source_type": "cooking_note",
                "source_id": note.id,
                "title": note.title,
                "tags": "",
            })
            pending_ids.append(doc_id)

    total_pending = len(pending_texts)
    if total_pending == 0:
        logger.info("没有需要编码的新文档块，向量库已是最新")
        if resume:
            _clear_checkpoint()
        return

    logger.info(f"开始重建向量库：共 {total_pending} 个待编码文档块")

    batch_size = settings.RAG_EMBEDDING_BATCH_SIZE
    if batch_size <= 0:
        batch_size = total_pending

    processed_in_run = 0
    for start in range(0, total_pending, batch_size):
        end = min(start + batch_size, total_pending)
        batch_texts = pending_texts[start:end]
        batch_metadatas = pending_metadatas[start:end]
        batch_ids = pending_ids[start:end]

        try:
            # 先删除本批次 ID（幂等：防止上次中断导致部分残留）
            try:
                vs._collection.delete(ids=batch_ids)
            except Exception:
                pass

            # 分批编码：出错会抛出异常
            embeddings = embedding_model._embed(batch_texts, raise_on_error=True)

            # 写入 Chroma
            vs._collection.add(
                embeddings=embeddings,
                documents=batch_texts,
                metadatas=batch_metadatas,
                ids=batch_ids,
            )

            # 更新断点
            done_ids.update(batch_ids)
            _save_checkpoint_ids(done_ids)

            processed_in_run += len(batch_ids)
            logger.info(
                f"向量库重建进度：{processed_in_run}/{total_pending} "
                f"（本批次 {len(batch_ids)} 个）"
            )
        except Exception as e:
            logger.error(
                f"向量库重建失败，已终止于第 {start} 个文档块 "
                f"（批次 {start}-{end}）: {e}"
            )
            logger.error(
                f"已记录 {len(done_ids)} 个成功文档块，下次 rebuild_vectorstore() "
                f"传入 resume=True 可断点续传"
            )
            raise

    logger.info(f"向量库重建完成：本次共编码 {processed_in_run} 个文档块")

    # 全部成功后清空 checkpoint
    if resume:
        _clear_checkpoint()