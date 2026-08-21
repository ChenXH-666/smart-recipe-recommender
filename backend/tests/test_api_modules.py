# -*- coding: utf-8 -*-
"""接口层单元测试（补充）—— 覆盖用户中心 / 点评 / 心得 / 套餐核心流程。

复用 conftest.client（get_db 注入 SQLite + Chroma stub），
并通过共享的 db 会话直接播种测试数据，聚焦各模块的主干业务与权限。
"""
from app.models import Recipe, Ingredient, RecipeIngredient


def _register(client, username="chef", email="chef@a.com", password="pass1234"):
    r = client.post("/api/auth/register", json={
        "username": username, "email": email, "password": password,
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _login(client, username="chef", password="pass1234"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def _approved_recipe(db, author_id, title="红烧肉", cost=20):
    r = Recipe(title=title, description=title, status="approved",
               is_deleted=0, author_id=author_id, estimated_cost=cost)
    db.add(r)
    db.commit()
    return r.id


def _approved_recipe_with_ingredient(db, author_id, title="有食材菜", cost=15):
    ing = Ingredient(name="猪肉", diet_tags=["meat"])
    db.add(ing)
    db.flush()
    r = Recipe(title=title, status="approved", is_deleted=0,
               author_id=author_id, estimated_cost=cost)
    db.add(r)
    db.flush()
    db.add(RecipeIngredient(recipe_id=r.id, ingredient_id=ing.id,
                            quantity="200克", sort_order=0))
    db.commit()
    return r.id


# ------------------------------- 用户中心 -------------------------------

class TestUsers:
    def test_preferences_roundtrip(self, client, db):
        _register(client)
        token = _login(client)
        put = client.put("/api/users/preferences", json={
            "cuisines": ["粤菜"], "diet_tags": ["seafood"], "free_text": "不吃辣",
        }, headers=_auth(token))
        assert put.status_code == 200
        got = client.get("/api/users/preferences", headers=_auth(token))
        assert got.json()["diet_tags"] == ["seafood"]
        assert got.json()["cuisines"] == ["粤菜"]

    def test_update_profile(self, client, db):
        _register(client)
        token = _login(client)
        r = client.put("/api/users/profile", json={"nickname": "暖心大厨"},
                       headers=_auth(token))
        assert r.status_code == 200
        assert r.json()["nickname"] == "暖心大厨"

    def test_favorites_lifecycle(self, client, db):
        uid = _register(client)
        token = _login(client)
        rid = _approved_recipe(db, uid)
        add = client.post("/api/users/favorites",
                          params={"favorite_type": "recipe", "favorite_id": rid},
                          headers=_auth(token))
        assert add.status_code == 200
        fav_id = add.json()["id"]
        lst = client.get("/api/users/favorites", headers=_auth(token))
        assert lst.json()["total"] == 1
        rmv = client.delete(f"/api/users/favorites/{fav_id}", headers=_auth(token))
        assert rmv.status_code == 200

    def test_browse_history_record_and_list(self, client, db):
        uid = _register(client)
        token = _login(client)
        rid = _approved_recipe(db, uid)
        rec = client.post("/api/users/history", params={"recipe_id": rid},
                          headers=_auth(token))
        assert rec.status_code == 200
        hist = client.get("/api/users/history", headers=_auth(token))
        assert hist.json()["total"] == 1


# ------------------------------- 点评 -------------------------------

class TestReviews:
    def test_create_list_duplicate_and_delete(self, client, db):
        uid = _register(client)
        token = _login(client)
        rid = _approved_recipe(db, uid)

        create = client.post(f"/api/reviews/recipes/{rid}",
                             json={"rating": 5, "content": "不错"},
                             headers=_auth(token))
        assert create.status_code == 200
        review_id = create.json()["id"]

        lst = client.get(f"/api/reviews/recipes/{rid}")
        assert lst.json()["total"] == 1

        dup = client.post(f"/api/reviews/recipes/{rid}",
                          json={"rating": 4}, headers=_auth(token))
        assert dup.status_code == 400  # 不能重复点评

        assert client.delete(f"/api/reviews/{review_id}",
                             headers=_auth(token)).status_code == 200


# ------------------------------- 烹饪心得 -------------------------------

class TestCookingNotes:
    def test_create_update_list_comment_delete(self, client, db):
        uid = _register(client)
        token = _login(client)
        rid = _approved_recipe(db, uid)

        create = client.post("/api/cooking-notes", json={
            "title": "今日家常", "content": "做法简单", "related_recipe_id": rid,
            "is_public": True,
        }, headers=_auth(token))
        assert create.status_code == 201
        note_id = create.json()["id"]

        assert client.get("/api/cooking-notes").json()["total"] == 1

        upd = client.put(f"/api/cooking-notes/{note_id}", json={"title": "改标题"},
                         headers=_auth(token))
        assert upd.status_code == 200
        assert upd.json()["title"] == "改标题"

        com = client.post(f"/api/cooking-notes/{note_id}/comments",
                          json={"content": "真不错"}, headers=_auth(token))
        assert com.status_code == 201

        rmv = client.delete(f"/api/cooking-notes/{note_id}", headers=_auth(token))
        assert rmv.status_code == 200


# ------------------------------- 套餐 -------------------------------

class TestMealPlans:
    def test_create_pending_shopping_list_and_delete(self, client, db):
        uid = _register(client)
        token = _login(client)
        rid = _approved_recipe_with_ingredient(db, uid, title="肉末茄子")

        create = client.post("/api/meal-plans", json={
            "title": "周末套餐", "description": "两菜一汤", "is_public": True,
            "items": [{"recipe_id": rid, "sort_order": 0}],
        }, headers=_auth(token))
        assert create.status_code == 201
        plan_id = create.json()["id"]
        assert create.json()["status"] == "pending"  # 普通用户待审核

        # 普通用户创建的待审核套餐不应出现在公开广场
        assert client.get("/api/meal-plans").json()["total"] == 0
        # 我的套餐可见
        assert client.get("/api/meal-plans", params={"mine": 1},
                          headers=_auth(token)).json()["total"] == 1

        # 生成购物清单（作者可访问自己的待审核套餐）
        sl = client.get(f"/api/meal-plans/{plan_id}/shopping-list",
                        headers=_auth(token))
        assert sl.status_code == 200

        # 详情
        det = client.get(f"/api/meal-plans/{plan_id}", headers=_auth(token))
        assert det.status_code == 200

        assert client.delete(f"/api/meal-plans/{plan_id}",
                             headers=_auth(token)).status_code == 200

    def test_create_plan_requires_auth(self, client):
        assert client.post("/api/meal-plans",
                           json={"title": "匿名套餐", "items": []}).status_code == 401