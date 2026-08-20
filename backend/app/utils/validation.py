"""
通用工具函数 —— 封面图白名单校验、URL 安全检查等

============================================================================
                    工具函数设计说明（面向答辩）
============================================================================

【封面图白名单校验】
  PRD 第 3.2 节明确要求：菜谱封面图仅允许来自专业美食网站白名单
  （meishichina.com、xiachufang.com、douguo.com、xiangha.com），且必须使用 HTTPS。

  本模块提供 is_safe_recipe_cover_url() 函数，在菜谱创建/更新时调用，
  拦截非白名单域名（防止瓷器、文档、风景等不相关图片）和非 HTTPS 链接（防止混合内容）。

  本地路径（如 /static/recipe_covers/xxx.jpg）默认放行 —— 这些图片由系统生成。
"""

import re
from urllib.parse import urlparse
from typing import Optional
from functools import lru_cache

from app.config import get_settings


@lru_cache()
def _get_settings():
    return get_settings()


def is_safe_recipe_cover_url(url: Optional[str]) -> bool:
    """
    校验菜谱封面图 URL 是否符合安全策略。

    规则：
      1. None/空字符串：放行（业务层用默认封面兜底）
      2. 本地路径（以 / 开头且不含协议头）：放行
      3. 完整 URL：
         - 必须是 HTTPS
         - 域名必须在白名单（meishichina/xiachufang/douguo/xiangha）
      4. 其他情况：拒绝
    """
    if not url or not url.strip():
        return True  # 空值交由业务层用默认封面兜底

    url = url.strip()

    # 本地静态路径（如 /static/recipe_covers/recipe_1.jpg）
    if url.startswith("/") and not url.startswith("//"):
        return True

    # 解析完整 URL
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    scheme = (parsed.scheme or "").lower()
    hostname = (parsed.hostname or "").lower()

    if not scheme or not hostname:
        return False

    # 必须 HTTPS
    if scheme != "https":
        return False

    # 域名白名单检查（支持子域名，如 i.meishichina.com）
    whitelist = _get_settings().recipe_cover_whitelist_list
    return any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in whitelist
    )


def sanitize_recipe_cover(url: Optional[str], default: str = "/static/recipe_covers/default.jpg") -> str:
    """
    清洗菜谱封面图 URL：若不安全则回退到默认封面。
    """
    if is_safe_recipe_cover_url(url):
        # 进一步检查非空且非假链接
        if url and url.strip() and "example.com" not in url:
            return url.strip()
    return default


def parse_int_list(s: Optional[str], max_items: int = 50) -> list[int]:
    """
    安全解析逗号分隔的整数列表，避免 ValueError 导致 500。

    参数：
      s: 原始字符串（如 "1,2,3"）
      max_items: 最大允许的 ID 数量，防止恶意超长请求

    返回：成功解析的整数列表；输入非法返回空列表
    """
    if not s:
        return []
    items = []
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            items.append(int(part))
        except ValueError:
            # 跳过非数字部分，避免整个请求失败
            continue
        if len(items) >= max_items:
            break
    return items
