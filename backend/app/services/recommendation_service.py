"""推荐引擎"""

import logging
import re
from typing import List, Dict, Optional, Tuple
from sqlalchemy.orm import Session, joinedload

from app.models import (
    Recipe, MealPlan, MealPlanItem, UserFavorite, UserBrowseHistory, RecipeTag,
    Tag, RecipeReview,
)
from app.schemas.interaction import MealPlanListOut
from app.services.rag_service import rag_search
from app.services.ai_service import generate_recommendation_text

logger = logging.getLogger(__name__)

# 通用"猜你想问"预设备题 —— 无个性化数据或未登录时兜底使用
GENERIC_PROMPTS = [
    {"label": "减脂晚餐", "prompt": "帮我推荐几道适合减脂的晚餐，健康又美味"},
    {"label": "快手家常菜", "prompt": "我想做几道快手家常菜，简单省时"},
    {"label": "川菜", "prompt": "我想吃川菜，帮我推荐几道正宗又好吃的"},
    {"label": "高蛋白", "prompt": "帮我推荐几道高蛋白的菜"},
    {"label": "50元以内", "prompt": "我想在50元以内做一顿二人餐，帮我搭配"},
]


# 过于宽泛、不适合作为"猜你想问"标签的标签名（生成个性化提问时跳过）
GENERIC_TAG_BLACKLIST = {
    "中式", "家常菜", "家常", "快手菜", "美食", "菜品", "菜肴",
    "简单", "好吃", "营养", "热菜", "凉菜", "素食", "荤菜",
}


def _prompt_for_tag(ttype: Optional[str], name: str) -> str:
    """按标签类型生成对应的自然语言提问模板"""
    t = (ttype or "").lower()
    if "cuisine" in t:
        return f"我想吃{name}，帮我推荐几道正宗又好吃的"
    if "dish_type" in t:
        return f"帮我推荐几道{name}的菜"
    if "cooking_method" in t:
        return f"推荐几道{name}菜"
    if "occasion" in t:
        return f"推荐适合{name}吃的菜"
    if "dietary" in t:
        return f"推荐几道{name}的菜"
    if "season" in t:
        return f"推荐适合{name}的菜"
    # 兜底：避免出现"下饭菜的菜/硬菜的菜"这类叠字
    if name.endswith("菜"):
        return f"推荐几道{name}"
    return f"推荐几道{name}的菜"


