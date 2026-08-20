"""
针对本次新增优化点的回归测试：

  1. _greedy_meal_combination          —— 2菜/3菜组合生成与预算约束
  2. get_budget_recommendations        —— joinedload（N+1 优化）后结果正确性
  3. /api/stats (app.api.stats)        —— 首页统计聚合正确性
"""

from datetime import timedelta

import pytest


# ─────────────────────────────────────────────────────────────
# 1. _greedy_meal_combination
# ─────────────────────────────────────────────────────────────
def test_greedy_generates_2dish_and_3dish_combos(db):
    from app.models import Recipe
    from app.services.recommendation_service import _greedy_meal_combination

    recipes = []
    for i, cost in enumerate([2, 3, 4, 5], start=1):
        r = Recipe(id=i, title=f"菜{i}", estimated_cost=cost, status="approved", is_deleted=0)
        recipes.append(r)

    out = _greedy_meal_combination(recipes, budget=9)
    types = {x["id"].split("_")[1] for x in out}

    assert "2" in types, "应生成 2 菜组合"
    assert "3" in types, "应生成 3 菜组合"
    # 所有组合成本都必须落在预算内
    for combo in out:
        assert combo["estimated_cost"] <= 9, f"组合超出预算: {combo}"
    # 不超过上限
    assert len(out) <= 10


def test_greedy_excludes_dishes_over_budget(db):
    from app.models import Recipe
    from app.services.recommendation_service import _greedy_meal_combination

    recipes = [Recipe(id=i, title=f"菜{i}", estimated_cost=c, status="approved", is_deleted=0)
               for i, c in enumerate([20, 25, 3, 4], start=1)]

    out = _greedy_meal_combination(recipes, budget=10)
    # 3元和4元两道菜可组合（7≤10）；超预算的20/25不得参与
    assert len(out) >= 1
    for combo in out:
        assert combo["estimated_cost"] <= 10
        assert "菜1" not in combo["title"] and "菜2" not in combo["title"]


def test_greedy_caps_max_combos(db):
    from app.models import Recipe
    from app.services.recommendation_service import _greedy_meal_combination

    recipes = [Recipe(id=i, title=f"菜{i}", estimated_cost=1, status="approved", is_deleted=0)
               for i in range(1, 11)]
    out = _greedy_meal_combination(recipes, budget=50, max_combos=10)
    assert len(out) <= 10


# ─────────────────────────────────────────────────────────────
# 2. get_budget_recommendations —— joinedload 优化后正确性
# ─────────────────────────────────────────────────────────────
def test_get_budget_recommendations_includes_recipes_plans_combos(db, week_ago):
    from app.services.recommendation_service import get_budget_recommendations

    # 预算内的 4 道已审核菜
    r1 = _recipe(db, "青椒肉丝", 3, "approved")
    r2 = _recipe(db, "番茄炒蛋", 4, "approved")
    r3 = _recipe(db, "凉拌黄瓜", 5, "approved")
    r4 = _recipe(db, "酸辣土豆丝", 2, "approved")
    # 一道超出预算的菜 → 不应出现在结果
    _recipe(db, "鲍鱼大餐", 999, "approved")
    # 一道未审核菜 → 不应出现在结果
    _recipe(db, "待审核菜", 2, "pending")

    # 预算内的公开套餐（包含 3+4+5=12>9，超出预算，不应出现）
    _plan(db, "超预算套餐", [r1.id, r2.id, r3.id], is_public=1, status="approved")
    # 预算内套餐（2+3=5）
    _plan(db, "实惠套餐", [r4.id, r1.id], is_public=1, status="approved")
    # 非公开套餐 → 不应出现
    _plan(db, "私有套餐", [r1.id], is_public=0, status="approved")

    out = get_budget_recommendations(9, db, meal_type=None)

    types = {x["type"] for x in out}
    assert "recipe" in types
    assert "meal_plan" in types
    assert "meal_combo" in types

    # 菜谱候选不含超预算/未审核菜
    recipe_ids = {x["id"] for x in out if x["type"] == "recipe"}
    assert "鲍鱼大餐" not in {x["title"] for x in out if x["type"] == "recipe"}

    # 套餐候选只含预算内的公开套餐
    plan_titles = {x["title"] for x in out if x["type"] == "meal_plan"}
    assert "实惠套餐" in plan_titles
    assert "超预算套餐" not in plan_titles
    assert "私有套餐" not in plan_titles


# ─────────────────────────────────────────────────────────────
# 3. /api/stats 首页统计
# ─────────────────────────────────────────────────────────────
def test_stats_counts(db, week_ago):
    from app.api.stats import home_stats
    from app.models import Recipe

    # 用户：1 个今天注册，1 个 8 天前注册，1 个今天注册
    u1 = _user(db, "u1", "u1@x.com")
    u2 = _user(db, "u2", "u2@x.com", created_at=week_ago - timedelta(days=1))  # 8 天前，不在近7天
    u3 = _user(db, "u3", "u3@x.com", created_at=week_ago + timedelta(days=1))  # 近7天内

    # 菜谱：1 个今天(已审核)，1 个 8 天前(已审核)，1 个未审核，1 个软删除
    _recipe(db, "今天菜", 10, "approved")
    _recipe(db, "八天前菜", 10, "approved", created_at=week_ago - timedelta(days=1))
    _recipe(db, "未审核菜", 10, "pending")
    _recipe(db, "已删除菜", 10, "approved")
    for r in db.query(Recipe).all():
        if r.title == "已删除菜":
            r.is_deleted = 1
    db.commit()

    # 套餐：1 个公开已审核(今天)，1 个私有，1 个未审核
    _plan(db, "公开套餐", [], is_public=1, status="approved")
    _plan(db, "私有套餐", [], is_public=0, status="approved")
    _plan(db, "未审核套餐", [], is_public=1, status="pending")

    stats = home_stats(db)

    assert stats["total_users"] == 3
    assert stats["new_users_week"] == 2                                        # u1 + u3
    assert stats["total_recipes"] == 2                                          # 今天菜 + 八天前菜（已审核且未删除）
    assert stats["new_recipes_week"] == 1                                       # 仅今天菜
    assert stats["total_meal_plans"] == 1                                       # 仅公开套餐
    assert stats["new_meal_plans_week"] == 1


# ── 本地小助手 ──────────────────────────────────────────────
def _user(db, username, email, created_at=None):
    from app.models import User
    u = User(username=username, email=email, password_hash="x", role="user", is_active=1, created_at=created_at)
    db.add(u)
    db.commit()
    return u


def _recipe(db, title, cost, status, created_at=None):
    from app.models import Recipe
    r = Recipe(title=title, description=title, estimated_cost=cost, status=status,
               is_deleted=0, view_count=0, favorite_count=0, created_at=created_at)
    db.add(r)
    db.commit()
    return r


def _plan(db, title, recipe_ids, is_public, status, created_at=None):
    from app.models import MealPlan, MealPlanItem, Recipe
    p = MealPlan(title=title, description=title + "套餐", user_id=1, is_public=is_public,
                 status=status, is_deleted=0, created_at=created_at)
    db.add(p)
    db.commit()
    for i, rid in enumerate(recipe_ids):
        db.add(MealPlanItem(meal_plan_id=p.id, recipe_id=rid, sort_order=i))
    db.commit()
    return p