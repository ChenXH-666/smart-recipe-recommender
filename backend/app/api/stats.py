"""公共首页统计

对未登录访客开放，返回菜谱/套餐/用户核心指标与近一周新增量，
用于首页统计卡片展示。注意：仅返回聚合计数，不暴露任何明细或敏感数据。
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Recipe, MealPlan, User

router = APIRouter()


@router.get("")
def home_stats(db: Session = Depends(get_db)):
    """首页统计：总量 + 近一周新增量"""
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

    return {
        "total_recipes": total_recipes,
        "new_recipes_week": new_recipes_week,
        "total_meal_plans": total_meal_plans,
        "new_meal_plans_week": new_meal_plans_week,
        "total_users": total_users,
        "new_users_week": new_users_week,
    }