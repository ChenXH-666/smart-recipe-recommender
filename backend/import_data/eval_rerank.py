"""
Rerank 精排评测脚本 v5 —— 论文实验：召回模式（纯向量 / 混合+RRF / 混合+查询改写）× 融合权重 α 扫描

遵循 rag-eval 科研评测规范（.trae/skills/rag-eval）：
  - 基线 + 消融 + 参数敏感性三合一：
      召回模式 ∈ {vector: 纯向量召回（原链路）,
                  hybrid: 混合召回（向量+BM25，RRF 融合）,
                  hybrid_rw: 混合召回 + 查询改写（无实体词查询经 LLM 改写后双查询召回 RRF 融合）}
      α ∈ {0, 0.3, 0.5, 0.7, 1.0}，α=0 即纯召回排序基线，α=1 即纯精排消融，中间为融合。
  - 同分复用：每条查询每个召回模式只调 1 次 Rerank API，各 α 在本地重算（控制成本与抖动）；
    查询改写同样每条查询只调 1 次 LLM，所有模式共用同一改写结果。
  - 分层汇报：全量平均 + 命中子集（相关菜已进候选池的查询）+ 按查询类型分组，
    把"第一级召回失败"与"排序质量差"两类问题分开。
  - 论文输出：结果同时打印并保存为 Markdown（可直接粘进论文）与 JSON（复算用），
    并附"查询改写记录"（触发与否 / 改写文本 / LLM 耗时，作为改写效果的直接证据）。
  - 数据一致性：文档/论文引用时**以同一次运行的结果为准**。默认一次跑完全部召回模式，
    输出文件即为该批数据；不同日期分别跑出的结果会因库内向量数据变化与精排服务
    抖动而存在末位差异（≤0.01），混用会让同一配置在文中出现两个数字，故不应混用。

用法（先 conda activate food；须访问真实 Chroma 与 SiliconFlow/LLM，须先停后端）：
    cd backend
    python import_data/eval_rerank.py --dump-titles          # 打印库内菜名（标注辅助）
    python import_data/eval_rerank.py                        # 全模式实验（默认含 hybrid_rw）
    python import_data/eval_rerank.py -k 12                  # 改截断 K
    python import_data/eval_rerank.py --alphas 0,0.5         # 只跑部分 α
    python import_data/eval_rerank.py --modes vector,hybrid   # 只跑旧对照（复现历史结果）
    python import_data/eval_rerank.py --modes hybrid,hybrid_rw --out-prefix eval_rewrite
                                                              # 混合召回 vs 查询改写对照
    python import_data/eval_rerank.py --out-prefix eval_hybrid  # 指定输出文件名前缀

评测集格式（category ∈ exact/cuisine/scenario/budget）：
    [{"category": "exact", "query": "...", "relevant_titles": ["..."]}]

指标：Recall@K / MRR / NDCG@K / 池命中数。K 默认取生产候选池上限
（RAG_CHAT_MAX_DISHES），保证评测与线上链路一致。
"""

import sys
import json
import math
import time
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
    plan_query_rewrite,
    query_has_library_entity,
    REWRITE_MIN_ENTITY_LEN,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("eval_rerank")
settings = get_settings()

DEFAULT_CASES = Path(__file__).parent / "eval_rerank_cases.json"

# 参数敏感性扫描点：0=基线（纯召回序），1=纯精排（消融），中间=融合
DEFAULT_ALPHAS = [0.0, 0.3, 0.5, 0.7, 1.0]

# 召回模式：vector=纯向量（原链路），hybrid=混合召回（向量+BM25，RRF 融合），
# hybrid_rw=混合召回+查询改写（改写查询与原查询双路召回，RRF 融合）
DEFAULT_MODES = ["vector", "hybrid", "hybrid_rw"]

CATEGORY_CN = {
    "exact": "精确型（菜名）",
    "cuisine": "类别型（菜系/主题）",
    "scenario": "场景意图型",
    "budget": "约束型（预算）",
}

