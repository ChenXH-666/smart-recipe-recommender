"""
Rerank 精排评测脚本 v3 —— 论文实验：两阶段检索融合权重 α 参数扫描

遵循 rag-eval 科研评测规范（.trae/skills/rag-eval）：
  - 基线 + 消融 + 参数敏感性三合一：α∈{0, 0.3, 0.5, 0.7, 1.0}，
    α=0 即纯 Embedding 召回排序基线，α=1 即纯精排消融，中间为融合。
  - 同分复用：每条查询只调 1 次 Rerank API，各 α 在本地重算（控制成本与抖动）。
  - 分层汇报：全量平均 + 命中子集（相关菜已进候选池的查询）+ 按查询类型分组，
    把"第一级召回失败"与"排序质量差"两类问题分开。
  - 论文输出：结果同时打印并保存为 Markdown（可直接粘进论文）与 JSON（复算用）。

用法（先 conda activate food；须访问真实 Chroma 与 SiliconFlow，须先停后端）：
    cd backend
    python import_data/eval_rerank.py --dump-titles   # 打印库内菜名（标注辅助）
    python import_data/eval_rerank.py                 # 跑 α 扫描实验
    python import_data/eval_rerank.py -k 12           # 改截断 K
    python import_data/eval_rerank.py --alphas 0,0.5  # 只跑部分 α

评测集格式（category ∈ exact/cuisine/scenario/budget）：
    [{"category": "exact", "query": "...", "relevant_titles": ["..."]}]

指标：Recall@K / MRR / NDCG@K / 池命中数。K 默认取生产候选池上限
（RAG_CHAT_MAX_DISHES），保证评测与线上链路一致。
"""

