# -*- coding: utf-8 -*-
"""utils/recipe_diet.py —— 忌口/过敏原过滤工具单元测试。"""
from types import SimpleNamespace

from app.utils.recipe_diet import (
    get_restriction_set,
    recipe_diet_warnings,
    filter_recipe_ids,
)


def _ing(name, tags):
    ing = SimpleNamespace(name=name, diet_tags=tags)
    return ing


def _ri(ing):
    return SimpleNamespace(ingredient=ing)


class TestGetRestrictionSet:
    def test_user_none(self):
        assert get_restriction_set(None) == set()

    def test_user_no_preferences(self):
        assert get_restriction_set(SimpleNamespace(preferences={})) == set()

    def test_user_with_diet_tags(self):
        user = SimpleNamespace(preferences={"diet_tags": ["seafood", "nuts"]})
        assert get_restriction_set(user) == {"seafood", "nuts"}

    def test_user_preferences_none(self):
        assert get_restriction_set(SimpleNamespace(preferences=None)) == set()


class TestRecipeDietWarnings:
    def test_no_restrictions(self):
        recipe = SimpleNamespace(ingredients=[_ri(_ing("虾", ["seafood"]))])
        assert recipe_diet_warnings(recipe, set()) == []

    def test_no_ingredients_with_tags(self):
        recipe = SimpleNamespace(ingredients=[_ri(_ing("盐", None))])
        assert recipe_diet_warnings(recipe, {"seafood"}) == []

    def test_matches_restriction(self):
        recipe = SimpleNamespace(ingredients=[_ri(_ing("虾", ["seafood", "spicy"]))])
        assert recipe_diet_warnings(recipe, {"seafood"}) == ["虾"]

    def test_not_matching(self):
        recipe = SimpleNamespace(ingredients=[_ri(_ing("牛肉", ["meat"]))])
        assert recipe_diet_warnings(recipe, {"seafood"}) == []

    def test_vegan_rejects_meat(self):
        recipe = SimpleNamespace(ingredients=[_ri(_ing("猪肉", ["meat"]))])
        assert recipe_diet_warnings(recipe, {"veg"}) == ["猪肉"]

    def test_vegan_allows_veg(self):
        recipe = SimpleNamespace(ingredients=[_ri(_ing("豆腐", ["soy"]))])
        assert recipe_diet_warnings(recipe, {"veg"}) == []

    def test_multiple_restrictions_only_names_once(self):
        recipe = SimpleNamespace(ingredients=[_ri(_ing("虾", ["seafood", "spicy"]))])
        assert recipe_diet_warnings(recipe, {"seafood", "spicy"}) == ["虾"]


class TestFilterRecipeIds:
    def test_empty_ids(self, db_session):
        assert filter_recipe_ids(db_session, [], {"seafood"}) == set()

    def test_no_restrictions_returns_all(self, db_session):
        assert filter_recipe_ids(db_session, [1, 2], set()) == {1, 2}

    def test_excludes_violating(self, db_session):
        from app.models import Recipe, Ingredient, RecipeIngredient

        ing_ok = Ingredient(name="豆腐", diet_tags=["soy"])
        ing_bad = Ingredient(name="虾", diet_tags=["seafood"])
        db_session.add_all([ing_ok, ing_bad])
        db_session.flush()

        r1 = Recipe(title="素菜", status="approved")
        r2 = Recipe(title="虾仁", status="approved")
        db_session.add_all([r1, r2])
        db_session.flush()
        db_session.add_all([
            RecipeIngredient(recipe_id=r1.id, ingredient_id=ing_ok.id),
            RecipeIngredient(recipe_id=r2.id, ingredient_id=ing_bad.id),
        ])
        db_session.commit()

        result = filter_recipe_ids(db_session, [r1.id, r2.id], {"seafood"})
        assert result == {r1.id}