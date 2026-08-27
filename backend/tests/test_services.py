# -*- coding: utf-8 -*-
"""服务层单元测试 —— RAG 候选池（预算解析/去重/忌口）与 AI 对话引擎。

外部依赖处理：
  - rag_service.rag_search / _get_popular_recipe_ids → monkeypatch 成可控假数据
  - ai_service._get_llm → monkeypatch 成返回固定分块的假 LLM
    保证测试不触碰真实 Chroma / SiliconFlow / MySQL。
"""
import asyncio
from collections import OrderedDict
from types import SimpleNamespace

import pytest

import app.services.rag_service as rag
import app.services.ai_service as ai
from app.models import Recipe


# ---------------------------------- 预算解析 ----------------------------------

class TestExtractBudget:
    @pytest.mark.parametrize("text,expected", [
        ("预算约500元", 500),
        ("预算为1000元", 1000),
        ("500元左右", 500),
        ("大概300块以内", 300),
        ("预算1元", 1),
    ])
    def test_valid_budgets(self, text, expected):
        assert rag._extract_budget(text) == expected

    @pytest.mark.parametrize("text", ["随便吃点", "预算0元", "预算999999", None, ""])
    def test_no_budget(self, text):
        assert rag._extract_budget(text) is None


# ------------------------- RAG 候选池：去重 / 排序 / 忌口 -------------------------

@pytest.fixture()
def _patch_retrieval(monkeypatch):
    """屏蔽真实检索与精排：默认空召回、空兜底、精排降级（返回 None）。"""
    monkeypatch.setattr(rag, "rag_search", lambda *a, **k: [])
    monkeypatch.setattr(rag, "_get_popular_recipe_ids", lambda *a, **k: [])
    monkeypatch.setattr(rag, "_rerank_pool_scores", lambda *a, **k: None)


def _recipe(db, title, cost=None, tags=None, ings=None):
    r = Recipe(title=title, status="approved", estimated_cost=cost)
    db.add(r)
    db.flush()
    return r


def _title_index(body, title):
    return body.find(f"菜：{title}") if f"菜：{title}" in body else body.index(title)


class TestRecipePoolContext:
    def test_dedup_recalled_duplicates(self, db_session, _patch_retrieval, monkeypatch):
        r1 = _recipe(db_session, "西红柿炒蛋", cost=12)
        r2 = _recipe(db_session, "红烧鱼", cost=30)
        # 召回含重复 source_id，验证按菜谱去重
        monkeypatch.setattr(rag, "rag_search",
                            lambda *a, **k: [{"source_id": r1.id}, {"source_id": r1.id},
                                             {"source_id": r2.id}])
        body = rag.build_recipe_pool_context(db_session, "随便", restriction_set=set())
        assert "菜1｜西红柿炒蛋" in body
        # 去重后每道菜只出现一次
        assert body.count("西红柿炒蛋") == 1
        assert body.count("红烧鱼") == 1

    def test_empty_recall_returns_empty(self, db_session, _patch_retrieval):
        assert rag.build_recipe_pool_context(db_session, "没有结果") == ""

    def test_budget_ordering_in_budget_first_asc(self, db_session, _patch_retrieval, monkeypatch):
        over = _recipe(db_session, "昂贵菜", cost=150)
        cheap = _recipe(db_session, "经济菜", cost=20)
        expen = _recipe(db_session, "中档菜", cost=80)
        # 召回顺序打乱：昂贵、经济、中档
        monkeypatch.setattr(rag, "rag_search",
                            lambda *a, **k: [{"source_id": over.id}, {"source_id": cheap.id},
                                             {"source_id": expen.id}])
        body = rag.build_recipe_pool_context(db_session, "预算约100元", restriction_set=set())
        # 预算内(≤100)升序：经济(20) < 中档(80)；超预算(150)排后
        assert body.index("经济菜") < body.index("中档菜") < body.index("昂贵菜")
        # 动态预算提示：用足预算目标区间
        assert "90~100 元" in body

    def test_relax_restriction_notes_for_others(self, db_session, _patch_retrieval, monkeypatch):
        _recipe(db_session, "海鲜大餐", cost=60)
        monkeypatch.setattr(rag, "rag_search",
                            lambda *a, **k: [{"source_id": 1}])
        body = rag.build_recipe_pool_context(
            db_session, "请客吃饭", restriction_set={"seafood"}, relax_restriction=True,
        )
        assert "为他人做菜" in body
        assert "不强制规避" in body


# ------------------------- Rerank 精排（两阶段检索第二级） -------------------------

