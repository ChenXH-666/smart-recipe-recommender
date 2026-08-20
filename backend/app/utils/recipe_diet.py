"""忌口/过敏原过滤工具 —— 复用 Ingredient.diet_tags 判断菜谱是否触碰用户忌口

restriction 标签与 Ingredient.diet_tags 同源：
  seafood / nuts / dairy / egg / gluten / mushroom / soy / allium / spicy / meat / veg
其中 'veg' 表示"素食者"，即要求该菜谱不含任何含 'meat' 标签的食材。
"""
from typing import List, Optional, Set


def get_restriction_set(user: Optional[object]) -> Set[str]:
    """从用户偏好提取忌口标签集合（无偏好或未登录返回空集）"""
    if not user:
        return set()
    prefs = getattr(user, "preferences", None) or {}
    return set(prefs.get("diet_tags", []) or [])


def recipe_diet_warnings(recipe, restriction_set: Set[str]) -> List[str]:
    """返回菜谱中触碰忌口的食材名列表（无则空列表）。

    recipe.ingredients 需为已加载的 RecipeIngredient 列表（含 .ingredient）。
    """
    if not restriction_set:
        return []
    warnings: List[str] = []
    for ri in recipe.ingredients:
        ing = getattr(ri, "ingredient", None)
        tags = (ing.diet_tags or []) if ing else []
        if not tags:
            continue
        tset = set(tags)
        for r in restriction_set:
            if r == "veg":
                if "meat" in tset:
                    warnings.append(ing.name)
                    break
            elif r in tset:
                warnings.append(ing.name)
                break
    return warnings


def filter_recipe_ids(db, recipe_ids, restriction_set) -> Set[int]:
    """从一批菜谱 id 中剔除触碰忌口的，返回保留的 id 集合（单查询批量判断）。
    传入空忌口或空 ids 时原样返回。
    """
    from app.models import RecipeIngredient, Ingredient
    if not recipe_ids or not restriction_set:
        return set(recipe_ids)

    rows = (
        db.query(RecipeIngredient.recipe_id, Ingredient.diet_tags)
        .join(Ingredient, Ingredient.id == RecipeIngredient.ingredient_id)
        .filter(
            RecipeIngredient.recipe_id.in_(list(recipe_ids)),
            Ingredient.diet_tags.isnot(None),
        )
        .all()
    )
    violating: Set[int] = set()
    for rid, tags in rows:
        tset = set(tags or [])
        for r in restriction_set:
            if r == "veg":
                if "meat" in tset:
                    violating.add(rid)
                    break
            elif r in tset:
                violating.add(rid)
                break
    return set(recipe_ids) - violating