def get_personalized_prompts(
    user_id: int,
    db: Session,
    limit: int = 6,
) -> List[Dict]:
    """根据用户行为（收藏/浏览/带评分点评）+ RAG 语义，生成个性化"猜你想问"预设备题

    加权评估（综合"点赞/收藏/评论/浏览"）：
      - 收藏菜谱：权重 3
      - 浏览历史：权重 1
      - 点评菜谱：权重 2 × 评分/5（5 分最重，未评分按中性 0.6）
    再将这些高权菜谱的标签按权重累加，取最偏好的标签生成提问模板。
    RAG 增强：把偏好标签拼成查询做向量语义检索，把语义最相关菜的标签也计入，
    从而抓取"用户没直接点过、但口味相近"的偏好。RAG 异常时静默降级为纯行为版本。
    不足时用通用预设备题兜底，保证每个用户都能看到可点击的问题。
    """
    # 1) 综合加权：收藏 / 浏览历史 / 带评分点评
    recipe_weight: Dict[int, float] = {}

    def _add_weight(ids, w: float):
        for i in ids:
            if i is None:
                continue
            recipe_weight[i] = recipe_weight.get(i, 0.0) + w

    fav_ids = [
        f.favorite_id for f in
        db.query(UserFavorite).filter(
            UserFavorite.user_id == user_id,
            UserFavorite.favorite_type == "recipe",
        ).limit(50).all()
    ]
    _add_weight(fav_ids, 3.0)  # 收藏权重最高

    hist_ids = [
        h.recipe_id for h in
        db.query(UserBrowseHistory).filter(
            UserBrowseHistory.user_id == user_id,
            UserBrowseHistory.recipe_id.isnot(None),
        ).limit(60).all()
    ]
    _add_weight(hist_ids, 1.0)  # 浏览

    reviews = db.query(RecipeReview).filter(
        RecipeReview.user_id == user_id,
        RecipeReview.is_deleted == 0,
    ).limit(40).all()
    for r in reviews:
        # 按评分加权：5 分最重，未评分按中性 0.6
        _add_weight([r.recipe_id], 2.0 * ((r.rating or 3) / 5.0))

    # 2) 把高权菜谱的标签按权重累加
    tag_counts: Dict[tuple, float] = {}
    if recipe_weight:
        recipe_tags = db.query(RecipeTag).options(
            joinedload(RecipeTag.tag)
        ).filter(RecipeTag.recipe_id.in_(list(recipe_weight.keys()))).all()
        for rt in recipe_tags:
            tag = rt.tag
            if not tag or not tag.name:
                continue
            key = (tag.type or "", tag.name)
            tag_counts[key] = tag_counts.get(key, 0.0) + recipe_weight.get(rt.recipe_id, 0.0)

    # 3) RAG 语义增强：偏好标签拼查询 → 语义相关菜谱 → 再回填标签权重
    try:
        pref_names = [
            name for (_tt, name), _c in
            sorted(tag_counts.items(), key=lambda kv: kv[1], reverse=True)[:5]
        ]
        if pref_names:
            pref_query = " ".join(pref_names)
            rag_results = rag_search(pref_query, top_k=10, filter_source_type="recipe")
            rag_ids = [
                int(r["source_id"]) for r in rag_results
                if r.get("source_type") == "recipe" and r.get("source_id")
            ]
            if rag_ids:
                rag_tags = db.query(RecipeTag).options(
                    joinedload(RecipeTag.tag)
                ).filter(RecipeTag.recipe_id.in_(rag_ids)).all()
                for rt in rag_tags:
                    tag = rt.tag
                    if not tag or not tag.name:
                        continue
                    key = (tag.type or "", tag.name)
                    tag_counts[key] = tag_counts.get(key, 0.0) + 0.5
    except Exception as e:
        logger.debug(f"预设备题 RAG 增强失败，忽略: {e}")

    # 4) 按权重降序生成个性化提问（跳过过于宽泛的标签名）
    personalized: List[Dict] = []
    seen = set()
    for (ttype, name), cnt in sorted(tag_counts.items(), key=lambda kv: kv[1], reverse=True):
        if name in seen or name in GENERIC_TAG_BLACKLIST:
            continue
        prompt = _prompt_for_tag(ttype, name)
        personalized.append({"label": name, "prompt": prompt})
        seen.add(name)
        # 预留若干位置给通用预设备题（保证多样性）
        if len(personalized) >= max(0, limit - 2):
            break

    # 5) 标准况下保留 2 个通用位，其他用通用预设备题填充
    result = personalized
    for g in GENERIC_PROMPTS:
        if len(result) >= limit:
            break
        if g["label"] in seen:
            continue
        result.append(g)
        seen.add(g["label"])

    return result[:limit]


def _format_tags(recipe) -> List[Dict]:
    """统一标签格式为前端需要的对象数组 {id, name, type}"""
    return [
        {"id": t.tag.id, "name": t.tag.name, "type": t.tag.type}
        for t in recipe.tags
        if t.tag
    ]


