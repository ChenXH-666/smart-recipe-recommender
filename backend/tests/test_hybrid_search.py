# -*- coding: utf-8 -*-
"""混合检索单元测试 —— BM25 分词 / 关键词通道 / RRF 融合 / 双路召回降级。

外部依赖处理：
  - 向量库用 SimpleNamespace 假对象模拟（_collection.get 供索引构建、
    similarity_search 返回预设结果），保证不触碰真实 Chroma / SiliconFlow。
"""
from types import SimpleNamespace

import pytest

import app.services.rag_service as rag


@pytest.fixture(autouse=True)
def _reset_kw_index():
    """BM25 索引是模块级缓存：逐用例清空，避免用例间互相污染。"""
    rag._kw_index = None
    yield
    rag._kw_index = None


def _fake_vs(docs_metas, sim_docs=None, sim_raises=False):
    """构造假 Chroma 向量库。

    docs_metas: [(content, meta), ...] 全量分块（供 BM25 索引构建）
    sim_docs:   向量通道预设返回的分块子集（按 [(content, meta)] 传入）
    sim_raises: 向量通道是否抛异常（模拟 Embedding/Chroma 故障）
    """
    collection = SimpleNamespace(
        get=lambda include=None, **k: {
            "documents": [c for c, _ in docs_metas],
            "metadatas": [m for _, m in docs_metas],
        }
    )

    def similarity_search(query, k=None, filter=None):
        if sim_raises:
            raise RuntimeError("similarity_search broken")
        out = [SimpleNamespace(page_content=c, metadata=m) for c, m in (sim_docs or [])]
        return out[:k] if k else out

    return SimpleNamespace(_collection=collection, similarity_search=similarity_search)


# ------------------------------ BM25 分词 ------------------------------

class TestBm25Tokens:
    @pytest.mark.parametrize("text,unigram,bigram", [
        ("红烧肉", "红烧", "烧肉"),
        ("西红柿炒鸡蛋", "西红", "红柿"),
    ])
    def test_cjk_unigram_and_bigram(self, text, unigram, bigram):
        toks = rag._bm25_tokens(text)
        assert unigram in toks and bigram in toks

    def test_ascii_words_kept_whole_lowercase(self):
        toks = rag._bm25_tokens("Braise Pork Belly")
        assert "braise" in toks and "pork" in toks and "belly" in toks

    def test_punctuation_ignored(self):
        # 标点被丢弃后，两侧汉字仍相邻成 bigram，与无标点版本分词一致
        assert rag._bm25_tokens("红烧，肉！") == rag._bm25_tokens("红烧肉")

    def test_mixed_ascii_cjk(self):
        toks = rag._bm25_tokens("可乐鸡翅500g")
        assert "可乐" in toks and "鸡翅" in toks and "500g" in toks

    def test_empty_or_none(self):
        assert rag._bm25_tokens("") == []
        assert rag._bm25_tokens(None) == []


# ------------------------------ RRF 排名融合 ------------------------------

class TestRrfFuse:
    def test_both_channels_win(self):
        # y 双路均出现 → RRF 分最高
        fused = rag._rrf_fuse([["x", "y", "z"], ["y", "w"]], k=60)
        assert fused[0] == "y"
        assert set(fused) == {"x", "y", "z", "w"}

    def test_formula_hand_computed(self):
        # k=1：x 仅 A 路 rank1 → 1/(1+1)=0.5；y 为 A rank2 + B rank1 → 1/3+1/2=0.833
        fused = rag._rrf_fuse([["x", "y"], ["y"]], k=1)
        assert fused == ["y", "x"]

    def test_higher_rank_wins_within_one_channel(self):
        # 单路时 RRF 退化为原顺序
        assert rag._rrf_fuse([["a", "b", "c"]], k=60) == ["a", "b", "c"]

    def test_empty_inputs(self):
        assert rag._rrf_fuse([], k=60) == []
        assert rag._rrf_fuse([[]], k=60) == []


# ------------------------------ BM25 关键词通道 ------------------------------

