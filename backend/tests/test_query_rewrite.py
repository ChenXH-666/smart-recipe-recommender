# -*- coding: utf-8 -*-
"""查询改写单元测试 —— 实体词触发判定 / 输出清洗与校验 / 降级回退 / 双查询 RRF 融合。

外部依赖处理：
  - 向量库用 SimpleNamespace 假对象模拟（_collection.get 提供菜名元数据），
    保证不触碰真实 Chroma / SiliconFlow；
  - LLM 调用（_call_rewrite_llm）一律 monkeypatch，绝不发起真实请求。
"""
from types import SimpleNamespace

import pytest

import app.services.rag_service as rag


@pytest.fixture(autouse=True)
def _reset_kw_index():
    """BM25 索引与菜名词表是模块级缓存：逐用例清空，避免用例间互相污染。"""
    rag._kw_index = None
    yield
    rag._kw_index = None


DOCS = [
    ("菜谱：清蒸鲈鱼", {"source_type": "recipe", "source_id": 1, "title": "清蒸鲈鱼", "tags": "清淡"}),
    ("菜谱：西红柿炒鸡蛋", {"source_type": "recipe", "source_id": 2, "title": "西红柿炒鸡蛋", "tags": "家常菜"}),
    ("菜谱：家常红烧肉", {"source_type": "recipe", "source_id": 3, "title": "家常红烧肉", "tags": "硬菜"}),
    # 心得分块：标题含"家常菜"泛词，不应进入菜名词表（否则会误判"查询已含实体词"）
    ("烹饪心得：新手也能学会的家常菜", {"source_type": "cooking_note", "source_id": 9,
                                 "title": "新手也能学会的家常菜", "tags": ""}),
]


@pytest.fixture()
def fake_vs(monkeypatch):
    """假向量库：菜名词表来自 DOCS，向量通道返回全部假分块。"""
    vs = SimpleNamespace(
        _collection=SimpleNamespace(
            get=lambda include=None, **k: {
                "documents": [c for c, _ in DOCS],
                "metadatas": [m for _, m in DOCS],
            }
        ),
        similarity_search=lambda q, k=None, filter=None: [
            SimpleNamespace(page_content=c, metadata=m) for c, m in DOCS
        ][:k],
    )
    monkeypatch.setattr(rag, "get_vectorstore", lambda: vs)
    return vs


# ------------------------------ 实体词触发判定 ------------------------------

class TestEntityTrigger:
    def test_longest_title_match_len(self, fake_vs):
        ngrams = rag._get_title_ngrams()
        assert rag._max_title_match_len("清蒸鲈鱼的做法", ngrams) == 4
        assert rag._max_title_match_len("新手也能做的蛋糕", ngrams) == 0  # 无 ≥3 字命中
        assert rag._max_title_match_len("减脂晚餐", ngrams) == 0

    def test_weak_two_char_hit_still_triggers(self, fake_vs):
        # 2 字命中（"家常"）不足以定位菜品 → 仍视为无实体词、触发改写
        assert rag.query_has_library_entity("下班后搞定的快手家常菜") is False

    def test_three_char_hit_counts_as_entity(self, fake_vs):
        # 3 字命中即视为已含实体词（"西红柿的做法"命中菜名片段"西红柿"）
        assert rag.query_has_library_entity("西红柿的做法") is True

    def test_cooking_note_titles_excluded_from_lexicon(self, fake_vs):
        # 心得标题不入菜名词表：查询"新手也能学会的家常菜"不得因泛词"家常菜"被判为含实体词
        assert rag.query_has_library_entity("新手也能学会的家常菜") is False

    def test_missing_index_treated_as_no_entity(self, monkeypatch):
        # 词表不可用（向量库异常）时保守按"无实体词"处理，不抛异常
        monkeypatch.setattr(rag, "get_vectorstore", lambda: (_ for _ in ()).throw(RuntimeError("chroma down")))
        assert rag.query_has_library_entity("随便") is False


# ------------------------------ 输出清洗与校验 ------------------------------