class _FakeResp:
    """模拟 requests.post 返回的精排响应。"""

    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _fake_recipe(title):
    """精排打分用的轻量菜谱对象（_build_rerank_document 只读这四个属性）。"""
    return SimpleNamespace(title=title, tags=None, ingredients=[], description="好吃")


class TestRerankPoolScores:
    """_rerank_pool_scores 单元测试 —— 请求构造、响应解析、降级路径。"""

    def test_disabled_returns_none(self, monkeypatch):
        monkeypatch.setattr(rag.settings, "RERANK_ENABLED", False)
        assert rag._rerank_pool_scores("q", [1, 2], {}) is None

    def test_missing_api_key_returns_none(self, monkeypatch):
        monkeypatch.setattr(rag.settings, "RERANK_ENABLED", True)
        monkeypatch.setattr(rag.settings, "RERANK_API_KEY", "")
        monkeypatch.setattr(rag.settings, "EMBEDDING_API_KEY", "")
        assert rag._rerank_pool_scores("q", [1, 2], {}) is None

    def test_single_candidate_returns_none(self, monkeypatch):
        monkeypatch.setattr(rag.settings, "RERANK_ENABLED", True)
        monkeypatch.setattr(rag.settings, "RERANK_API_KEY", "test-key")
        r = _fake_recipe("只有一道")
        assert rag._rerank_pool_scores("q", [1], {1: r}) is None

    def test_parses_scores_by_index(self, monkeypatch):
        monkeypatch.setattr(rag.settings, "RERANK_ENABLED", True)
        monkeypatch.setattr(rag.settings, "RERANK_API_KEY", "test-key")
        captured = {}

        def fake_post(url, headers=None, json=None, timeout=None):
            captured.update(url=url, json=json, timeout=timeout)
            return _FakeResp({"results": [
                {"index": 1, "relevance_score": 0.9},
                {"index": 0, "relevance_score": 0.2},
            ]})

        monkeypatch.setattr(rag.requests, "post", fake_post)
        recipes = {1: _fake_recipe("红烧肉"), 2: _fake_recipe("潮汕卤鹅")}
        scores = rag._rerank_pool_scores("潮汕年夜饭", [1, 2], recipes)

        assert scores == {2: 0.9, 1: 0.2}
        # 请求体：全量候选打分（top_n=2）、不回传原文、带查询
        assert captured["json"]["query"] == "潮汕年夜饭"
        assert captured["json"]["top_n"] == 2
        assert captured["json"]["return_documents"] is False
        assert captured["json"]["model"] == rag.settings.RERANK_MODEL
        assert len(captured["json"]["documents"]) == 2

    def test_api_error_returns_none(self, monkeypatch):
        monkeypatch.setattr(rag.settings, "RERANK_ENABLED", True)
        monkeypatch.setattr(rag.settings, "RERANK_API_KEY", "test-key")

        def boom(*a, **k):
            raise RuntimeError("network down")

        monkeypatch.setattr(rag.requests, "post", boom)
        recipes = {1: _fake_recipe("红烧肉"), 2: _fake_recipe("潮汕卤鹅")}
        assert rag._rerank_pool_scores("q", [1, 2], recipes) is None

    def test_empty_results_returns_none(self, monkeypatch):
        monkeypatch.setattr(rag.settings, "RERANK_ENABLED", True)
        monkeypatch.setattr(rag.settings, "RERANK_API_KEY", "test-key")
        monkeypatch.setattr(rag.requests, "post",
                            lambda *a, **k: _FakeResp({"results": []}))
        recipes = {1: _fake_recipe("红烧肉"), 2: _fake_recipe("潮汕卤鹅")}
        assert rag._rerank_pool_scores("q", [1, 2], recipes) is None

    def test_build_rerank_document_compact(self):
        r = SimpleNamespace(
            title="潮汕卤鹅", tags=None, ingredients=[], description="\n潮汕名菜\n" * 10
        )
        doc = rag._build_rerank_document(r)
        assert doc.startswith("潮汕卤鹅")
        assert "\n" not in doc
        assert len(doc) < 200


