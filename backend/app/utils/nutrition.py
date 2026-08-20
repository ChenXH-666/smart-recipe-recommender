"""菜谱营养估算工具 —— 基于食材每100g营养 + 用量解析"""
from typing import Optional

from app.utils.portions import parse_grams

NUTRITION_KEYS = ("kcal", "protein", "fat", "carbs")


def compute_recipe_nutrition(ingredients) -> Optional[dict]:
    """对一组 RecipeIngredient 计算一份的总营养（估算）。

    对每个食材：grams = 用量解析器换算的克数；营养 = 食材每100g值 × grams/100。
    没有任何食材有营养数据时返回 None（前端可隐藏该模块）。
    """
    totals = {"kcal": 0.0, "protein": 0.0, "fat": 0.0, "carbs": 0.0}
    covered = False
    for ri in ingredients:
        ing = getattr(ri, "ingredient", None)
        nut = (ing.nutrition) if ing else None
        if not nut:
            continue
        grams = parse_grams(getattr(ri, "quantity", None)) or 0
        if grams <= 0:
            continue
        mult = grams / 100.0
        for k in NUTRITION_KEYS:
            v = nut.get(k)
            if v is not None:
                totals[k] += float(v) * mult
                covered = True
    if not covered:
        return None
    return {k: round(totals[k], 1) for k in NUTRITION_KEYS}