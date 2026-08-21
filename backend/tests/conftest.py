# -*- coding: utf-8 -*-
"""pytest 根配置 —— 路径注入 + 共享 fixture。

分层测试设计：
  - 纯函数层（portions/validation/security/config 等）：不需要数据库。
  - 模型层 / 服务层 / 接口层：通过 SQLite 内存库 + SQLAlchemy StaticPool 隔离，
    保证多线程（TestClient 线程池）下所有连接共享同一内存库。
  - 外部依赖（Chroma / LLM）一律 mock，绝不触碰真实 MySQL / SiliconFlow / 向量库。
"""
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# 确保 backend/ 在 sys.path 上，使 `import app` 可用
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# 测试期间屏蔽高噪音三方库日志
for _name in ("chromadb", "httpx", "httpcore", "nltk"):
    logging.getLogger(_name).setLevel(logging.ERROR)

from app.database import Base  # noqa: E402
from app import models as _models  # noqa: F401,E402  # 注册全部表到 Base.metadata


@pytest.fixture()
def engine():
    """SQLite 内存引擎。

    关键：使用 StaticPool 使所有连接共享同一内存数据库，
    否则 TestClient 的线程池会为每个线程创建独立的空库，导致"no such table"。
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db(engine):
    """可写会话（服务层 / 模型层 / 预置回归测试使用）。"""
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def db_session(db):
    """db 的便捷别名，命名更语义化。"""
    return db


@pytest.fixture()
def db_engine(engine):
    """引擎别名，供接口层 TestClient 注册隔离依赖使用。"""
    return engine


@pytest.fixture()
def week_ago():
    """与 app/api/stats.py 中一致的"近 7 天"时间基准（naive 本地时间）。"""
    return datetime.now() - timedelta(days=7)


@pytest.fixture(autouse=True)
def _clear_rate_limiter():
    """认证接口限流为全局状态；逐用例清理，保证测试确定性、互不干扰。"""
    from app.core import rate_limit
    rate_limit._limiter._store.clear()
    yield
    rate_limit._limiter._store.clear()


@pytest.fixture()
def client(db_engine, monkeypatch):
    """FastAPI TestClient —— 覆盖 get_db 依赖注入 SQLite 会话，并 stub Chroma 同步。"""
    from fastapi.testclient import TestClient
    from sqlalchemy.orm import sessionmaker as _sessionmaker

    from app.main import app
    from app.database import get_db
    import app.api.recipes as _recipes_api
    import app.api.cooking_notes as _notes_api
    import app.api.admin as _admin_api

    Session = _sessionmaker(bind=db_engine, expire_on_commit=False)

    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    # 屏蔽真实向量库同步，避免测试触碰 Chroma
    monkeypatch.setattr(_recipes_api, "sync_recipe_to_chroma", lambda recipe: None)
    monkeypatch.setattr(_recipes_api, "remove_from_chroma", lambda *a, **k: None)
    monkeypatch.setattr(_notes_api, "sync_cooking_note_to_chroma", lambda note: None)
    monkeypatch.setattr(_notes_api, "remove_from_chroma", lambda *a, **k: None)
    monkeypatch.setattr(_admin_api, "sync_recipe_to_chroma", lambda recipe: None)
    monkeypatch.setattr(_admin_api, "remove_from_chroma", lambda *a, **k: None)

    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()