class TestRerankInRecipePool:
    """精排 + 分数融合与 build_recipe_pool_context 的集成行为（打桩精排分数）。"""

    def test_rerank_reorders_to_relevance(self, db_session, _patch_retrieval, monkeypatch):
        # 纯精排（alpha=1）：召回顺序 红烧肉→清蒸鲈鱼→潮汕卤鹅；精排把卤鹅顶到第一
        monkeypatch.setattr(rag.settings, "RERANK_ALPHA", 1.0)
        hong = _recipe(db_session, "红烧肉", cost=30)
        zheng = _recipe(db_session, "清蒸鲈鱼", cost=40)
        lu = _recipe(db_session, "潮汕卤鹅", cost=45)
        monkeypatch.setattr(rag, "rag_search",
                            lambda *a, **k: [{"source_id": hong.id}, {"source_id": zheng.id},
                                             {"source_id": lu.id}])
        monkeypatch.setattr(rag, "_rerank_pool_scores",
                            lambda q, pool, recipes: {lu.id: 0.9, zheng.id: 0.5, hong.id: 0.1})
        body = rag.build_recipe_pool_context(db_session, "潮汕年夜饭", restriction_set=set())
        assert "菜1｜潮汕卤鹅" in body
        assert body.index("潮汕卤鹅") < body.index("清蒸鲈鱼") < body.index("红烧肉")

    def test_rerank_missing_score_sinks_to_bottom(self, db_session, _patch_retrieval, monkeypatch):
        # 纯精排（alpha=1）：兜底补充的菜没有精排分数 → 沉底且不丢失
        monkeypatch.setattr(rag.settings, "RERANK_ALPHA", 1.0)
        hi = _recipe(db_session, "潮汕卤鹅", cost=45)
        fallback = _recipe(db_session, "普通热门菜", cost=20)
        monkeypatch.setattr(rag, "rag_search",
                            lambda *a, **k: [{"source_id": fallback.id}, {"source_id": hi.id}])
        monkeypatch.setattr(rag, "_rerank_pool_scores",
                            lambda q, pool, recipes: {hi.id: 0.9})
        body = rag.build_recipe_pool_context(db_session, "潮汕年夜饭", restriction_set=set())
        assert body.index("潮汕卤鹅") < body.index("普通热门菜")

    def test_rerank_budget_group_first_relevance_within(self, db_session, _patch_retrieval, monkeypatch):
        # 纯精排（alpha=1）：预算分组优先级高于精排分；超预算高分菜仍在预算内之后
        monkeypatch.setattr(rag.settings, "RERANK_ALPHA", 1.0)
        over = _recipe(db_session, "昂贵海鲜", cost=150)
        hi = _recipe(db_session, "潮汕卤鹅", cost=40)
        lo = _recipe(db_session, "清蒸鲈鱼", cost=35)
        monkeypatch.setattr(rag, "rag_search",
                            lambda *a, **k: [{"source_id": over.id}, {"source_id": hi.id},
                                             {"source_id": lo.id}])
        monkeypatch.setattr(rag, "_rerank_pool_scores",
                            lambda q, pool, recipes: {over.id: 0.95, hi.id: 0.8, lo.id: 0.3})
        body = rag.build_recipe_pool_context(db_session, "潮汕年夜饭 预算约100元",
                                             restriction_set=set())
        # 预算内(≤100)在前、超预算(150)在后；组内保持精排相关度序
        assert body.index("潮汕卤鹅") < body.index("昂贵海鲜")
        assert body.index("清蒸鲈鱼") < body.index("昂贵海鲜")
        assert body.index("潮汕卤鹅") < body.index("清蒸鲈鱼")

    # ---- 分数融合 _fusion_sorted_pool ----

    def test_fusion_alpha_zero_keeps_recall_order(self, monkeypatch):
        monkeypatch.setattr(rag.settings, "RERANK_ALPHA", 0.0)
        pool = [101, 102, 103]
        recipes = {101: _fake_recipe("红烧肉"), 102: _fake_recipe("清蒸鲈鱼"),
                   103: _fake_recipe("潮汕卤鹅")}
        scores = {103: 0.95, 102: 0.6, 101: 0.6}
        assert rag._fusion_sorted_pool(pool, recipes, scores) == [101, 102, 103]

    def test_fusion_alpha_half_keeps_top_recall_promotes_relevant(self, monkeypatch):
        # 召回第1的菜(101)即使精排分不高(0.6)仍保持第1；
        # 精排高分(0.95)的 103 上浮到第2，但不推翻粗排好序
        monkeypatch.setattr(rag.settings, "RERANK_ALPHA", 0.5)
        pool = [101, 102, 103]
        recipes = {101: _fake_recipe("红烧肉"), 102: _fake_recipe("清蒸鲈鱼"),
                   103: _fake_recipe("潮汕卤鹅")}
        scores = {103: 0.95, 102: 0.6, 101: 0.6}
        ordered = rag._fusion_sorted_pool(pool, recipes, scores)
        assert ordered[0] == 101
        assert ordered[1] == 103
        assert ordered[2] == 102

    def test_fusion_alpha_one_pure_rerank(self, monkeypatch):
        monkeypatch.setattr(rag.settings, "RERANK_ALPHA", 1.0)
        pool = [101, 102, 103]
        recipes = {101: _fake_recipe("红烧肉"), 102: _fake_recipe("清蒸鲈鱼"),
                   103: _fake_recipe("潮汕卤鹅")}
        scores = {103: 0.95, 102: 0.6, 101: 0.6}
        ordered = rag._fusion_sorted_pool(pool, recipes, scores)
        assert ordered[0] == 103  # 纯精排：精排分最高者第一
        assert 101 in ordered and 102 in ordered

    def test_fusion_missing_score_sinks(self, monkeypatch):
        monkeypatch.setattr(rag.settings, "RERANK_ALPHA", 0.5)
        pool = [101, 102, 999]  # 999 无精排分
        recipes = {101: _fake_recipe("红烧肉"), 102: _fake_recipe("清蒸鲈鱼"),
                   999: _fake_recipe("兜底热门")}
        scores = {101: 0.9, 102: 0.5}
        ordered = rag._fusion_sorted_pool(pool, recipes, scores)
        assert ordered[-1] == 999  # 无分菜沉底
        assert ordered[0] == 101


