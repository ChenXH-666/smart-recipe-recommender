# -*- coding: utf-8 -*-
"""模型层单元测试 —— 使用 SQLite 内存库验证 ORM 模型的计算属性与默认值。"""
from sqlalchemy import text

from app.models import User, Recipe, MealPlan


class TestAuthorNickname:
    def test_recipe_with_author_prefers_nickname(self, db_session):
        author = User(username="u1", nickname="暖心大厨", email="u1@a.com", password_hash="h")
        recipe = Recipe(title="红烧肉", status="approved")
        recipe.author = author
        db_session.add_all([author, recipe])
        db_session.commit()
        db_session.refresh(recipe)
        assert recipe.author_nickname == "暖心大厨"

    def test_recipe_falls_back_to_username(self, db_session):
        author = User(username="u2", email="u2@a.com", password_hash="h")
        recipe = Recipe(title="清蒸鱼", status="approved")
        recipe.author = author
        db_session.add(author)
        db_session.add(recipe)
        db_session.commit()
        db_session.refresh(recipe)
        assert recipe.author_nickname == "u2"

    def test_recipe_without_author(self, db_session):
        recipe = Recipe(title="无主菜", status="approved")
        db_session.add(recipe)
        db_session.commit()
        db_session.refresh(recipe)
        assert recipe.author_nickname is None

    def test_meal_plan_nickname(self, db_session):
        creator = User(username="u3", nickname="美食家", email="u3@a.com", password_hash="h")
        plan = MealPlan(title="周一套餐", status="pending")
        plan.creator = creator
        db_session.add(creator)
        db_session.add(plan)
        db_session.commit()
        db_session.refresh(plan)
        assert plan.author_nickname == "美食家"


class TestModelDefaults:
    def test_recipe_status_default_is_pending(self, db_session):
        recipe = Recipe(title="默认状态菜")
        db_session.add(recipe)
        db_session.commit()
        db_session.refresh(recipe)
        assert recipe.status == "pending"
        assert recipe.is_deleted == 0

    def test_user_role_default(self, db_session):
        user = User(username="def", email="def@a.com", password_hash="h")
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        assert user.role == "user"

    def test_list_dishes_table_created(self, db_engine):
        # 验证 Base.metadata 已包含全部业务表
        with db_engine.connect() as conn:
            tables = {
                r[0] for r in conn.execute(text(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ))
            }
        for tab in ("users", "recipes", "ingredients", "meal_plans",
                    "ai_conversations", "user_favorites"):
            assert tab in tables