class TestBm25KeywordSearch:
    DOCS = [
        ("菜谱：清蒸鲈鱼\n简介：清淡鲜嫩", {"source_type": "recipe", "source_id": 1, "title": "清蒸鲈鱼", "tags": "清淡"}),
        ("菜谱：红烧肉\n简介：经典浓油赤酱", {"source_type": "recipe", "source_id": 2, "title": "红烧肉", "tags": "下饭"}),
        ("烹饪心得：鲈鱼去腥技巧", {"source_type": "cooking_note", "source_id": 3, "title": "鲈鱼去腥", "tags": ""}),
    ]

    def test_title_exact_match_ranks_first(self):
        vs = _fake_vs(self.DOCS)
        res = rag._bm25_keyword_search(vs, "清蒸鲈鱼", top_k=3, filter_source_type="recipe")
        assert res and res[0]["source_id"] == 1
        assert res[0]["title"] == "清蒸鲈鱼"

    def test_filter_source_type_excludes_notes(self):
        vs = _fake_vs(self.DOCS)
        res = rag._bm25_keyword_search(vs, "鲈鱼", top_k=10, filter_source_type="recipe")
        assert {r["source_type"] for r in res} == {"recipe"}
        # 不过滤时心得也应进入候选
        res_all = rag._bm25_keyword_search(vs, "鲈鱼", top_k=10, filter_source_type=None)
        assert any(r["source_type"] == "cooking_note" for r in res_all)

    def test_no_token_match_returns_empty(self):
        vs = _fake_vs(self.DOCS)
        assert rag._bm25_keyword_search(vs, "披萨汉堡", top_k=3, filter_source_type="recipe") == []

    def test_top_k_truncates(self):
        vs = _fake_vs(self.DOCS)
        res = rag._bm25_keyword_search(vs, "鲈鱼", top_k=1, filter_source_type=None)
        assert len(res) == 1


# ------------------------------ 混合检索主流程与降级 ------------------------------

class TestHybridSearch:
    DOCS = [
        ("菜谱：清蒸鲈鱼\n食材：鲈鱼", {"source_type": "recipe", "source_id": 1, "title": "清蒸鲈鱼", "tags": ""}),
        ("菜谱：鲈鱼豆腐汤\n食材：鲈鱼", {"source_type": "recipe", "source_id": 2, "title": "鲈鱼豆腐汤", "tags": ""}),
        ("菜谱：红烧肉", {"source_type": "recipe", "source_id": 3, "title": "红烧肉", "tags": ""}),
    ]

    def test_fusion_contains_both_channel_hits(self):
        # 向量通道只回了 doc1，关键词通道把 doc2 也捞了回来 → 融合结果含两者
        vs = _fake_vs(self.DOCS, sim_docs=[self.DOCS[0]])
        res = rag._hybrid_search(vs, "鲈鱼", top_k=3, filter_source_type="recipe")
        ids = {r["source_id"] for r in res}
        assert {1, 2} <= ids

    def test_vector_channel_failure_degrades_to_keyword(self):
        vs = _fake_vs(self.DOCS, sim_raises=True)
        res = rag._hybrid_search(vs, "清蒸鲈鱼", top_k=3, filter_source_type="recipe")
        assert res and res[0]["source_id"] == 1

    def test_keyword_channel_failure_degrades_to_vector(self):
        # 空 BM25 索引（假 collection 返回空）→ 仅向量通道结果
        empty_vs = SimpleNamespace(
            _collection=SimpleNamespace(
                get=lambda include=None, **k: {"documents": [], "metadatas": []}
            ),
            similarity_search=lambda q, k=None, filter=None: [
                SimpleNamespace(page_content=c, metadata=m) for c, m in [self.DOCS[2]]
            ],
        )
        res = rag._hybrid_search(empty_vs, "红烧肉", top_k=3, filter_source_type="recipe")
        assert [r["source_id"] for r in res] == [3]

    def test_keyword_channel_exception_degrades_to_vector(self, monkeypatch):
        # BM25 通道抛异常（而非仅索引为空）→ 仍返回向量通道结果
        def boom(*a, **k):
            raise RuntimeError("bm25 broken")

        monkeypatch.setattr(rag, "_bm25_keyword_search", boom)
        vs = _fake_vs(self.DOCS, sim_docs=[self.DOCS[0]])
        res = rag._hybrid_search(vs, "清蒸鲈鱼", top_k=3, filter_source_type="recipe")
        assert [r["source_id"] for r in res] == [1]

    def test_result_structure(self):
        vs = _fake_vs(self.DOCS, sim_docs=[self.DOCS[0]])
        res = rag._hybrid_search(vs, "清蒸鲈鱼", top_k=3, filter_source_type="recipe")
        for r in res:
            assert set(r) == {"content", "source_type", "source_id", "title", "tags"}