# ------------------------------ AI 对话引擎 ------------------------------

@pytest.fixture(autouse=True)
def _reset_memories():
    """每个测试前清空 ai_service 的全局对话内存，避免状态串扰。"""
    originals = {}
    for cid in list(ai._conversation_memories):
        originals[cid] = ai._conversation_memories.pop(cid)
    yield
    ai._conversation_memories.clear()
    ai._conversation_memories.update(originals)


class TestIsCookingForOthers:
    @pytest.mark.parametrize("msg,expected", [
        ("给朋友做饭", True),
        ("这季度想请客", True),
        ("招待客人", True),
        ("给自己晚餐", False),
        ("做给小孩吃", True),
    ])
    def test_patterns(self, msg, expected):
        assert ai._is_cooking_for_others(msg) is expected


class TestBuildContextFromRag:
    def test_empty(self):
        assert ai._build_context_from_rag([]) == ""

    def test_formats_results(self):
        out = ai._build_context_from_rag([
            {"content": "做法一", "title": "红烧肉"},
            {"content": "做法二", "title": "清蒸鱼"},
        ])
        assert "参考资料 1" in out
        assert "做法一" in out
        assert "参考资料 2" in out
        assert "做法二" in out


class TestChatStream:
    async def _collect(self, llm):
        return [c async for c in ai.chat_stream(
            message="推荐两道菜", conversation_id=1, use_rag=False, db=None,
        )]

    def test_stream_yields_and_saves_memory(self, monkeypatch):
        async def fake_astream(messages):
            for piece in ("你好", "，", "红烧肉"):
                yield SimpleNamespace(content=piece)
        monkeypatch.setattr(ai, "_get_llm", lambda: SimpleNamespace(astream=fake_astream))

        chunks = asyncio.run(self._collect(None))
        assert "".join(chunks) == "你好，红烧肉"
        # 对话已存入内存，供后续上下文使用
        memory = ai._get_or_create_memory(1)
        msgs = memory.chat_memory.messages
        assert any(getattr(m, "content", "") == "推荐两道菜" for m in msgs)
        assert any(getattr(m, "content", "") == "你好，红烧肉" for m in msgs)

    def test_llm_failure_returns_graceful_message(self, monkeypatch):
        async def boom(messages):
            if True:
                raise RuntimeError("llm down")
            yield None
        monkeypatch.setattr(ai, "_get_llm", lambda: SimpleNamespace(astream=boom))

        chunks = asyncio.run(self._collect(None))
        assert "".join(chunks) == "抱歉，AI 服务暂时不可用，请稍后重试。"

    def test_memory_lru_eviction(self):
        # 预填满活跃会话，再插入一个新会话应淘汰最旧的
        ai._conversation_memories.clear()
        for cid in range(ai._MAX_ACTIVE_MEMORIES):
            m = ai._get_or_create_memory(cid)
        assert len(ai._conversation_memories) == ai._MAX_ACTIVE_MEMORIES
        m_new = ai._get_or_create_memory(99999)
        assert len(ai._conversation_memories) == ai._MAX_ACTIVE_MEMORIES
        assert 0 not in ai._conversation_memories  # 最久未活跃的被淘汰
        assert 1 in ai._conversation_memories
        assert 99999 in ai._conversation_memories