class TestRewriteCleaningAndValidation:
    def test_clean_takes_first_non_empty_line(self):
        assert rag._clean_rewrite_text("改写结果：凉拌土豆丝 酸辣土豆丝") == "凉拌土豆丝 酸辣土豆丝"
        assert rag._clean_rewrite_text('"清蒸鲈鱼 清蒸鱼"') == "清蒸鲈鱼 清蒸鱼"
        assert rag._clean_rewrite_text("\n\n  \n快手菜 西红柿炒鸡蛋\n第二行") == "快手菜 西红柿炒鸡蛋"
        assert rag._clean_rewrite_text("") == ""

    def test_clean_truncates_overlong_output(self):
        assert len(rag._clean_rewrite_text("蒸" * 200)) == rag._REWRITE_MAX_CHARS

    def test_validate_rejects_hallucinated_dish(self, fake_vs):
        assert rag._validate_rewrite("米其林三星佛跳墙", "下班做什么菜") is False

    def test_validate_rejects_dropped_budget_constraint(self, fake_vs):
        # 原查询含预算 100，改写丢失该金额 → 校验不过（防止预算约束被改写丢弃）
        assert rag._validate_rewrite("西红柿炒鸡蛋 家常红烧肉", "预算100元的家常菜") is False

    def test_validate_allows_dropping_non_constraint_number(self, fake_vs):
        # 非约束数字（"30分钟"）允许改写丢弃，不影响校验通过
        assert rag._validate_rewrite("西红柿炒鸡蛋 家常红烧肉", "30分钟搞定的快手家常菜") is True

    def test_validate_accepts_grounded_rewrite(self, fake_vs):
        assert rag._validate_rewrite("预算100元 家常红烧肉 西红柿炒鸡蛋", "预算100元的家常菜") is True


# ------------------------------ 改写总入口与降级 ------------------------------

class TestPlanQueryRewrite:
    QUERY = "下班做什么菜"  # 与库内菜名无 3 字以上连续命中 → 触发改写

    @pytest.fixture(autouse=True)
    def _with_api_key(self, monkeypatch):
        """测试环境 .env 不含 Key：注入假 Key 以进入 LLM 改写分支（不发起真实请求）。"""
        monkeypatch.setattr(rag.settings, "LLM_API_KEY", "test-key")

    def test_skip_when_entity_present(self, fake_vs, monkeypatch):
        monkeypatch.setattr(rag, "_call_rewrite_llm",
                            lambda q: (_ for _ in ()).throw(AssertionError("不应调用 LLM")))
        assert rag.plan_query_rewrite("清蒸鲈鱼怎么做") is None

    def test_success_path(self, fake_vs, monkeypatch):
        monkeypatch.setattr(rag, "_call_rewrite_llm", lambda q: "西红柿炒鸡蛋 家常红烧肉")
        assert rag.plan_query_rewrite(self.QUERY) == "西红柿炒鸡蛋 家常红烧肉"

    def test_llm_failure_falls_back(self, fake_vs, monkeypatch):
        def _boom(q):
            raise TimeoutError("llm timeout")
        monkeypatch.setattr(rag, "_call_rewrite_llm", _boom)
        assert rag.plan_query_rewrite(self.QUERY) is None

    def test_validation_failure_falls_back(self, fake_vs, monkeypatch):
        monkeypatch.setattr(rag, "_call_rewrite_llm", lambda q: "佛跳墙 龙肝凤髓")
        assert rag.plan_query_rewrite(self.QUERY) is None

    def test_empty_output_falls_back(self, fake_vs, monkeypatch):
        monkeypatch.setattr(rag, "_call_rewrite_llm", lambda q: "   ")
        assert rag.plan_query_rewrite(self.QUERY) is None

    def test_identical_output_skipped(self, fake_vs, monkeypatch):
        monkeypatch.setattr(rag, "_call_rewrite_llm", lambda q: self.QUERY)
        assert rag.plan_query_rewrite(self.QUERY) is None

    def test_missing_api_key_skips_without_call(self, fake_vs, monkeypatch):
        monkeypatch.setattr(rag.settings, "LLM_API_KEY", "")
        monkeypatch.setattr(rag, "_call_rewrite_llm",
                            lambda q: (_ for _ in ()).throw(AssertionError("不应调用 LLM")))
        assert rag.plan_query_rewrite(self.QUERY) is None