MODE_CN = {
    "vector": "纯向量召回",
    "hybrid": "混合召回（向量+BM25，RRF）",
    "hybrid_rw": "混合召回+查询改写（双查询 RRF）",
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

def get_base_pool(query: str, db, hybrid: bool = False, rewritten_query: str = None):
    """第一级：召回 + 去重 + 热门兜底（与生产 build_recipe_pool_context 一致）。

    hybrid=False 走纯向量召回（原链路）；hybrid=True 走混合召回
    （向量 + BM25 双通道，RRF 融合）—— 通过 rag_search 的 hybrid 参数
    显式控制，不受 RAG_HYBRID_SEARCH 环境配置影响，保证对照实验可比。

    rewritten_query 非空时，按生产链路执行"改写查询二次召回 + 双查询 RRF 融合"；
    改写文本由调用方每条查询只计算一次并注入（rewrite=False 保证不重复触发 LLM）。

    返回 (pool, recipes)；pool 为召回原序的菜谱 ID 列表（不被后续排序修改）。
    """
    results = rag_search(
        query, top_k=settings.RAG_CHAT_RECALL_K,
        filter_source_type="recipe", hybrid=hybrid,
        rewrite=False, rewritten_query=rewritten_query,
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

    # 与生产一致预加载标签/食材链路，避免精排文档构建时的 N+1 惰性查询
    from app.models import RecipeTag, RecipeIngredient
    from sqlalchemy.orm import joinedload, selectinload
    recipes = {
        r.id: r for r in db.query(Recipe)
        .options(
            joinedload(Recipe.tags).joinedload(RecipeTag.tag),
            selectinload(Recipe.ingredients).joinedload(RecipeIngredient.ingredient),
        )
        .filter(Recipe.id.in_(pool))
        .all()
    }
    return pool, recipes


def finalize_pool(query: str, pool: list, recipes: dict, scores, alpha: float) -> list:
    """第二级（按指定 α）：分数融合 → 预算分组 → 截断前 K（与生产一致）。

    生产分支语义：融合生效（有分数且 α>0）→ 预算分组组内保持融合相关度序；
    未融合（scores 为 None 或 α=0）→ 组内按成本升序（与生产基线一致，
    保证实验 α=0 行完全等于"关闭精排"的线上行为）。
    """
    applied = bool(scores) and alpha > 0
    p = pool
    if applied:
        p = _fusion_sorted_pool(p, recipes, scores, alpha=alpha)

    budget = _extract_budget(query)
    if budget is not None:
        def _cost(rid: int) -> float:
            r = recipes.get(rid)
            return float(r.estimated_cost) if r and r.estimated_cost else float("inf")

        in_ids = [rid for rid in p if _cost(rid) <= budget]
        over_ids = [rid for rid in p if _cost(rid) > budget]
        if applied:
            p = in_ids + over_ids
        else:
            p = sorted(in_ids, key=_cost) + sorted(over_ids, key=_cost)

    return p[: settings.RAG_CHAT_MAX_DISHES]


# ------------------------------ 输出渲染 ------------------------------

def fmt(x: float) -> str:
    return f"{x:.3f}"


def config_label(mode: str, alpha: float) -> str:
    """行标签：召回模式 × 融合权重"""
    a_part = (
        "基线（α=0）" if alpha == 0.0
        else "纯精排（α=1）" if alpha == 1.0
        else f"融合（α={alpha}）"
    )
    return f"{MODE_CN[mode]}｜{a_part}"


def render_main_table(rows_per_key: dict, keys: list, k: int, subset_name: str) -> str:
    """渲染主结果表（Markdown）。rows_per_key: (mode, alpha) → [row,...]（行=指标字典）"""
    lines = [
        f"**{subset_name}**",
        "",
        f"| 方法（召回模式 × α） | Recall@{k} | MRR | NDCG@{k} |",
        "|---|---|---|---|",
    ]
    for key in keys:
        rows = rows_per_key.get(key) or []
        if not rows:
            continue
        n = len(rows)
        avg = {m: sum(r["metrics"][m] for r in rows) / n
               for m in ("recall", "mrr", "ndcg")}
        lines.append(
            f"| {config_label(*key)} | {fmt(avg['recall'])} | {fmt(avg['mrr'])} | {fmt(avg['ndcg'])} |"
        )
    return "\n".join(lines)


def render_category_table(all_rows: list, keys: list, k: int) -> str:
    """渲染分组分析表：行=召回模式×α，列=各查询类型的三指标。"""
    cats = [c for c in ("exact", "cuisine", "scenario", "budget")
            if any(r["category"] == c for r in all_rows)]
    header = "| 方法（召回模式 × α） |"
    sep = "|---|"
    for c in cats:
        header += f" {CATEGORY_CN[c]} R@{k}/MRR/NDCG |"
        sep += "---|"
    lines = [header, sep]
    for key in keys:
        mode, alpha = key
        rows_k = [r for r in all_rows
                  if r["mode"] == mode and r["alpha"] == alpha]
        if not rows_k:
            continue
        cells = []
        for c in cats:
            cr = [r for r in rows_k if r["category"] == c]
            if not cr:
                cells.append("—")
                continue
            m = len(cr)
            avg = {metric: sum(r["metrics"][metric] for r in cr) / m
                   for metric in ("recall", "mrr", "ndcg")}
            cells.append(f"{fmt(avg['recall'])} / {fmt(avg['mrr'])} / {fmt(avg['ndcg'])}")
        lines.append(f"| {config_label(mode, alpha)} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def render_detail_table(all_rows: list, keys: list, k: int) -> str:
    """逐条明细（含池命中诊断）：纯向量基线 / 混合 α=0.5 / 混合+改写 α=0.5。"""
    show = [key for key in keys
            if key in (("vector", 0.0), ("hybrid", 0.5), ("hybrid_rw", 0.5))]
    if not show:
        show = keys[:2]
    header = f"| 查询 | 类型 | 池命中/总相关 |"
    sep = "|---|---|---|"
    for key in show:
        short = f"{key[0]}/α={key[1]}"
        header += f" R@{k}({short}) | MRR({short}) | NDCG({short}) |"
        sep += "---|---|---|"
    lines = [header, sep]
    first_key = show[0]
    for r in [x for x in all_rows
              if x["mode"] == first_key[0] and x["alpha"] == first_key[1]]:
        cells = [
            r["query"], r["category"],
            f"{r['metrics']['hits']}/{r['metrics']['rel_total']}",
        ]
        for key in show:
            m = next((x["metrics"] for x in all_rows
                      if x["query"] == r["query"] and x["mode"] == key[0]
                      and x["alpha"] == key[1]), None)
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
    parser = argparse.ArgumentParser(description="混合召回 + Rerank 精排论文评测（召回模式 × α 扫描）")
    parser.add_argument("--cases", type=str, default=str(DEFAULT_CASES))
    parser.add_argument("--dump-titles", action="store_true")
    parser.add_argument("-k", type=int, default=settings.RAG_CHAT_MAX_DISHES)
    parser.add_argument("--alphas", type=str, default=",".join(str(a) for a in DEFAULT_ALPHAS),
                        help="逗号分隔的 α 扫描点（默认 0,0.3,0.5,0.7,1.0）")
    parser.add_argument("--modes", type=str, default=",".join(DEFAULT_MODES),
                        help="逗号分隔的召回模式（vector=纯向量，hybrid=混合+RRF，"
                             "hybrid_rw=混合+查询改写；默认三者）")
    parser.add_argument("--out-prefix", type=str, default="eval_rerank",
                        help="结果文件名前缀（改写实验建议 eval_rewrite，避免覆盖旧结果）")
    args = parser.parse_args()
    alphas = [float(x) for x in args.alphas.split(",") if x.strip() != ""]
    modes = [m.strip() for m in args.modes.split(",") if m.strip()]
    for m in modes:
        if m not in MODE_CN:
            parser.error(f"未知召回模式：{m}（可选 vector / hybrid / hybrid_rw）")

    db = SessionLocal()
    try:
        if args.dump_titles:
            dump_titles(db)
            return

        result_md = Path(__file__).parent / f"{args.out_prefix}_results.md"
        result_json = Path(__file__).parent / f"{args.out_prefix}_results.json"

        approved = (
            db.query(Recipe)
            .filter(Recipe.status == "approved", Recipe.is_deleted == 0)
            .all()
        )
        id2title = {r.id: r.title for r in approved}
        title2id = {r.title: r.id for r in approved}

        cases = load_cases(Path(args.cases))
        k = args.k
        keys = [(m, a) for m in modes for a in alphas]
        print(f"\n评测集：{len(cases)} 条查询 | 截断 K={k} | 召回模式：{modes} | "
              f"α 扫描：{alphas} | 精排模型：{settings.RERANK_MODEL}\n")

        all_rows = []          # 每条 (query, category, mode, alpha, metrics)
        rerank_fail = 0        # 精排未生效（降级）的 (查询, 模式) 数
        cat_stat = {c: 0 for c in CATEGORY_CN}
        # 池级命中：相关菜是否进入【截断前】候选池（与 α 无关，按召回模式分别判定）
        pool_hit_queries = {m: set() for m in modes}
        rw_records = []        # 查询改写记录：触发与否 / 改写文本 / LLM 耗时
        need_rewrite = "hybrid_rw" in modes

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

            # 查询改写：每条查询只调 1 次 LLM，所有模式复用同一改写结果（rewrite 模式专用）
            rewritten = None
            if need_rewrite:
                triggered = not query_has_library_entity(query)
                t0 = time.perf_counter()
                rewritten = plan_query_rewrite(query)
                elapsed_ms = (time.perf_counter() - t0) * 1000
                status = ("改写成功" if rewritten
                          else "未触发（已含实体词）" if not triggered
                          else "回退原查询（失败/校验未过）")
                rw_records.append({
                    "query": query, "category": category, "triggered": triggered,
                    "status": status, "rewritten": rewritten,
                    "latency_ms": round(elapsed_ms, 1),
                })

            # 同分复用：每个召回模式各取一次召回池与精排分数，各 α 本地重算
            for mode in modes:
                pool, recipes = get_base_pool(
                    query, db,
                    hybrid=(mode in ("hybrid", "hybrid_rw")),
                    rewritten_query=(rewritten if mode == "hybrid_rw" else None),
                )
                if set(pool) & relevant_ids:
                    pool_hit_queries[mode].add(query)
                scores = _rerank_pool_scores(query, pool, recipes)
                if not scores:
                    rerank_fail += 1

                for alpha in alphas:
                    final = finalize_pool(query, pool, recipes, scores, alpha)
                    metrics = evaluate_ordering(final, id2title, relevant_ids, k)
                    all_rows.append({
                        "query": query, "category": category, "mode": mode,
                        "alpha": alpha, "metrics": metrics,
                    })

        valid_queries = {r["query"] for r in all_rows}
        n = len(valid_queries)
        if n == 0:
            print("没有可评测的查询")
            return

        # ---- 汇总：全量 / 命中子集（截断前池命中，与 α 无关） ----
        rows_per_key_full = {
            key: [r for r in all_rows if (r["mode"], r["alpha"]) == key]
            for key in keys
        }
        rows_per_key_hit = {
            key: [r for r in all_rows
                  if (r["mode"], r["alpha"]) == key and r["query"] in pool_hit_queries[r["mode"]]]
            for key in keys
        }

        md = [
            f"# 混合召回 + Rerank 精排实验结果（自动生成：{datetime.now().strftime('%Y-%m-%d %H:%M')}）",
            "",
            f"评测集 {n} 条查询（" + "、".join(
                f"{CATEGORY_CN[c]} {cat_stat[c]} 条"
                for c in ("exact", "cuisine", "scenario", "budget") if cat_stat.get(c)
            ) + f"）；截断 K={k}；精排模型 {settings.RERANK_MODEL}。",
            "召回模式：" + " / ".join(MODE_CN[m] for m in modes)
            + f"（RRF k={settings.RAG_HYBRID_RRF_K}；查询改写触发条件：与全库菜名无 "
              f"{REWRITE_MIN_ENTITY_LEN} 字以上连续命中）。",
            f"融合公式：最终分 = α×精排分 + (1−α)×召回位置分。",
            "",
            "## 1. 主结果（全量）",
            "",
            render_main_table(rows_per_key_full, keys, k, "全量平均"),
            "",
            f"## 2. 主结果（命中子集，相关菜已进入候选池的查询，按召回模式分别判定）",
            "",
        ]
        for m in modes:
            md.append(render_main_table(
                {key: rows for key, rows in rows_per_key_hit.items() if key[0] == m},
                [key for key in keys if key[0] == m], k,
                f"{MODE_CN[m]}（命中 {len(pool_hit_queries[m])}/{n} 条）",
            ))
            md.append("")
        md += [
            f"## 3. 参数敏感性（α 扫描，全量）",
            "",
            render_main_table(rows_per_key_full, keys, k, "α 扫描（同表 1，用于曲线绘制）"),
            "",
            f"## 4. 分组分析（各查询类型，全量）",
            "",
            render_category_table(all_rows, keys, k),
            "",
            f"## 5. 逐条明细（纯向量基线 vs 混合召回 vs 混合+查询改写）",
            "",
            render_detail_table(all_rows, keys, k),
            "",
            "## 6. 诊断",
            "",
        ]
        recall_fail = {m: n - len(pool_hit_queries[m]) for m in modes}
        md.append(f"- 精排未生效（API 失败/降级）：{rerank_fail}/{n * len(modes)} 次"
                  f"{'（超过 10%，建议排查后重跑）' if rerank_fail > n * len(modes) * 0.1 else ''}")
        for m in modes:
            tag = MODE_CN[m]
            if recall_fail[m]:
                md.append(f"- {tag}：相关菜未进入候选池 {recall_fail[m]}/{n} 条（第一级召回失败，"
                          f"截断前池判定，精排无法补救）。")
            else:
                md.append(f"- {tag}：相关菜未进入候选池 0/{n} 条，第一级召回全部成功。")
        md.append("")

        # ---- 查询改写记录（hybrid_rw 模式；触发与否 / 改写文本 / LLM 耗时） ----
        md += ["## 7. 查询改写记录", ""]
        if rw_records:
            trig = [r for r in rw_records if r["triggered"]]
            ok = [r for r in rw_records if r["rewritten"]]
            lat = [r["latency_ms"] for r in ok]
            md.append(
                f"- 触发改写判定：{len(trig)}/{len(rw_records)} 条"
                f"（其余查询已含库内菜名实体词，跳过、零 LLM 调用开销）；"
                f"改写成功 {len(ok)} 条、回退原查询 {len(trig) - len(ok)} 条。"
            )
            if lat:
                md.append(
                    f"- 改写 LLM 调用耗时（仅成功条数）：平均 {sum(lat) / len(lat):.0f} ms，"
                    f"区间 {min(lat):.0f}~{max(lat):.0f} ms"
                    f"（该开销位于召回前置，同步计入 AI 对话首包延迟）。"
                )
            md += ["", "| 查询 | 类型 | 是否触发 | 结果 | 改写文本 | LLM 耗时(ms) |",
                   "|---|---|---|---|---|---|"]
            for r in rw_records:
                md.append(
                    f"| {r['query']} | {r['category']} | {'是' if r['triggered'] else '否'} | "
                    f"{r['status']} | {r['rewritten'] or '—'} | {r['latency_ms']:.0f} |"
                )
        else:
            md.append("（本次未包含 hybrid_rw 模式，无查询改写记录）")
        md.append("")

        text = "\n".join(md)
        print(text)
        result_md.write_text(text, encoding="utf-8")
        result_json.write_text(
            json.dumps({"rows": all_rows, "rewrite_records": rw_records},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"结果已保存：{result_md}\n               {result_json}\n")
    finally:
        db.close()


if __name__ == "__main__":
    main()