def _db_keyword_fallback_recipes(
    query: str, db: Session, budget: Optional[float] = None, limit: int = 10
) -> List[Dict]:
    """
    关键词兜底推荐 —— 当 RAG 向量搜索不可用时，
    直接从 MySQL 按标题/描述的 n-gram 模糊匹配拉取菜谱。

    - 标题命中权重高于描述
    - 使用字符级 n-gram（2-3 字）处理近似匹配（如"西红柿鸡蛋"匹配"西红柿炒鸡蛋"）
    - 仍支持预算过滤
    """
    if not query:
        return []

    # 从查询中抽取关键词（去除常见标点与无关词）
    stopwords = {"推荐", "帮", "我", "的", "一个", "点", "些", "想", "要", "吃", "做", "个",
                 "便宜", "好吃", "简单", "点的", "来点", "今天", "请问", "有没有", "有什么"}
    raw_tokens = [t for t in re.split(r"[\s，。、；：,.;:!?()（）\[\]【】\"'《》]+", query) if t]
    tokens = [t for t in raw_tokens if t and t not in stopwords]
    if not tokens:
        tokens = raw_tokens or [query]

    # 先拿一批候选（状态正常 + 未删除 + 可选预算过滤）
    query_builder = db.query(Recipe).options(
        joinedload(Recipe.tags).joinedload(RecipeTag.tag)
    ).filter(
        Recipe.status == "approved",
        Recipe.is_deleted == 0,
    )
    if budget is not None:
        query_builder = query_builder.filter(
            (Recipe.estimated_cost.is_(None)) | (Recipe.estimated_cost <= budget)
        )
    candidates = query_builder.limit(300).all()

    # 关键词评分（支持 n-gram 近似匹配）
    def calc_score(recipe) -> float:
        title_low = (recipe.title or "").lower()
        desc_low = (recipe.description or "").lower()
        sc = 0.0
        matched = set()
        for tok in tokens:
            t = tok.lower()
            if not t:
                continue
            # 精确整词匹配（高权重）
            if t in title_low:
                sc += 3.0
            if t in desc_low:
                sc += 1.0
            # n-gram 近似匹配（仅当整词未命中时）
            if t not in title_low and t not in desc_low:
                for n in (2, 3):
                    if len(t) < n:
                        continue
                    for i in range(len(t) - n + 1):
                        gram = t[i:i + n]
                        if gram in matched:
                            continue
                        g_score = 0.0
                        if gram in title_low:
                            g_score += 0.6
                        if gram in desc_low:
                            g_score += 0.2
                        if g_score > 0:
                            matched.add(gram)
                            sc += g_score
        return sc

    scored = []
    for r in candidates:
        s = calc_score(r)
        if s > 0:
            scored.append((s, r))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [r for _, r in scored[:limit]]

    results = []
    for recipe in top:
        cost = float(recipe.estimated_cost) if recipe.estimated_cost else 0
        if budget is None or cost <= budget:
            results.append({
                "id": recipe.id,
                "title": recipe.title,
                "description": recipe.description,
                "cover_image_url": recipe.cover_image_url,
                "difficulty": recipe.difficulty,
                "cooking_time": recipe.cooking_time,
                "estimated_cost": cost,
                "type": "recipe",
                "similarity_score": round(1.0 - (len(results) / (limit + 1)), 3),
                "tags": _format_tags(recipe),
            })
    if restriction_set:
        from app.utils.recipe_diet import filter_recipe_ids
        allowed = filter_recipe_ids(db, [r["id"] for r in results], restriction_set)
        results = [r for r in results if r["id"] in allowed]
    return results


def extract_user_preferences(user_id: int, db: Session) -> List[int]:
    """从用户历史里扒拉出偏好标签"""
    tag_ids = []

    # 从收藏的菜谱提取标签
    fav_recipe_ids = [
        f.favorite_id for f in
        db.query(UserFavorite).filter(
            UserFavorite.user_id == user_id,
            UserFavorite.favorite_type == "recipe",
        ).limit(20).all()
    ]
    if fav_recipe_ids:
        recipe_tags = db.query(RecipeTag).filter(RecipeTag.recipe_id.in_(fav_recipe_ids)).all()
        tag_ids.extend([rt.tag_id for rt in recipe_tags])

    # 从浏览历史提取标签
    history_recipe_ids = [
        h.recipe_id for h in
        db.query(UserBrowseHistory).filter(
            UserBrowseHistory.user_id == user_id,
            UserBrowseHistory.recipe_id.isnot(None),
        ).limit(30).all()
    ]
    if history_recipe_ids:
        history_tags = db.query(RecipeTag).filter(RecipeTag.recipe_id.in_(history_recipe_ids)).all()
        tag_ids.extend([rt.tag_id for rt in history_tags])

    return list(set(tag_ids))


