# -*- coding: utf-8 -*-
"""utils/nutrition.py —— 营养估算工具单元测试。"""
from types import SimpleNamespace

from app.utils.nutrition import compute_recipe_nutrition, NUTRITION_KEYS


def _ri(nutrition, quantity):
    """构造带任意回退字段的 RecipeIngredient 假对象。"""
    ri = SimpleNamespace()
    ri.ingredient = SimpleNamespace(nutrition=nutrition)
    ri.quantity = quantity
    return ri


class TestComputeNutrition:
    def test_single_ingredient(self):
        # 100g → 200g：各营养 ×2
        ri = _ri({"kcal": 100, "protein": 20, "fat": 5, "carbs": 10}, "200克")
        assert compute_recipe_nutrition([ri]) == {
            "kcal": 200.0, "protein": 40.0, "fat": 10.0, "carbs": 20.0,
        }

    def test_multiple_ingredients_accumulate(self):
        ri1 = _ri({"kcal": 100, "protein": 10}, "100克")
        ri2 = _ri({"kcal": 50, "protein": 5}, "100克")
        result = compute_recipe_nutrition([ri1, ri2])
        assert result["kcal"] == 150.0
        assert result["protein"] == 15.0

    def test_no_nutrition_data_returns_none(self):
        assert compute_recipe_nutrition([_ri(None, "200克")]) is None

    def test_no_quantity_skipped(self):
        # quantity 无法解析（None）→ 跳过，最终无覆盖 → None
        assert compute_recipe_nutrition([_ri({"kcal": 100}, None)]) is None

    def test_partial_missing_keys(self):
        # 某食材缺部分字段：只累加已有的
        ri = _ri({"kcal": 100, "protein": 10}, "200克")
        result = compute_recipe_nutrition([ri])
        assert result["fat"] == 0.0
        assert result["carbs"] == 0.0

    def test_rounding_to_one_decimal(self):
        # 333.33g × 3 容易产生循环小数，验证 round(value, 1)
        ri = _ri({"kcal": 100}, "333克")
        result = compute_recipe_nutrition([ri])
        assert result["kcal"] == round(333.0, 1)

    def test_all_keys_present(self):
        result = compute_recipe_nutrition([_ri({"kcal": 1, "protein": 1, "fat": 1, "carbs": 1}, "100克")])
        assert set(result.keys()) == set(NUTRITION_KEYS)