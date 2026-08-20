"""
数据库连接层 —— SQLAlchemy 引擎、会话工厂、依赖注入

============================================================================
                    数据库连接设计说明（面向答辩）
============================================================================

【连接池配置】
  pool_size=20      → 连接池维持 20 个常驻连接，适合中等并发场景
  max_overflow=40   → 高峰期最多额外创建 40 个临时连接（总计 60 个）
  pool_pre_ping=True → 每次从连接池取出连接时，先 ping 一下验证连接是否有效

  pool_pre_ping 的重要性：
  MySQL 默认 wait_timeout=8小时，空闲连接超时后会被服务端断开。
  如果不启用 pool_pre_ping，SQLAlchemy 从池中取出一个已断开的连接
  并尝试执行 SQL 时就会报错（MySQL server has gone away）。
  启用后，每次使用前都会先 ping 验证，如果连接失效则自动重建。

【会话管理】
  SessionLocal：线程局部的会话工厂，autocommit=False 表示需要显式 commit。
  get_db()：FastAPI 依赖注入使用的生成器函数，请求开始创建会话，请求结束自动关闭。
  使用 yield 确保无论请求正常还是异常，finally 块都会执行 db.close()。
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import get_settings

settings = get_settings()

# 创建数据库引擎
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=20,
    max_overflow=40,
    pool_pre_ping=True,  # 每次使用前 ping 连接，防止使用已断开的连接
    echo=settings.DEBUG,
)

# SessionLocal 是线程局部的会话工厂，每次调用产生一个新的数据库会话
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# declarative_base() 创建 ORM 基类，所有模型类继承自它
Base = declarative_base()


def get_db():
    """
    获取数据库会话（FastAPI 依赖注入）。

    使用生成器 yield 模式：
      - 请求进入时创建会话并 yield 给路由函数
      - 请求结束后执行 finally 块，确保连接归还连接池

    示例用法：
      @router.get("/items")
      def get_items(db: Session = Depends(get_db)):
          return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()