def get_personalized_recommendations(
    user_id: int,
    db: Session,
    limit: int = 20,
    restriction_set: Optional[set] = None,
) -> List[Dict]:
    """个性推荐：根据用户历史推荐菜谱

    策略说明：
    - 无浏览/收藏历史：直接返回热门菜谱
    - 有历史：基于偏好标签推荐；若标签匹配结果不足 limit 数量，用热门菜谱补齐
    - 补齐时自动排除已在推荐列表中的菜谱，避免重复"""
    tag_ids = extract_user_preferences(user_id, db)
    if not tag_ids:
        # 无历史，返回热门菜谱
        recipes = (
            db.query(Recipe)
            .options(joinedload(Recipe.tags).joinedload(RecipeTag.tag))
            .filter(
                Recipe.status == "approved",
                Recipe.is_deleted == 0,
            )
            .order_by(Recipe.view_count.desc())
            .limit(limit)
            .all()
        )
    else:
        # 基于标签推荐
        recipe_ids = [
            rt.recipe_id for rt in
            db.query(RecipeTag).filter(
                RecipeTag.tag_id.in_(tag_ids),
            ).all()
        ]
        recipes = (
            db.query(Recipe)
            .options(joinedload(Recipe.tags).joinedload(RecipeTag.tag))
            .filter(
                Recipe.id.in_(recipe_ids),
                Recipe.status == "approved",
                Recipe.is_deleted == 0,
            )
            .order_by(Recipe.favorite_count.desc(), Recipe.view_count.desc())
            .limit(limit)
            .all()
        )

        # 关键修复：如果标签匹配结果不足，用热门菜谱补齐
        if len(recipes) < limit:
            existing_ids = {r.id for r in recipes}
            fill_count = limit - len(recipes)
            extra_recipes = (
                db.query(Recipe)
                .options(joinedload(Recipe.tags).joinedload(RecipeTag.tag))
                .filter(
                    Recipe.id.notin_(existing_ids),
                    Recipe.status == "approved",
                    Recipe.is_deleted == 0,
                )
                .order_by(Recipe.view_count.desc())
                .limit(fill_count)
                .all()
            )
            recipes.extend(extra_recipes)

    results = []
    for r in recipes:
        results.append({
            "id": r.id,
            "title": r.title,
            "description": r.description,
            "cover_image_url": r.cover_image_url,
            "difficulty": r.difficulty,
            "cooking_time": r.cooking_time,
            "estimated_cost": float(r.estimated_cost) if r.estimated_cost else 0,
            "view_count": r.view_count,
            "favorite_count": r.favorite_count,
            "tags": _format_tags(r),
        })
    if restriction_set:
        from app.utils.recipe_diet import filter_recipe_ids
        allowed = filter_recipe_ids(db, [r["id"] for r in results], restriction_set)
        results = [r for r in results if r["id"] in allowed]
    return results


# ═════════════════════════════════════════════════════════════════════════
# 统一 RAG 个性化推荐引擎
# 核心思路：把用户行为（收藏/浏览/点评）涉及的菜谱标题+标签拼成"偏好画像文本"，
# 再走 RAG 向量语义检索评估出最匹配的菜谱；套餐推荐则以 RAG 评估出的偏好菜谱为锚点。
# 无行为数据的用户回退到热门/默认列表，保证任何情况下都有可用结果。
# ═════════════════════════════════════════════════════════════════════════

