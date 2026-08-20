"""内存限流器 —— 防止认证接口被暴力破解/撞库

============================================================================
                      设计说明（面向答辩）
============================================================================

【为什么需要限流】
  即使密码使用 bcrypt 哈希、登录失败统一返回错误信息，攻击者仍可：
    1. 暴力破解：对单个账户高频尝试密码
    2. 撞库攻击：用泄露的"账号+密码"字典批量尝试
    3. 注册滥用：批量创建垃圾账户
  限流是认证安全的最后一道防线，与密码强度校验、bcrypt 哈希形成纵深防御。

【算法选择 —— 滑动窗口日志】
  采用滑动窗口（记录每次请求时间戳，剔除窗口外过期记录）而非固定窗口：
    - 固定窗口在边界处可被突破（窗口末尾+下一窗口开头 = 2倍流量）
    - 滑动窗口更精确，无边界突变问题
    - 单机内存实现，无需 Redis，适合单实例部署的毕业设计场景

【线程安全】
  使用 asyncio.Lock 保护 _store 字典的并发访问。
  清理过期条目采用惰性策略：每次检查时顺带清理，无需独立清理线程。

【多实例部署注意】
  本实现为单机内存限流。若未来横向扩展为多实例，
  应替换为 Redis + sliding-window 原子脚本，或使用 slowapi 等成熟中间件。

【键策略】
  以客户端 IP 为键（request.client.host）。
  生产环境若部署在反向代理后，需从 X-Forwarded-For 取真实 IP
  （此时应配置 uvicorn --proxy-headers，并在 Request.client 中获取真实 IP）。
"""

import time
from collections import defaultdict, deque
from typing import Deque, Dict

from fastapi import HTTPException, Request, status


class _SlidingWindowLimiter:
    """滑动窗口限流器（单例）"""

    def __init__(self) -> None:
        # key -> 该 key 在窗口内的请求时间戳队列（单调递增）
        self._store: Dict[str, Deque[float]] = defaultdict(deque)
        # asyncio.Lock 在首次事件循环中创建，避免 "no running event loop" 警告
        self._lock = None

    def _get_lock(self):
        """惰性创建 asyncio.Lock，绑定到当前运行的事件循环"""
        import asyncio
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def check(self, key: str, max_requests: int, window_seconds: int) -> None:
        """
        检查 key 是否超过限流阈值。超过则抛 429。

        参数：
          key: 限流维度标识（如 "login:127.0.0.1"）
          max_requests: 窗口内允许的最大请求次数
          window_seconds: 窗口大小（秒）
        """
        lock = self._get_lock()
        async with lock:
            now = time.monotonic()
            window_start = now - window_seconds
            bucket = self._store[key]

            # 惰性清理：剔除窗口外的过期时间戳
            while bucket and bucket[0] < window_start:
                bucket.popleft()

            if len(bucket) >= max_requests:
                # 计算还需等待多久才能再次请求（最早过期时间 - now）
                retry_after = int(bucket[0] + window_seconds - now) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "message": "请求过于频繁，请稍后再试",
                        "detail": f"超过限流阈值 {max_requests}次/{window_seconds}秒，"
                                  f"请 {retry_after} 秒后重试",
                    },
                    headers={"Retry-After": str(retry_after)},
                )

            # 记录本次请求
            bucket.append(now)

            # 惰性清理空队列，避免 _store 无限增长
            if not bucket:
                self._store.pop(key, None)


# 全局单例 —— 模块级实例化，所有请求共享同一限流状态
_limiter = _SlidingWindowLimiter()


def rate_limit(max_requests: int, window_seconds: int, action: str = "request"):
    """
    FastAPI 依赖：对路由按客户端 IP 限流。

    用法：
        @router.post("/login",
                     dependencies=[Depends(rate_limit(10, 60, "login"))])
        def login(...): ...

    参数：
      max_requests: 窗口内允许的最大请求次数
      window_seconds: 窗口大小（秒）
      action: 业务动作名（login/register），用于限流键命名，便于日志排查
    """
    async def _dependency(request: Request) -> None:
        # 取客户端 IP；反向代理部署时应从 X-Forwarded-For 取真实 IP
        client_host = request.client.host if request.client else "unknown"
        key = f"{action}:{client_host}"
        await _limiter.check(key, max_requests, window_seconds)

    return _dependency