class TestRagSearchHybridSwitch:
    DOCS = [
        ("菜谱：清蒸鲈鱼", {"source_type": "recipe", "source_id": 1, "title": "清蒸鲈鱼", "tags": ""}),
    ]

    def test_hybrid_true_calls_fusion(self, monkeypatch):
        vs = _fake_vs(self.DOCS, sim_docs=self.DOCS)
        monkeypatch.setattr(rag, "get_vectorstore", lambda: vs)
        res = rag.rag_search("清蒸鲈鱼", top_k=1, filter_source_type="recipe", hybrid=True)
        assert res and res[0]["source_id"] == 1

    def test_hybrid_false_pure_vector_path(self, monkeypatch):
        called = {"kw": False}

        def _no_kw(*a, **k):
            called["kw"] = True  # 不应被调用
            return []

        monkeypatch.setattr(rag, "_bm25_keyword_search", _no_kw)
        vs = _fake_vs(self.DOCS, sim_docs=self.DOCS)
        monkeypatch.setattr(rag, "get_vectorstore", lambda: vs)
        res = rag.rag_search("清蒸鲈鱼", top_k=1, filter_source_type="recipe", hybrid=False)
        assert res and res[0]["source_id"] == 1
        assert called["kw"] is False

    def test_hybrid_exception_falls_back_to_vector(self, monkeypatch):
        def _boom(*a, **k):
            raise RuntimeError("hybrid broken")

        monkeypatch.setattr(rag, "_hybrid_search", _boom)
        vs = _fake_vs(self.DOCS, sim_docs=self.DOCS)
        monkeypatch.setattr(rag, "get_vectorstore", lambda: vs)
        res = rag.rag_search("清蒸鲈鱼", top_k=1, filter_source_type="recipe", hybrid=True)
        assert res and res[0]["source_id"] == 1


# ------------------------------ 约束类查询跳过关键词通道 ------------------------------

class TestConstraintQuerySkipKeyword:
    """约束类查询（预算/人数）跳过 BM25 关键词通道 —— 修复约束组召回回退。

    背景：BM25 对"东北""家常"等泛类别词的大面积字面命中会把同类无关菜
    推入前排、经 RRF 融合后挤掉向量通道语义命中的确切菜谱。
    """

    DOCS = [
        ("菜谱：清蒸鲈鱼", {"source_type": "recipe", "source_id": 1, "title": "清蒸鲈鱼", "tags": ""}),
        ("菜谱：家常地三鲜", {"source_type": "recipe", "source_id": 2, "title": "家常地三鲜", "tags": "家常菜"}),
    ]

    @pytest.mark.parametrize("query,expected", [
        ("预算100元的东北菜家常菜", True),
        ("300块以内的东北菜", True),
        ("花150元做几个菜", True),
        ("给三个人做的晚餐", True),
        ("5人份的家常菜", True),
        ("一人食简单午餐", True),
        ("清蒸鲈鱼的做法", False),
        ("5块排骨怎么做", False),               # 量词不误判为货币（历史踩坑）
        ("下班后30分钟搞定的快手家常菜", False),  # 时长不是约束条件
    ])
    def test_constraint_detection(self, query, expected):
        assert rag.query_has_explicit_constraint(query) is expected

    def test_hybrid_skips_keyword_for_constraint_query(self, monkeypatch):
        called = {"kw": False}

        def _kw(*a, **k):
            called["kw"] = True
            return []

        monkeypatch.setattr(rag, "_bm25_keyword_search", _kw)
        vs = _fake_vs(self.DOCS, sim_docs=self.DOCS)
        monkeypatch.setattr(rag, "get_vectorstore", lambda: vs)
        res = rag.rag_search("预算100元的东北菜家常菜", top_k=2,
                             filter_source_type="recipe", hybrid=True)
        assert called["kw"] is False          # 关键词通道被跳过（退化为纯向量）
        assert res and res[0]["source_id"] == 1

    def test_non_constraint_query_still_uses_keyword(self, monkeypatch):
        called = {"kw": False}

        def _kw(*a, **k):
            called["kw"] = True
            return []

        monkeypatch.setattr(rag, "_bm25_keyword_search", _kw)
        vs = _fake_vs(self.DOCS, sim_docs=self.DOCS)
        monkeypatch.setattr(rag, "get_vectorstore", lambda: vs)
        rag.rag_search("清蒸鲈鱼", top_k=2, filter_source_type="recipe", hybrid=True)
        assert called["kw"] is True

    def test_explicit_override_disables_skip(self, monkeypatch):
        """评测对照用：skip_kw_constraint=False 显式保留关键词通道（修复前行为）"""
        called = {"kw": False}

        def _kw(*a, **k):
            called["kw"] = True
            return []

        monkeypatch.setattr(rag, "_bm25_keyword_search", _kw)
        vs = _fake_vs(self.DOCS, sim_docs=self.DOCS)
        monkeypatch.setattr(rag, "get_vectorstore", lambda: vs)
        rag.rag_search("预算100元的东北菜家常菜", top_k=2, filter_source_type="recipe",
                       hybrid=True, skip_kw_constraint=False)
        assert called["kw"] is True

    def test_config_switch_disables_skip(self, monkeypatch):
        """配置关闭（RAG_HYBRID_CONSTRAINT_SKIP_KEYWORD=False）时维持双通道原行为"""
        called = {"kw": False}

        def _kw(*a, **k):
            called["kw"] = True
            return []

        monkeypatch.setattr(rag.settings, "RAG_HYBRID_CONSTRAINT_SKIP_KEYWORD", False)
        monkeypatch.setattr(rag, "_bm25_keyword_search", _kw)
        vs = _fake_vs(self.DOCS, sim_docs=self.DOCS)
        monkeypatch.setattr(rag, "get_vectorstore", lambda: vs)
        rag.rag_search("给三个人做的晚餐", top_k=2, filter_source_type="recipe", hybrid=True)
        assert called["kw"] is True


