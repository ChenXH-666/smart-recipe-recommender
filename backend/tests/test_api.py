# -*- coding: utf-8 -*-
"""接口层单元测试 —— 基于 FastAPI TestClient + SQLite 内存库。

通过覆盖 app.dependency_overrides[get_db] 注入测试会话，避免连接真实 MySQL；
同时将菜谱接口内部的 Chroma 同步函数 mock 为空操作，保证测试快速且确定。
"""
import pytest
from sqlalchemy.orm import sessionmaker

from app.models import Ingredient


def _register(client, username="user1", email="user1@a.com", password="pass1234"):
    r = client.post("/api/auth/register", json={
        "username": username, "email": email, "password": password,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _login(client, username="user1", password="pass1234"):
    r = client.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth_header(token):
    return {"Authorization": f"Bearer {token}"}


class TestAuthApi:
    def test_register_login_me_flow(self, client):
        _register(client)
        token = _login(client)
        r = client.get("/api/auth/me", headers=_auth_header(token))
        assert r.status_code == 200
        assert r.json()["username"] == "user1"

    def test_register_duplicate_username_rejected(self, client):
        _register(client, username="dup")
        r = _register_dup = client.post("/api/auth/register", json={
            "username": "dup", "email": "o@a.com", "password": "pass1234",
        })
        assert r.status_code == 400
        assert "用户名已存在" in r.text

    def test_me_without_token_returns_401(self, client):
        assert client.get("/api/auth/me").status_code == 401

    def test_login_wrong_password(self, client):
        _register(client)
        r = client.post("/api/auth/login", json={"username": "user1", "password": "wrong123"})
        assert r.status_code == 401

    def test_too_short_password_rejected_by_schema(self, client):
        # 密码不足 8 位：Pydantic schema 拦截返回 422
        r = client.post("/api/auth/register", json={
            "username": "shortpwd", "email": "sp@a.com", "password": "123",
        })
        assert r.status_code == 422

    def test_composition_weak_password_rejected(self, client):
        # 长度≥8 但全是数字：经 schema 后由处理器强度校验返回 400
        r = client.post("/api/auth/register", json={
            "username": "allnum", "email": "an@a.com", "password": "12345678",
        })
        assert r.status_code == 400
        assert "字母" in r.text


class TestRecipeApi:
    def _seed_user_recipe(self, client, db_engine):
        Session = sessionmaker(bind=db_engine, expire_on_commit=False)
        s = Session()
        ing = Ingredient(name="猪肉")
        s.add(ing)
        s.commit()
        ing_id = ing.id
        s.close()
        _register(client, "chef", "chef@a.com")
        token = _login(client, "chef")
        r = client.post("/api/recipes", json={
            "title": "红烧肉", "difficulty": "easy", "estimated_cost": 20,
            "ingredients": [{"ingredient_id": ing_id, "quantity": "200克"}],
            "steps": [{"step_number": 1, "instruction": "下锅翻炒"}],
            "tag_ids": [],
        }, headers=_auth_header(token))
        assert r.status_code == 201, r.text
        return token, r.json()["id"]

    def test_list_recipes_empty(self, client):
        r = client.get("/api/recipes", params={"status": "approved"})
        assert r.status_code == 200
        assert r.json()["items"] == []

    def test_bad_difficulty_filter_rejected(self, client):
        r = client.get("/api/recipes", params={"difficulty": "insane"})
        assert r.status_code == 400

    def test_create_recipe_requires_auth(self, client):
        assert client.post("/api/recipes", json={}).status_code == 401

    def test_create_recipe_as_normal_user_is_pending(self, client, db_engine):
        _register(client, "chef", "chef@a.com")
        token = _login(client, "chef")
        Session = sessionmaker(bind=db_engine, expire_on_commit=False)
        s = Session()
        ing = Ingredient(name="青菜")
        s.add(ing)
        s.commit()
        r = client.post("/api/recipes", json={
            "title": "清炒时蔬", "difficulty": "easy", "estimated_cost": 8,
            "ingredients": [{"ingredient_id": ing.id, "quantity": "200克"}],
            "steps": [{"step_number": 1, "instruction": "热油下锅"}],
            "tag_ids": [],
        }, headers=_auth_header(token))
        s.close()
        assert r.status_code == 201
        assert r.json()["status"] == "pending"

    def test_recipe_not_visible_public_until_approved(self, client, db_engine):
        token, _rid = self._seed_user_recipe(client, db_engine)
        # 普通用户创建的 pending 菜谱不应出现在公开列表
        r = client.get("/api/recipes", params={"status": "approved"})
        assert all(item["title"] != "红烧肉" for item in r.json()["items"])

    def test_update_other_users_recipe_forbidden(self, client, db_engine):
        token, rid = self._seed_user_recipe(client, db_engine)
        _register(client, "other", "other@a.com")
        other_token = _login(client, "other")
        r = client.put(f"/api/recipes/{rid}", json={"title": "篡改"},
                       headers=_auth_header(other_token))
        assert r.status_code == 404  # 非作者看不到，规避越权
        # 作者本人可更新
        r2 = client.put(f"/api/recipes/{rid}", json={"title": "红烧肉改"},
                        headers=_auth_header(token))
        assert r2.status_code == 200
        assert r2.json()["title"] == "红烧肉改"