# ------------------------------ 双查询召回 RRF 融合 ------------------------------

def _hit(rid: int, content: str = None):
    return {
        "content": content or f"chunk-{rid}",
        "source_type": "recipe",
        "source_id": rid,
        "title": f"菜{rid}",
        "tags": "",
    }


class TestMergeRankedResults:
    def test_empty_secondary_keeps_primary(self):
        primary = [_hit(1)]
        assert rag._merge_ranked_results(primary, [], 5) is primary

    def test_empty_primary_keeps_secondary(self):
        secondary = [_hit(1)]
        assert rag._merge_ranked_results([], secondary, 5) is secondary

    def test_both_lists_contribute_and_dedupe(self):
        # 分块 1 被两路共同召回 → RRF 分最高且只出现一次；分块 9 仅改写查询召回
        fused = rag._merge_ranked_results([_hit(1), _hit(2)], [_hit(1), _hit(9)], 5)
        ids = [r["source_id"] for r in fused]
        assert ids[0] == 1
        assert set(ids) == {1, 2, 9}
        assert len(ids) == len(set(ids))

    def test_truncates_to_top_k(self):
        fused = rag._merge_ranked_results(
            [_hit(1), _hit(2), _hit(3)], [_hit(4), _hit(5)], 3
        )
        assert len(fused) == 3


class TestRagSearchRewritePath:
    def test_rewrite_false_does_not_trigger(self, monkeypatch):
        monkeypatch.setattr(rag, "plan_query_rewrite",
                            lambda q: (_ for _ in ()).throw(AssertionError("不应触发改写")))
        monkeypatch.setattr(rag, "_single_query_recall", lambda *a, **k: [_hit(1)])
        monkeypatch.setattr(rag, "get_vectorstore", lambda: SimpleNamespace())
        res = rag.rag_search("下班做什么菜", top_k=3, filter_source_type="recipe",
                             rewrite=False)
        assert [r["source_id"] for r in res] == [1]

    def test_injected_rewrite_runs_second_recall_and_fusion(self, monkeypatch):
        calls = []

        def _fake_recall(vs, query, top_k, filter_source_type, hybrid):
            calls.append(query)
            return [_hit(1), _hit(2)] if query == "原查询" else [_hit(3)]

        monkeypatch.setattr(rag, "_single_query_recall", _fake_recall)
        monkeypatch.setattr(rag, "get_vectorstore", lambda: SimpleNamespace())
        res = rag.rag_search("原查询", top_k=5, filter_source_type="recipe",
                             rewrite=False, rewritten_query="改写查询")
        assert calls == ["原查询", "改写查询"]
        assert {r["source_id"] for r in res} == {1, 2, 3}

    def test_second_recall_failure_keeps_primary(self, monkeypatch):
        def _fake_recall(vs, query, top_k, filter_source_type, hybrid):
            if query == "改写查询":
                raise RuntimeError("recall broken")
            return [_hit(1)]

        monkeypatch.setattr(rag, "_single_query_recall", _fake_recall)
        monkeypatch.setattr(rag, "get_vectorstore", lambda: SimpleNamespace())
        res = rag.rag_search("原查询", top_k=5, filter_source_type="recipe",
                             rewrite=False, rewritten_query="改写查询")
        assert [r["source_id"] for r in res] == [1]

    def test_default_uses_config_and_triggers_plan(self, monkeypatch):
        # 未显式传参与 rewritten_query 时，按配置触发 plan_query_rewrite
        called = {"plan": False}

        def _plan(q):
            called["plan"] = True
            return "改写查询"

        monkeypatch.setattr(rag, "plan_query_rewrite", _plan)
        monkeypatch.setattr(rag, "_single_query_recall",
                            lambda vs, q, k, f, h: [_hit(1)] if q == "原查询" else [_hit(3)])
        monkeypatch.setattr(rag, "get_vectorstore", lambda: SimpleNamespace())
        res = rag.rag_search("原查询", top_k=5, filter_source_type="recipe")
        assert called["plan"] is True
        assert {r["source_id"] for r in res} == {1, 3}