def _collect_user_recipe_ids(user_id: int, db: Session) -> set:
    """汇总用户行为涉及的菜谱 ID（收藏 + 浏览历史 + 点评）"""
    recipe_ids = set()

    fav_ids = [
        f.favorite_id for f in
        db.query(UserFavorite).filter(
            UserFavorite.user_id == user_id,
            UserFavorite.favorite_type == "recipe",
        ).limit(40).all()
    ]
    recipe_ids.update(fav_ids)

    hist_ids = [
        h.recipe_id for h in
        db.query(UserBrowseHistory).filter(
            UserBrowseHistory.user_id == user_id,
            UserBrowseHistory.recipe_id.isnot(None),
        ).limit(50).all()
    ]
    recipe_ids.update(hist_ids)

    review_ids = [
        r.recipe_id for r in
        db.query(RecipeReview).filter(
            RecipeReview.user_id == user_id,
            RecipeReview.is_deleted == 0,
        ).limit(40).all()
    ]
    recipe_ids.update(review_ids)
    recipe_ids.discard(None)
    return recipe_ids


def _build_user_preference_query(user_id: int, db: Session, max_items: int = 50) -> str:
    """构建用户偏好画像文本：取行为菜谱的标题 + 标签拼接成一段语义描述"""
    recipe_ids = _collect_user_recipe_ids(user_id, db)
    if not recipe_ids:
        return ""

    recipes = (
        db.query(Recipe)
        .options(joinedload(Recipe.tags).joinedload(RecipeTag.tag))
        .filter(Recipe.id.in_(list(recipe_ids)[:max_items]))
        .all()
    )

    tokens: List[str] = []
    seen = set()
    for r in recipes:
        candidates = [r.title or ""] + [t.tag.name for t in r.tags if t.tag]
        for t in candidates:
            t = (t or "").strip()
            if t and t not in seen:
                seen.add(t)
                tokens.append(t)
    return " ".join(tokens[:80])


def _format_recipe_with_score(recipe, score: float) -> Dict:
    """统一菜谱输出格式（带 similarity_score）"""
    return {
        "id": recipe.id,
        "title": recipe.title,
        "description": recipe.description,
        "cover_image_url": recipe.cover_image_url,
        "difficulty": recipe.difficulty,
        "cooking_time": recipe.cooking_time,
        "estimated_cost": float(recipe.estimated_cost) if recipe.estimated_cost else 0,
        "view_count": recipe.view_count,
        "favorite_count": recipe.favorite_count,
        "tags": _format_tags(recipe),
        "similarity_score": round(max(0.0, min(1.0, score)), 3),
    }


def _get_hot_recipe_list(db: Session, limit: int) -> List[Dict]:
    """无偏好时的热门菜谱兜底"""
    recipes = (
        db.query(Recipe)
        .options(joinedload(Recipe.tags).joinedload(RecipeTag.tag))
        .filter(Recipe.status == "approved", Recipe.is_deleted == 0)
        .order_by(Recipe.view_count.desc())
        .limit(limit)
        .all()
    )
    return [_format_recipe_with_score(r, 0.5) for r in recipes]


