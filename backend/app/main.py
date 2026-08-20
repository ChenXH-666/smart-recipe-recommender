"""
应用入口 —— FastAPI 应用工厂

============================================================================
                    FastAPI 应用架构说明（面向答辩）
============================================================================

本系统采用 FastAPI 框架，遵循以下架构设计：

【应用结构】
  main.py          → 应用入口，创建 FastAPI 实例，注册中间件和路由
  config.py        → 集中管理所有配置（数据库、JWT、LLM、RAG参数）
  database.py      → 数据库引擎和会话管理（SQLAlchemy）
  models/          → 数据库 ORM 模型（15张表，按用户/菜谱/互动/AI四大模块组织）
  schemas/         → Pydantic 数据验证模型（请求体/响应体定义）
  api/             → API 路由层（RESTful 接口，按业务模块拆分）
  services/        → 业务逻辑层（AI对话、RAG检索、推荐引擎）
  core/            → 基础设施（认证中间件、权限依赖注入、JWT处理）
  utils/           → 工具函数

【中间件管道】
  请求 → CORS中间件 → 全局异常处理 → 路由匹配 → 依赖注入 → 路由处理函数 → 响应

【路由组织】
  所有 API 以 /api/ 为前缀，按功能模块划分：
    /api/auth          → 注册、登录、JWT签发
    /api/recipes       → 菜谱 CRUD
    /api/users         → 用户中心（个人信息、收藏、历史）
    /api/reviews       → 菜谱点评
    /api/cooking-notes → 烹饪心得
    /api/meal-plans    → 套餐规划
    /api/ai            → AI 对话（流式 SSE）
    /api/recommendations → 智能推荐
    /api/admin         → 后台管理（审核、用户管理）

【安全设计】
  - CORS：生产环境必须通过 .env 的 CORS_ALLOW_ORIGINS 配置白名单
    注意：allow_origins=["*"] 与 allow_credentials=True 不能同时使用（浏览器规范禁止）
  - 全局异常处理：捕获未处理异常，统一返回 {code, message, detail} 格式
    避免向前端泄露堆栈/SQL等敏感信息
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import get_settings
from app.api import auth, recipes, users, reviews, cooking_notes, meal_plans, ai, admin, recommendations, stats

settings = get_settings()

# 全局日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理。
    在启动/关闭时执行初始化与清理操作（如数据库连接池预热、向量库加载等）。
    """
    # 启动时校验关键配置
    if settings.is_jwt_secret_weak:
        # 生产环境（DEBUG=False）弱密钥直接拒绝启动，杜绝占位值上线
        if not settings.DEBUG:
            raise RuntimeError(
                "JWT_SECRET_KEY 为弱密钥/占位值，生产环境禁止启动！"
                "请在 .env 中配置 secrets.token_urlsafe(48) 生成的强随机字符串。"
            )
        logger.warning(
            "⚠️ JWT_SECRET_KEY 为弱密钥/占位值，开发环境可继续运行，"
            "生产环境必须通过 .env 替换为强随机字符串（≥32 字符）！"
        )
    if not settings.EMBEDDING_API_KEY or not settings.LLM_API_KEY:
        logger.warning(
            "⚠️ EMBEDDING_API_KEY 或 LLM_API_KEY 未配置，AI/RAG 功能将无法正常工作。"
            "请在 .env 中配置真实 API Key。"
        )
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="基于大语言模型与RAG的智能菜谱推荐与菜单规划系统",
    lifespan=lifespan,
)

# CORS 中间件 —— 严格遵循浏览器规范：
# 当 allow_credentials=True 时，allow_origins 不能为 ["*"]，
# 必须配置具体的域名白名单。
# 开发环境：通过 CORS_ALLOW_ORIGINS=* 配置，自动将 allow_credentials 设为 False
# 生产环境：CORS_ALLOW_ORIGINS=https://example.com,https://www.example.com，allow_credentials=True
_origins = settings.cors_allow_origins_list
_allow_credentials = "*" not in _origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# 全局异常处理 —— 统一错误响应格式 {code, message, detail}
# ─────────────────────────────────────────────────────────────────────────────
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """处理 HTTPException，统一返回 {code, message, detail} 格式"""
    detail = exc.detail
    if isinstance(detail, dict) and "message" in detail:
        # 已经是结构化 detail，直接透传（含 Retry-After 等响应头，如限流 429）
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.status_code,
                "message": detail["message"],
                "detail": detail.get("detail"),
            },
            headers=getattr(exc, "headers", None),
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.status_code,
            "message": str(detail) if detail else "请求错误",
            "detail": None,
        },
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """处理请求参数校验失败，返回 422 + 详细错误信息

    使用 jsonable_encoder 转换错误列表，确保 ValueError 等
    非 JSON 原生类型（来自 model_validator）能被正确序列化。
    """
    from fastapi.encoders import jsonable_encoder
    return JSONResponse(status_code=422, content={
        "code": 422,
        "message": "请求参数校验失败",
        "detail": jsonable_encoder(exc.errors()),
    })


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """兜底处理未捕获异常，避免向前端泄露堆栈/SQL等敏感信息"""
    logger.exception(f"未处理异常: {request.method} {request.url.path} - {exc}")
    return JSONResponse(status_code=500, content={
        "code": 500,
        "message": "服务器内部错误，请稍后重试",
        "detail": None,  # 生产环境不向前端泄露内部错误
    })


# 静态文件服务：提供本地生成的菜谱封面图
static_dir = Path(__file__).parent.parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# 注册路由模块
app.include_router(auth.router, prefix="/api/auth", tags=["认证"])
app.include_router(recipes.router, prefix="/api/recipes", tags=["菜谱"])
app.include_router(users.router, prefix="/api/users", tags=["用户中心"])
app.include_router(reviews.router, prefix="/api/reviews", tags=["点评"])
app.include_router(cooking_notes.router, prefix="/api/cooking-notes", tags=["烹饪心得"])
app.include_router(meal_plans.router, prefix="/api/meal-plans", tags=["套餐"])
app.include_router(ai.router, prefix="/api/ai", tags=["AI助手"])
app.include_router(stats.router, prefix="/api/stats", tags=["统计"])
app.include_router(recommendations.router, prefix="/api/recommendations", tags=["智能推荐"])
app.include_router(admin.router, prefix="/api/admin", tags=["后台管理"])


@app.get("/")
async def root():
    """根路径 —— 返回应用基本信息"""
    return {
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",  # FastAPI 自动生成的 Swagger 文档
    }


@app.get("/api/health")
async def health_check():
    """
    健康检查端点 —— 用于监控和负载均衡探测。

    执行 SELECT 1 探测数据库连接：
      - 进程存活且数据库可用 → 200 {"status": "ok"}
      - 进程存活但数据库不可用 → 503 {"status": "degraded", "db": "error"}
        （区分"后端挂了"与"数据库挂了"两种故障场景）
    """
    try:
        from sqlalchemy import text
        from app.database import SessionLocal
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"健康检查：数据库连接异常 {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "db": "error"},
        )