# ------------------------------ 索引失效钩子 ------------------------------

class TestKwIndexInvalidation:
    def test_invalidate_clears_cache(self):
        rag._kw_index = {"terms": {"x": 1}}
        rag._invalidate_kw_index()
        assert rag._kw_index is None

    def test_sync_recipe_invalidates_index(self, monkeypatch):
        # 假向量库 + 假菜谱对象，验证同步后索引被置空
        added = []

        class _FakeVS:
            _collection = SimpleNamespace(
                get=lambda **kwargs: {"ids": []},
                delete=lambda where=None, ids=None: None,
            )

            def add_texts(self, texts, metadatas=None, ids=None):
                added.extend(ids or [])

        rag._kw_index = {"terms": {"stale": True}}
        monkeypatch.setattr(rag, "get_vectorstore", lambda: _FakeVS())
        recipe = SimpleNamespace(
            id=99, title="测试菜", description="", tags=[],
            ingredients=[], steps=[],
        )
        rag.sync_recipe_to_chroma(recipe)
        assert added == ["recipe_99_0"]
        assert rag._kw_index is None


# ------------------------------ 单查询召回的降级路径 ------------------------------

class TestSingleQueryRecall:
    """_single_query_recall：混合检索命中/空结果时的向量检索调用次数。"""

    DOCS = [
        ("菜谱：清蒸鲈鱼", {"source_type": "recipe", "source_id": 1,
                          "title": "清蒸鲈鱼", "tags": ""}),
    ]

    def test_hybrid_hit_does_not_retry_vector_search(self):
        vs = _fake_vs(self.DOCS, sim_docs=self.DOCS)
        calls = []
        original = vs.similarity_search

        def counting(q, k=None, filter=None):
            calls.append(1)
            return original(q, k=k, filter=filter)

        vs.similarity_search = counting
        res = rag._single_query_recall(vs, "清蒸鲈鱼", 3, "recipe", hybrid=True)
        assert [r["source_id"] for r in res] == [1]
        assert len(calls) == 1

    def test_empty_hybrid_does_not_repeat_vector_search(self):
        calls = []

        def empty_search(q, k=None, filter=None):
            calls.append(1)
            return []

        vs = SimpleNamespace(
            _collection=SimpleNamespace(
                get=lambda include=None, **k: {"documents": [], "metadatas": []}
            ),
            similarity_search=empty_search,
        )
        res = rag._single_query_recall(vs, "不存在的菜", 3, "recipe", hybrid=True)
        assert res == []
        assert len(calls) == 1