def get_personalized_rag_recommendations(
    user_id: int,
    db: Session,
    limit: int = 20,
    restriction_set: Optional[set] = None,
) -> List[Dict]:
    """基于用户偏好画像的 RAG 语义推荐（"为你推荐"统一评估逻辑）

    流程：
      1. 构建偏好画像文本（行为菜谱标题 + 标签）
      2. 用该文本做 RAG 向量语义检索，得到语义最匹配的菜谱
      3. 结果不足时用偏好标签的 MySQL 匹配补齐；无任何偏好时回退热门
    """
    pref = _build_user_preference_query(user_id, db)
    if not pref:
        return _get_hot_recipe_list(db, limit)

    results: List[Dict] = []
    seen_ids: set = set()
    try:
        rag_results = rag_search(pref, top_k=limit * 3, filter_source_type="recipe")
    except Exception as e:
        logger.error(f"个性化 RAG 检索失败（将回退标签匹配）: {e}")
        rag_results = []

    for r in rag_results:
        if r.get("source_type") != "recipe" or not r.get("source_id"):
            continue
        sid = int(r["source_id"])
        if sid in seen_ids:
            continue
        seen_ids.add(sid)
        recipe = (
            db.query(Recipe)
            .options(joinedload(Recipe.tags).joinedload(RecipeTag.tag))
            .filter(
                Recipe.id == sid,
                Recipe.status == "approved",
                Recipe.is_deleted == 0,
            )
            .first()
        )
        if recipe:
            score = 1.0 - (len(results) / (limit * 2))
            results.append(_format_recipe_with_score(recipe, score))
        if len(results) >= limit:
            break

    # 结果不足 → 用偏好标签的 MySQL 匹配补齐（排除已推荐）
    if len(results) < limit:
        tag_ids = extract_user_preferences(user_id, db)
        if tag_ids:
            recipe_ids = [
                rt.recipe_id for rt in
                db.query(RecipeTag).filter(RecipeTag.tag_id.in_(tag_ids)).all()
            ]
            fill_query = (
                db.query(Recipe)
                .options(joinedload(Recipe.tags).joinedload(RecipeTag.tag))
                .filter(
                    Recipe.id.in_(recipe_ids),
                    Recipe.status == "approved",
                    Recipe.is_deleted == 0,
                )
            )
            if seen_ids:
                fill_query = fill_query.filter(Recipe.id.notin_(seen_ids))
            fill_recipes = (
                fill_query.order_by(Recipe.favorite_count.desc())
                .limit(limit - len(results))
                .all()
            )
            for recipe in fill_recipes:
                results.append(_format_recipe_with_score(recipe, 0.5))

    # 仍不足 → 热门补齐
    if len(results) < limit:
        existing_ids = {r["id"] for r in results}
        fill_count = limit - len(results)
        extra = (
            db.query(Recipe)
            .options(joinedload(Recipe.tags).joinedload(RecipeTag.tag))
            .filter(
                Recipe.id.notin_(existing_ids),
                Recipe.status == "approved",
                Recipe.is_deleted == 0,
            )
            .order_by(Recipe.view_count.desc())
            .limit(fill_count)
            .all()
        )
        for recipe in extra:
            results.append(_format_recipe_with_score(recipe, 0.3))

    if restriction_set:
        from app.utils.recipe_diet import filter_recipe_ids
        allowed = filter_recipe_ids(db, [r["id"] for r in results], restriction_set)
        results = [r for r in results if r["id"] in allowed]

    return results[:limit]


def _get_public_plan_list(db: Session, limit: int) -> List[Dict]:
    """无偏好时的公开套餐兜底（按收藏数降序）"""
    plans = (
        db.query(MealPlan)
        .options(joinedload(MealPlan.creator))
        .filter(
            MealPlan.status == "approved",
            MealPlan.is_deleted == 0,
            MealPlan.is_public == 1,
        )
        .order_by(MealPlan.favorite_count.desc())
        .limit(limit)
        .all()
    )
    return [MealPlanListOut.model_validate(p) for p in plans]


def get_personalized_meal_plans(
    user_id: int,
    db: Session,
    limit: int = 6,
) -> List[Dict]:
    """RAG 偏好驱动的套餐推荐（"推荐套餐"统一评估逻辑）

    流程：
      1. 构建偏好画像文本 → RAG 检索得到用户偏好的菜谱集合
      2. 优先返回"包含这些偏好菜谱"的公开套餐，按命中数降序
      3. 无偏好/无匹配时回退公开热门套餐
    """
    pref = _build_user_preference_query(user_id, db)
    if not pref:
        return _get_public_plan_list(db, limit)

    pref_recipe_ids: set = set()
    try:
        rag_results = rag_search(pref, top_k=40, filter_source_type="recipe")
        pref_recipe_ids = {
            int(r["source_id"])
            for r in rag_results
            if r.get("source_type") == "recipe" and r.get("source_id")
        }
    except Exception as e:
        logger.error(f"套餐个性化 RAG 检索失败（将回退公开列表）: {e}")
        pref_recipe_ids = set()

    if not pref_recipe_ids:
        return _get_public_plan_list(db, limit)

    plans = (
        db.query(MealPlan)
        .options(joinedload(MealPlan.creator))
        .join(MealPlanItem)
        .filter(
            MealPlan.status == "approved",
            MealPlan.is_deleted == 0,
            MealPlan.is_public == 1,
            MealPlanItem.recipe_id.in_(pref_recipe_ids),
        )
        .distinct()
        .all()
    )

    # 按命中偏好菜谱数量降序，越贴合用户口味越靠前
    plans.sort(
        key=lambda p: sum(1 for item in p.items if item.recipe_id in pref_recipe_ids),
        reverse=True,
    )
    if not plans:
        # 无匹配套餐时回退公开热门套餐，保证推荐区域不为空
        return _get_public_plan_list(db, limit)
    return [MealPlanListOut.model_validate(p) for p in plans[:limit]]


