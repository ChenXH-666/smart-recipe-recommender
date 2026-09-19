# -*- coding: utf-8 -*-
"""查询关键词匹配打分 —— RAG 兜底检索与推荐兜底共用的一份实现。

同一套"整词精确命中 + 2~3 字 n-gram 近似命中"的打分逻辑，此前在
rag_service._keyword_match_score 与 recommendation_service 的 calc_score 里各写一遍。
抽出后由调用方传入各自的字段与权重（两侧权重本就不同，不强行统一），逻辑只维护一份。
"""
import re
from typing import List, Sequence, Tuple

# 口语化查询里的常见词：不携带菜谱信息，打分前剔除
QUERY_STOPWORDS = {
    "推荐", "帮", "我", "的", "一个", "点", "些", "想", "要", "吃", "做", "个",
    "便宜", "好吃", "简单", "点的", "来点", "今天", "请问", "有没有", "有什么",
}

_SPLIT_RE = re.compile(r"[\s，。、；：,.;:!?()（）\[\]【】\"'《》]+")


def tokenize_query(query: str) -> List[str]:
    """按标点切分查询并剔除停用词；全部被剔除时退回原始切分，保证仍有 token 可用"""
    raw = [t for t in _SPLIT_RE.split(query or "") if t]
    tokens = [t for t in raw if t not in QUERY_STOPWORDS]
    return tokens or raw


def keyword_match_score(
    tokens: Sequence[str],
    exact_fields: Sequence[Tuple[str, float]],
    ngram_fields: Sequence[Tuple[str, float]],
) -> float:
    """
    关键词打分：整词命中任一 exact_fields 字段即按对应权重累加；
    整词一个都没命中时，退化为 2~3 字 n-gram 近似匹配，按 ngram_fields 权重累加
    （同一个 gram 只计一次，避免重复加分）。
    """
    lower_exact = [(text or "").lower() for text, _ in exact_fields]
    lower_ngram = [(text or "").lower() for text, _ in ngram_fields]

    score = 0.0
    matched_ngrams = set()
    for tok in tokens:
        t = (tok or "").lower()
        if not t:
            continue

        # 整词精确命中（最高权重，可同时命中多个字段）
        hit = False
        for (_, weight), low in zip(exact_fields, lower_exact):
            if t in low:
                score += weight
                hit = True
        if hit:
            continue

        # 字符级 n-gram 部分匹配 —— 处理"西红柿鸡蛋" ≈ "西红柿炒鸡蛋" 这种情况
        for n in (2, 3):
            if len(t) < n:
                continue
            for i in range(len(t) - n + 1):
                gram = t[i:i + n]
                if gram in matched_ngrams:
                    continue
                gram_score = 0.0
                for (_, weight), low in zip(ngram_fields, lower_ngram):
                    if gram in low:
                        gram_score += weight
                if gram_score > 0:
                    matched_ngrams.add(gram)
                    score += gram_score

    return score