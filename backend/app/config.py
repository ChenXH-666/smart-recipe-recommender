"""
应用配置 —— 所有环境变量从 .env 文件读取，通过 Pydantic Settings 管理

============================================================================
                      配置项说明（面向答辩）
============================================================================

【安全建议】
  ⚠️ 生产环境中，API Key 和 JWT Secret 必须通过环境变量传入，不应硬编码在代码中。
  当前 JWT_SECRET_KEY 和 API Key 为开发阶段占位值，
  上线前应替换为强随机字符串并存入 .env 文件。

【数据库配置】
  DATABASE_URL 通过 @property 动态拼接，统一管理连接串中的 host/port/user/password。
  使用 utf8mb4 字符集以支持 emoji 等 4 字节 UTF-8 字符。

【JWT 配置】
  JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 1440（24 小时），适合用户体验与安全性的平衡。

【RAG 参数说明】
  RAG_TOP_K = 5        → 每次检索返回最相关的 5 个文档块
  RAG_CHUNK_SIZE = 500 → 每个文档块约 500 字符，过大则检索精度下降，过小则上下文不完整
  RAG_CHUNK_OVERLAP = 50 → 相邻块重叠 50 字符，防止关键信息在分块边界处被截断
  RAG_EMBEDDING_BATCH_SIZE = 64 → 每次 Embedding API 最多同时编码 64 个文本块，避免单次请求过大或额度耗尽
  RAG_CHECKPOINT_FILE = "./chroma_db/rebuild_checkpoint.json" → 全量重建向量库时的断点文件，记录已成功的文档 ID
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # 应用
    APP_NAME: str = "智能菜谱推荐系统"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True

    # 数据库 - MySQL
    DB_HOST: str = "localhost"
    DB_PORT: int = 3308
    DB_USER: str = "root"
    DB_PASSWORD: str = "123456"
    DB_NAME: str = "recipe_system"
    DB_CHARSET: str = "utf8mb4"

    @property
    def DATABASE_URL(self) -> str:
        """动态拼接数据库连接 URL"""
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            f"?charset={self.DB_CHARSET}"
        )

    # JWT —— 密钥必须通过 .env 注入，禁止硬编码
    JWT_SECRET_KEY: str = "CHANGE-ME-IN-PRODUCTION-USE-STRONG-RANDOM-SECRET"  # 仅开发占位，生产环境必须替换
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24小时

    # 已知弱密钥黑名单 —— 启动时校验，防止误用占位值上线
    _WEAK_JWT_SECRETS = frozenset({
        "CHANGE-ME-IN-PRODUCTION-USE-STRONG-RANDOM-SECRET",
        "recipe-system-jwt-secret-key-change-in-production",
        "secret",
        "changeme",
        "",
    })

    @property
    def is_jwt_secret_weak(self) -> bool:
        """JWT 密钥强度自检：黑名单值或长度 < 32 字符视为弱密钥"""
        secret = self.JWT_SECRET_KEY
        return secret in self._WEAK_JWT_SECRETS or len(secret) < 32

    # CORS 白名单 —— 生产环境通过 .env 配置具体域名，逗号分隔
    CORS_ALLOW_ORIGINS: str = "*"  # 开发期允许所有来源；生产环境应配置如 "https://example.com,https://www.example.com"

    # Chroma 向量数据库（本地持久化）
    # ⚠ 注意：ChromaDB 1.5.9 的 Rust 绑定在 Windows 上
    #   不支持含中文字符的持久化路径（会导致 HNSW 索引 data_level0.bin
    #   读取失败，抛出 "Error loading hnsw index"）。
    #   因此此路径必须是不含中文的绝对路径，推荐使用 F:/chroma_db 等纯 ASCII 路径。
    #   如需在其他机器部署，请修改此路径或通过 .env 注入。
    CHROMA_PERSIST_DIR: str = "F:/chroma_db"

    # Embedding（SiliconFlow BGE-M3 模型，1024维，多语言支持）
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    EMBEDDING_API_KEY: str = ""  # 必须通过 .env 注入，禁止硬编码
    EMBEDDING_API_URL: str = "https://api.siliconflow.cn/v1/embeddings"

    # LLM（SiliconFlow DeepSeek-R1-0528-Qwen3-8B，支持思考链推理）
    LLM_PROVIDER: str = "siliconflow"
    LLM_MODEL: str = "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"
    LLM_API_KEY: str = ""  # 必须通过 .env 注入，禁止硬编码
    LLM_BASE_URL: str = "https://api.siliconflow.cn/v1"
    LLM_TEMPERATURE: float = 0.7  # 0.7 平衡创造性与稳定性
    LLM_MAX_TOKENS: int = 2048

    # 菜谱封面图白名单域名（仅允许专业美食网站，符合项目硬约束）
    RECIPE_COVER_WHITELIST: str = "meishichina.com,xiachufang.com,douguo.com,xiangha.com"

    @property
    def cors_allow_origins_list(self) -> list[str]:
        """解析 CORS 允许的来源列表"""
        if not self.CORS_ALLOW_ORIGINS or self.CORS_ALLOW_ORIGINS == "*":
            return ["*"]
        return [s.strip() for s in self.CORS_ALLOW_ORIGINS.split(",") if s.strip()]

    @property
    def recipe_cover_whitelist_list(self) -> list[str]:
        """解析菜谱封面图白名单域名列表"""
        return [s.strip() for s in self.RECIPE_COVER_WHITELIST.split(",") if s.strip()]

    # RAG 参数
    RAG_TOP_K: int = 5                       # 检索返回的文档块数量
    RAG_CHUNK_SIZE: int = 500                # 文档分块大小（字符数）
    RAG_CHUNK_OVERLAP: int = 50              # 相邻块重叠字符数
    RAG_EMBEDDING_BATCH_SIZE: int = 64       # Embedding API 单次请求最大文本数
    RAG_CHECKPOINT_FILE: str = "./chroma_db/rebuild_checkpoint.json"  # 重建断点文件路径

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# 单例缓存 —— 使用 lru_cache 避免每次重复读取 .env 文件
@lru_cache()
def get_settings() -> Settings:
    return Settings()