def get_budget_recommendations(
    budget: float,
    db: Session,
    meal_type: Optional[str] = None,
) -> List[Dict]:
    """预算推荐：从 MySQL 按成本筛候选，再组合套餐"""
    candidates = []

    # 1. 查询预算范围内的单菜
    recipe_query = db.query(Recipe).options(
        joinedload(Recipe.tags).joinedload(RecipeTag.tag)
    ).filter(
        Recipe.status == "approved",
        Recipe.is_deleted == 0,
        Recipe.estimated_cost.isnot(None),
        Recipe.estimated_cost <= budget,
    )
    # 如果指定了餐次类型，通过标签过滤
    if meal_type:
        recipe_query = recipe_query.join(RecipeTag).join(Tag).filter(Tag.type == "meal_type", Tag.name == meal_type)

    recipes = recipe_query.order_by(Recipe.favorite_count.desc()).limit(30).all()

    for r in recipes:
        candidates.append({
            "id": r.id,
            "title": r.title,
            "description": r.description,
            "cover_image_url": r.cover_image_url,
            "difficulty": r.difficulty,
            "cooking_time": r.cooking_time,
            "estimated_cost": float(r.estimated_cost),
            "type": "recipe",
            "tags": _format_tags(r),
        })

    # 2. 查询预算范围内的预置套餐
    #    性能优化：用 joinedload 一次性取出 items 及其 recipe，避免每条套餐做 N+1 次查询
    plans = (
        db.query(MealPlan)
        .options(
            joinedload(MealPlan.items).joinedload(MealPlanItem.recipe)
        )
        .filter(
            MealPlan.status == "approved",
            MealPlan.is_deleted == 0,
            MealPlan.is_public == 1,
        ).all()
    )

    for plan in plans:
        total_cost = 0.0
        for item in plan.items:
            if item.recipe and item.recipe.estimated_cost:
                total_cost += float(item.recipe.estimated_cost)

        if total_cost <= budget:
            recipe_names = [item.recipe.title for item in plan.items if item.recipe]
            candidates.append({
                "id": plan.id,
                "title": plan.title,
                "description": plan.description,
                "cover_image_url": plan.cover_image_url,
                "estimated_cost": round(total_cost, 2),
                "type": "meal_plan",
                "items": recipe_names,
            })

    # 3. 贪心组合单菜成套餐（2-3 道菜）
    if len(recipes) >= 2:
        greedy_combos = _greedy_meal_combination(recipes, budget)
        candidates.extend(greedy_combos)

    return candidates


