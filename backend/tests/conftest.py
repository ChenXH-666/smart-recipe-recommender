"""
测试基础设施 —— SQLite 内存库，隔离真实 MySQL 与外部 LLM API。

说明：
  - 全部后端回归测试使用 SQLite（:memory:），通过 StaticPool 共享同一连接，
    保证 create_all 后各测试会话可见同一 Schema/数据。
  - 不依赖真实 MySQL（避免环境污染与连接依赖）。
  - 不调用真实 LLM / Embedding API（AI 流式 SSE 与 RAG 相关不在本文件覆盖，
    其逻辑通过导入校验 + 纯函数单测验证）。
"""

import os
import sys
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# 让测试能 import app.*
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from app.database import Base
    import app.models  # noqa: F401  确保所有模型已注册到 Base 元数据
    Base.metadata.create_all(eng)
    return eng


@pytest.fixture()
def db(engine):
    """每个测试一个独立会话，且每次清空数据，避免用例间污染。"""
    from app.database import Base
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    SessionTesting = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionTesting()
    yield session
    session.close()


def seed_user(session, username="alice", email="a@example.com", role="user", created_at=None):
    from app.models import User
    u = User(
        username=username,
        email=email,
        password_hash="x",
        role=role,
        is_active=1,
        created_at=created_at or datetime.now(),
    )
    session.add(u)
    session.commit()
    return u


def seed_recipe(session, title, cost=None, status="approved", author_id=None, created_at=None):
    from app.models import Recipe
    r = Recipe(
        title=title,
        description=f"{title}描述",
        estimated_cost=cost,
        status=status,
        is_deleted=0,
        author_id=author_id,
        view_count=0,
        favorite_count=0,
        created_at=created_at or datetime.now(),
    )
    session.add(r)
    session.commit()
    return r


def seed_meal_plan(session, title, recipe_ids, user_id=None, is_public=1, status="approved", created_at=None):
    from app.models import MealPlan, MealPlanItem
    p = MealPlan(
        user_id=user_id or 0,
        title=title,
        description=title + "套餐",
        is_public=is_public,
        status=status,
        is_deleted=0,
        created_at=created_at or datetime.now(),
    )
    session.add(p)
    session.commit()
    for i, rid in enumerate(recipe_ids):
        session.add(MealPlanItem(meal_plan_id=p.id, recipe_id=rid, sort_order=i))
    session.commit()
    return p


@pytest.fixture
def week_ago():
    return datetime.now() - timedelta(days=7)