import sys
import json
import math
import argparse
import logging
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.config import get_settings
from app.database import SessionLocal
from app.models import Recipe
from app.services.rag_service import (
    rag_search,
    _rerank_pool_scores,
    _fusion_sorted_pool,
    _get_popular_recipe_ids,
    _extract_budget,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("eval_rerank")
settings = get_settings()

DEFAULT_CASES = Path(__file__).parent / "eval_rerank_cases.json"
RESULT_MD = Path(__file__).parent / "eval_rerank_results.md"
RESULT_JSON = Path(__file__).parent / "eval_rerank_results.json"

# 参数敏感性扫描点：0=基线（纯召回序），1=纯精排（消融），中间=融合
DEFAULT_ALPHAS = [0.0, 0.3, 0.5, 0.7, 1.0]

CATEGORY_CN = {
    "exact": "精确型（菜名）",
    "cuisine": "类别型（菜系/主题）",
    "scenario": "场景意图型",
    "budget": "约束型（预算）",
}


# ------------------------------ 检索质量指标 ------------------------------

def recall_at_k(ranked: list, relevant: set, k: int) -> float:
    if not relevant:
        return 0.0
    return len(set(ranked[:k]) & relevant) / len(relevant)


def mrr(ranked: list, relevant: set) -> float:
    for i, item in enumerate(ranked, 1):
        if item in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(ranked: list, relevant: set, k: int) -> float:
    dcg = sum(
        1.0 / math.log2(i + 1)
        for i, item in enumerate(ranked[:k], 1)
        if item in relevant
    )
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0


def evaluate_ordering(ranked_ids: list, id2title: dict, relevant_ids: set, k: int) -> dict:
    ranked = [id2title[rid] for rid in ranked_ids if rid in id2title]
    relevant = {id2title[rid] for rid in relevant_ids if rid in id2title}
    return {
        "recall": recall_at_k(ranked, relevant, k),
        "mrr": mrr(ranked, relevant),
        "ndcg": ndcg_at_k(ranked, relevant, k),
        "hits": len(set(ranked) & relevant),
        "rel_total": len(relevant),
    }


# ------------------------------ 生产链路复现 ------------------------------

def get_base_pool(query: str, db):
    """第一级：向量召回 + 去重 + 热门兜底（与生产 build_recipe_pool_context 一致）。

    返回 (pool, recipes)；pool 为召回原序的菜谱 ID 列表（不被后续排序修改）。
    """
    results = rag_search(
        query, top_k=settings.RAG_CHAT_RECALL_K, filter_source_type="recipe"
    )
    pool, seen = [], set()
    for r in results:
        rid = r.get("source_id")
        if rid and rid not in seen:
            seen.add(rid)
            pool.append(rid)
    if not pool:
        return [], {}

    if len(pool) < settings.RAG_CHAT_MAX_DISHES:
        fill = _get_popular_recipe_ids(
            db, limit=settings.RAG_CHAT_MAX_DISHES + 16, exclude=set(pool)
        )
        for rid in fill:
            if rid not in seen:
                seen.add(rid)
                pool.append(rid)
            if len(pool) >= settings.RAG_CHAT_MAX_DISHES + 8:
                break

    recipes = {r.id: r for r in db.query(Recipe).filter(Recipe.id.in_(pool)).all()}
    return pool, recipes


def finalize_pool(query: str, pool: list, recipes: dict, scores, alpha: float) -> list:
    """第二级（按指定 α）：分数融合 → 预算分组 → 截断前 K（与生产一致）。"""
    p = pool
    if scores:
        p = _fusion_sorted_pool(p, recipes, scores, alpha=alpha)

    budget = _extract_budget(query)
    if budget is not None:
        def _cost(rid: int) -> float:
            r = recipes.get(rid)
            return float(r.estimated_cost) if r and r.estimated_cost else float("inf")

        in_ids = [rid for rid in p if _cost(rid) <= budget]
        over_ids = [rid for rid in p if _cost(rid) > budget]
        p = in_ids + over_ids

    return p[: settings.RAG_CHAT_MAX_DISHES]


# ------------------------------ 输出渲染 ------------------------------

def fmt(x: float) -> str:
    return f"{x:.3f}"


def render_main_table(rows_per_alpha: dict, alphas: list, k: int, subset_name: str) -> str:
    """渲染主结果表（Markdown）。rows_per_alpha: α → [row,...]（行=指标字典）"""
    lines = [
        f"**{subset_name}**",
        "",
        f"| 方法（α） | Recall@{k} | MRR | NDCG@{k} |",
        "|---|---|---|---|",
    ]
    for a in alphas:
        rows = rows_per_alpha[a]
        if not rows:
            continue
        n = len(rows)
        avg = {key: sum(r["metrics"][key] for r in rows) / n
               for key in ("recall", "mrr", "ndcg")}
        label = (
            "基线（纯 Embedding 召回序）" if a == 0.0
            else f"纯精排（bge-reranker 重排）" if a == 1.0
            else f"融合排序（α={a}）"
        )
        lines.append(
            f"| {label} | {fmt(avg['recall'])} | {fmt(avg['mrr'])} | {fmt(avg['ndcg'])} |"
        )
    return "\n".join(lines)


def render_category_table(all_rows: list, alphas: list, k: int) -> str:
    """渲染分组分析表：行=α，列=各查询类型的三指标。"""
    cats = [c for c in ("exact", "cuisine", "scenario", "budget")
            if any(r["category"] == c for r in all_rows)]
    header = "| 方法（α） |"
    sep = "|---|"
    for c in cats:
        header += f" {CATEGORY_CN[c]} R@{k}/MRR/NDCG |"
        sep += "---|"
    lines = [header, sep]
    for a in alphas:
        rows_a = [r for r in all_rows if r["alpha"] == a]
        if not rows_a:
            continue
        label = ("基线" if a == 0.0 else f"α={a}")
        cells = []
        for c in cats:
            cr = [r for r in rows_a if r["category"] == c]
            if not cr:
                cells.append("—")
                continue
            m = len(cr)
            avg = {key: sum(r["metrics"][key] for r in cr) / m
                   for key in ("recall", "mrr", "ndcg")}
            cells.append(f"{fmt(avg['recall'])} / {fmt(avg['mrr'])} / {fmt(avg['ndcg'])}")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def render_detail_table(all_rows: list, alphas: list, k: int) -> str:
    """逐条明细（含池命中诊断），仅展示基线与推荐配置 α=0.5。"""
    show = [a for a in alphas if a in (0.0, 0.5)] or alphas[:2]
    header = f"| 查询 | 类型 | 池命中/总相关 |"
    sep = "|---|---|---|"
    for a in show:
        header += f" R@{k}(α={a}) | MRR(α={a}) | NDCG(α={a}) |"
        sep += "---|---|---|"
    lines = [header, sep]
    for r in all_rows:
        if r["alpha"] != show[0]:
            continue
        cells = [
            r["query"], r["category"],
            f"{r['metrics']['hits']}/{r['metrics']['rel_total']}",
        ]
        for a in show:
            m = next((x["metrics"] for x in all_rows
                      if x["query"] == r["query"] and x["alpha"] == a), None)
            cells.append(fmt(m["recall"]) if m else "—")
            cells.append(fmt(m["mrr"]) if m else "—")
            cells.append(fmt(m["ndcg"]) if m else "—")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


# ------------------------------ 主流程 ------------------------------

def dump_titles(db) -> None:
    recipes = (
        db.query(Recipe)
        .filter(Recipe.status == "approved", Recipe.is_deleted == 0)
        .order_by(Recipe.id)
        .all()
    )
    print(f"\n库内已上架菜谱共 {len(recipes)} 道：\n")
    for r in recipes:
        cost = f"{r.estimated_cost}元" if r.estimated_cost else "待定"
        print(f"  [{r.id:>4}] {r.title}（成本：{cost}）")
    print()


def load_cases(path: Path) -> list:
    if not path.exists():
        print(f"评测集文件不存在：{path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = argparse.ArgumentParser(description="Rerank 精排论文评测（α 扫描）")
    parser.add_argument("--cases", type=str, default=str(DEFAULT_CASES))
    parser.add_argument("--dump-titles", action="store_true")
    parser.add_argument("-k", type=int, default=settings.RAG_CHAT_MAX_DISHES)
    parser.add_argument("--alphas", type=str, default=",".join(str(a) for a in DEFAULT_ALPHAS),
                        help="逗号分隔的 α 扫描点（默认 0,0.3,0.5,0.7,1.0）")
    args = parser.parse_args()
    alphas = [float(x) for x in args.alphas.split(",") if x.strip() != ""]

    db = SessionLocal()
    try:
        if args.dump_titles:
            dump_titles(db)
            return

        approved = (
            db.query(Recipe)
            .filter(Recipe.status == "approved", Recipe.is_deleted == 0)
            .all()
        )
        id2title = {r.id: r.title for r in approved}
        title2id = {r.title: r.id for r in approved}

        cases = load_cases(Path(args.cases))
        k = args.k
        print(f"\n评测集：{len(cases)} 条查询 | 截断 K={k} | α 扫描：{alphas} | "
              f"精排模型：{settings.RERANK_MODEL}\n")

        all_rows = []          # 每条 (query, category, alpha, metrics)
        rerank_fail = 0        # 精排未生效（降级）的查询数
        cat_stat = {c: 0 for c in CATEGORY_CN}
        # 池级命中：相关菜是否进入【截断前】候选池（与 α 无关，纯第一级召回判定）
        pool_hit_queries = set()
        pool_miss_queries = set()

        for case in cases:
            query = case["query"]
            category = case.get("category", "scenario")
            cat_stat[category] = cat_stat.get(category, 0) + 1
            relevant_ids = set()
            for title in case.get("relevant_titles", []):
                rid = title2id.get(title)
                if rid is None:
                    logger.warning(f"标注菜名不在库内，已忽略：{title}")
                else:
                    relevant_ids.add(rid)
            if not relevant_ids:
                logger.warning(f"查询「{query}」无有效标注，跳过")
                continue

            # 同分复用：召回池与精排分数各取一次，各 α 本地重算
            pool, recipes = get_base_pool(query, db)
            if set(pool) & relevant_ids:
                pool_hit_queries.add(query)
            else:
                pool_miss_queries.add(query)
            scores = _rerank_pool_scores(query, pool, recipes)
            if not scores:
                rerank_fail += 1

            for alpha in alphas:
                final = finalize_pool(query, pool, recipes, scores, alpha)
                metrics = evaluate_ordering(final, id2title, relevant_ids, k)
                all_rows.append({
                    "query": query, "category": category,
                    "alpha": alpha, "metrics": metrics,
                })

        valid_queries = {r["query"] for r in all_rows}
        n = len(valid_queries)
        if n == 0:
            print("没有可评测的查询")
            return

        # ---- 汇总：全量 / 命中子集（截断前池命中，与 α 无关） ----
        rows_per_alpha_full = {a: [r for r in all_rows if r["alpha"] == a] for a in alphas}
        rows_per_alpha_hit = {
            a: [r for r in all_rows if r["alpha"] == a and r["query"] in pool_hit_queries]
            for a in alphas
        }

        md = [
            f"# Rerank 精排实验结果（自动生成：{datetime.now().strftime('%Y-%m-%d %H:%M')}）",
            "",
            f"评测集 {n} 条查询（" + "、".join(
                f"{CATEGORY_CN[c]} {cat_stat[c]} 条"
                for c in ("exact", "cuisine", "scenario", "budget") if cat_stat.get(c)
            ) + f"）；截断 K={k}；精排模型 {settings.RERANK_MODEL}；"
            f"融合公式：最终分 = α×精排分 + (1−α)×召回位置分。",
            "",
            "## 1. 主结果（全量）",
            "",
            render_main_table(rows_per_alpha_full, alphas, k, "全量平均"),
            "",
            f"## 2. 主结果（命中子集，相关菜已进入候选池的 {len(pool_hit_queries)}/{n} 条）",
            "",
            render_main_table(rows_per_alpha_hit, alphas, k, "命中子集平均"),
            "",
            f"## 3. 参数敏感性（α 扫描，全量）",
            "",
            render_main_table(rows_per_alpha_full, alphas, k, "α 扫描（同表 1，用于曲线绘制）"),
            "",
            f"## 4. 分组分析（各查询类型，全量）",
            "",
            render_category_table(all_rows, alphas, k),
            "",
            f"## 5. 逐条明细（基线 vs 推荐 α=0.5）",
            "",
            render_detail_table(all_rows, alphas, k),
            "",
            "## 6. 诊断",
            "",
        ]
        recall_fail = n - len(pool_hit_queries)
        md.append(f"- 精排未生效（API 失败/降级）：{rerank_fail}/{n} 条"
                  f"{'（超过 10%，建议排查后重跑）' if rerank_fail > n * 0.1 else ''}")
        md.append(f"- 相关菜未进入候选池（第一级召回失败，截断前池判定）：{recall_fail}/{n} 条，"
                  f"属双塔 Embedding 对场景意图型查询的召回局限，精排无法补救。"
                  if pool_miss_queries else
                  f"- 相关菜未进入候选池：0/{n} 条，第一级召回全部成功。")
        md.append("")

        text = "\n".join(md)
        print(text)
        RESULT_MD.write_text(text, encoding="utf-8")
        RESULT_JSON.write_text(
            json.dumps(all_rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"结果已保存：{RESULT_MD}\n               {RESULT_JSON}\n")
    finally:
        db.close()


if __name__ == "__main__":
    main()