def _greedy_meal_combination(recipes: list, budget: float, max_combos: int = 10) -> List[Dict]:
    """贪心凑套餐：在预算内生成 2 菜 / 3 菜组合，方便用户一键搭配

    性能策略：
      - 只保留单菜成本严格小于预算的候选，压缩组合规模
      - 候选按成本升序排列，内层循环成本一旦超预算立即 break（剪枝）
      - 最多返回 max_combos 组，避免结果过载
    """
    candidates = [r for r in recipes if float(r.estimated_cost or 0) < budget]
    candidates.sort(key=lambda r: float(r.estimated_cost or 0))
    n = len(candidates)

    def cost_of(r) -> float:
        return float(r.estimated_cost or 0)

    results: List[Dict] = []

    def append_combo(combo: list, combo_type: str) -> None:
        total_cost = round(sum(cost_of(r) for r in combo), 2)
        name = " + ".join(r.title for r in combo)
        results.append({
            "id": f"{combo_type}_{'_'.join(str(r.id) for r in combo)}",
            "title": f"{name}（{total_cost}元）",
            "description": f"{len(combo)} 道菜组合，总成本 {total_cost}元",
            "estimated_cost": total_cost,
            "type": "meal_combo",
            "items": [r.title for r in combo],
        })

    def enough() -> bool:
        return len(results) >= max_combos

    # 2 菜组合
    for i in range(n):
        if enough():
            break
        if cost_of(candidates[i]) >= budget:
            continue
        for j in range(i + 1, n):
            two_sum = cost_of(candidates[i]) + cost_of(candidates[j])
            if two_sum > budget:
                break  # 已按成本升序，后续组合只会更贵
            append_combo([candidates[i], candidates[j]], "combo_2")
            if enough():
                break

    # 3 菜组合（成本约束较强，规模可控；同样做了剪枝）
    if not enough():
        for i in range(n):
            if enough():
                break
            if cost_of(candidates[i]) * 3 >= budget:
                continue
            for j in range(i + 1, n):
                if enough():
                    break
                two_sum = cost_of(candidates[i]) + cost_of(candidates[j])
                if two_sum >= budget:
                    break
                for k in range(j + 1, n):
                    three_sum = two_sum + cost_of(candidates[k])
                    if three_sum > budget:
                        break
                    append_combo([candidates[i], candidates[j], candidates[k]], "combo_3")
                    if enough():
                        break

    return results


def rag_recommend_by_query(
    query: str,
    db: Session,
    budget: Optional[float] = None,
    top_k: int = 10,
) -> List[Dict]:
    """RAG 语义推荐：用户说人话，系统找菜谱（带降级容错）

    降级策略：
      1. 优先走向量语义检索（rag_search）
      2. 若检索失败或无结果：回退到 MySQL 关键词匹配
      3. 始终保证不抛异常，至少返回空列表
    """
    results: List[Dict] = []
    seen_ids = set()

    # 1. 优先 RAG 检索（内部已有容错）
    try:
        rag_results = rag_search(query, top_k=top_k, filter_source_type="recipe")
    except Exception as e:
        logger.error(f"RAG 检索异常（将回退到关键词匹配）: {e}")
        rag_results = []

    # 2. 从 MySQL 获取完整信息
    for r in rag_results:
        if r.get("source_type") == "recipe" and r.get("source_id") not in seen_ids:
            seen_ids.add(r["source_id"])
            recipe = db.query(Recipe).options(
                joinedload(Recipe.tags).joinedload(RecipeTag.tag)
            ).filter(
                Recipe.id == r["source_id"],
                Recipe.status == "approved",
                Recipe.is_deleted == 0,
            ).first()
            if recipe:
                cost = float(recipe.estimated_cost) if recipe.estimated_cost else 0
                if budget is None or cost <= budget:
                    results.append({
                        "id": recipe.id,
                        "title": recipe.title,
                        "description": recipe.description,
                        "cover_image_url": recipe.cover_image_url,
                        "difficulty": recipe.difficulty,
                        "cooking_time": recipe.cooking_time,
                        "estimated_cost": cost,
                        "type": "recipe",
                        "similarity_score": round(1.0 - (len(results) / (top_k + 1)), 3),
                        "tags": _format_tags(recipe),
                    })

    # 3. 若 RAG 未能提供结果（或结果太少），回退到 MySQL 关键词匹配
    if len(results) < 3:
        try:
            fallback = _db_keyword_fallback_recipes(query, db, budget=budget, limit=top_k)
            existing_ids = {item["id"] for item in results if item.get("type") == "recipe"}
            for item in fallback:
                if item["id"] not in existing_ids:
                    results.append(item)
        except Exception as e:
            logger.error(f"关键词兜底检索失败: {e}")

    return results