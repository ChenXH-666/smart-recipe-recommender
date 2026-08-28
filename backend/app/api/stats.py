"""公共首页统计

对未登录访客开放，返回菜谱/套餐/用户核心指标与近一周新增量，
用于首页统计卡片展示。注意：仅返回聚合计数，不暴露任何明细或敏感数据。

性能：本接口共执行 7 次聚合 COUNT，且统计数据变化频率低（周粒度展示），
采用进程内 TTL 缓存（60 秒），避免每次首页访问都全量统计；
明细数据变化最迟 60 秒后反映到统计卡片，对该粒度展示无感知影响。
"""

import time
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Recipe, MealPlan, User

router = APIRouter()

# 统计缓存：{data: 统计结果, expires_at: 过期时间（time.monotonic）}
_STATS_TTL_SECONDS = 60
_stats_cache: dict = {"data": None, "expires_at": 0.0}


@router.get("")
def home_stats(db: Session = Depends(get_db)):
    """首页统计：总量 + 近一周新增量（60 秒 TTL 内存缓存）"""
    now = time.monotonic()
    cached = _stats_cache["data"]
    if cached is not None and now < _stats_cache["expires_at"]:
        return cached

    week_ago = datetime.now() - timedelta(days=7)

    total_recipes = db.query(func.count(Recipe.id)).filter(
        Recipe.status == "approved", Recipe.is_deleted == 0
    ).scalar() or 0
    new_recipes_week = db.query(func.count(Recipe.id)).filter(
        Recipe.status == "approved",
        Recipe.is_deleted == 0,
        Recipe.created_at >= week_ago,
    ).scalar() or 0

    total_meal_plans = db.query(func.count(MealPlan.id)).filter(
        MealPlan.status == "approved",
        MealPlan.is_deleted == 0,
        MealPlan.is_public == 1,
    ).scalar() or 0
    new_meal_plans_week = db.query(func.count(MealPlan.id)).filter(
        MealPlan.status == "approved",
        MealPlan.is_deleted == 0,
        MealPlan.is_public == 1,
        MealPlan.created_at >= week_ago,
    ).scalar() or 0

    total_users = db.query(func.count(User.id)).scalar() or 0
    new_users_week = db.query(func.count(User.id)).filter(
        User.created_at >= week_ago
    ).scalar() or 0

    result = {
        "total_recipes": total_recipes,
        "new_recipes_week": new_recipes_week,
        "total_meal_plans": total_meal_plans,
        "new_meal_plans_week": new_meal_plans_week,
        "total_users": total_users,
        "new_users_week": new_users_week,
    }
    _stats_cache["data"] = result
    _stats_cache["expires_at"] = now + _STATS_TTL_SECONDS
    return result