"""
接口性能基准脚本 —— 论文 6.5 节"性能测试"数据来源（检索优化待办·方案A）

测量对象：已启动的后端服务（真实 HTTP 调用，不经 TestClient 绕过网络栈）
  A. 纯接口串行基准（N=100，预热 5 次后统计）：菜谱列表 / 菜谱详情 / 菜谱搜索 /
     个性化推荐 / 用户登录，记录 avg / P50 / P95 / P99 / max
  B. AI 对话首包延迟：POST /api/ai/chat（SSE 流式），测首帧到达时间与整段回复时长
     （注意：真实调用 Embedding/Rerank/LLM 三类外部 API，消耗额度，样本默认 6 条）
  C. 并发基准：菜谱列表接口在 10 / 20 / 50 并发下的 QPS、P95 与错误率
  D. 缓存区分：首页统计接口（60s TTL 进程内缓存）的"冷启动（缓存过期后首次）"
     与"缓存命中"两组延迟分开测量

测试条件（结果不含网络开销、绝对值偏乐观）：
  - 客户端与后端同机 localhost、单进程单 Worker、连接复用（keep-alive）
  - 测量期间不做其他重负载操作；推荐接口的延迟含一次外部 Embedding API 调用

用法（先 conda activate food；后端须以 --port 8000 --proxy-headers 启动）：
    需预先注册一个用于压测的普通账号，凭据通过参数或环境变量传入（脚本不内置默认账号）：
    cd backend
    python import_data/bench_api.py --username bench_user --password '<密码>'   # 全量基准（含 AI 首包）
    python import_data/bench_api.py --username bench_user --password '<密码>' --skip-ai  # 跳过 AI 首包（省额度）
    # 也可用环境变量：BENCH_USERNAME / BENCH_PASSWORD
    python import_data/bench_api.py --serial-n 50    # 改串行样本数
    python import_data/bench_api.py --concurrency 10,20,50 --conc-total 200
    python import_data/bench_api.py --no-cold-wait   # 不等统计缓存过期

为什么需要 --proxy-headers：登录接口限流为 10 次/分钟/IP（core/rate_limit.py），
串行基准要取 100 个有效样本，脚本为每个登录请求构造独立的 X-Forwarded-For
以模拟不同客户端（后端启用 --proxy-headers 后按该头取真实访客 IP，与生产部署
姿势一致）；若后端未启用该参数，脚本会检出 429 并自动把登录样本降为限流窗口
内的 10 次，同时在结果中明确标注。

结果输出：控制台打印 + 落盘 bench_api_results.md / bench_api_results.json
（机器相关本地实验产物，已在 .gitignore 忽略）
"""

import os
import sys
import json
import time
import asyncio
import argparse
import statistics
from pathlib import Path
from datetime import datetime

import requests

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.config import get_settings  # noqa: E402  （仅读取 .env 配置用于报告，不初始化 DB/Chroma）

DEFAULT_CONCURRENCY = [10, 20, 50]
DEFAULT_SERIAL_N = 100
DEFAULT_AI_N = 6
DEFAULT_COLD_WAIT = 61  # 首页统计缓存 TTL=60s，等待 61s 保证过期

# AI 首包测试样本（各条独立会话，避免同质；控制在默认 6 条以内，真烧额度）
AI_MESSAGES = [
    "推荐一道简单的家常菜",
    "红烧肉怎么做才软糯",
    "适合减脂期的低油低脂晚餐有哪些",
    "两个人吃，预算50元，推荐几个菜",
    "西红柿炒鸡蛋怎么做",
    "有什么快手菜推荐",
]

# 串行基准中登录接口使用的模拟客户端 IP 段（RFC1918 私有地址）
_FAKE_IP_PREFIX = "10.77"


def percentile(sorted_values: list, q: float) -> float:
    """线性插值分位数（与 numpy.percentile 默认口径一致）"""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = q * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def summarize(latencies_ms: list, errors: int = 0) -> dict:
    """把一组耗时（毫秒）汇总为 avg / P50 / P95 / P99 / max"""
    s = sorted(latencies_ms)
    return {
        "n": len(s) + errors,
        "ok": len(s),
        "errors": errors,
        "avg_ms": statistics.fmean(s) if s else 0.0,
        "p50_ms": percentile(s, 0.50),
        "p95_ms": percentile(s, 0.95),
        "p99_ms": percentile(s, 0.99),
        "max_ms": s[-1] if s else 0.0,
    }


# ──────────────────────────── A. 纯接口串行基准 ────────────────────────────

def bench_serial(name: str, do_request, n: int, warmup: int = 5) -> dict:
    """串行测量单个接口：预热 warmup 次（不计入统计）后跑 n 次"""
    for _ in range(warmup):
        try:
            do_request()
        except Exception:
            pass

    latencies, errors = [], 0
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            resp = do_request()
            dt = (time.perf_counter() - t0) * 1000
            if resp.status_code == 200:
                latencies.append(dt)
            else:
                errors += 1
        except Exception:
            errors += 1
    result = summarize(latencies, errors)
    result["name"] = name
    print(f"  {name}: avg={result['avg_ms']:.1f}ms p95={result['p95_ms']:.1f}ms "
          f"p99={result['p99_ms']:.1f}ms max={result['max_ms']:.1f}ms "
          f"errors={errors}/{result['n']}")
    return result


def run_serial_benchmarks(base_url: str, session: requests.Session, token: str,
                          recipe_ids: list, keyword: str, n: int,
                          username: str, password: str,
                          cold_wait: int = None) -> dict:
    """串行基准主入口，返回 {"items": [...], "stats_cache": {...}}"""
    auth = {"Authorization": f"Bearer {token}"}
    items = []

    print("[A] 串行基准（预热 5 次，不计入统计）")

    items.append(bench_serial(
        "菜谱列表 GET /api/recipes",
        lambda: session.get(f"{base_url}/api/recipes", params={"page": 1, "page_size": 20}),
        n,
    ))

    # 详情接口轮换 10 个真实 ID；未登录访问（不计浏览历史，仅含 view_count 原子更新）
    idx = {"i": 0}

    def _detail():
        rid = recipe_ids[idx["i"] % len(recipe_ids)]
        idx["i"] += 1
        return session.get(f"{base_url}/api/recipes/{rid}")

    items.append(bench_serial(f"菜谱详情 GET /api/recipes/{{id}}（轮换 {len(recipe_ids)} 个 ID）",
                              _detail, n))

    items.append(bench_serial(
        f"菜谱搜索 GET /api/recipes?keyword={keyword}",
        lambda: session.get(f"{base_url}/api/recipes",
                            params={"keyword": keyword, "page": 1, "page_size": 20}),
        n,
    ))

    items.append(bench_serial(
        "个性化推荐 GET /api/recommendations/personalized（含外部 Embedding 调用）",
        lambda: session.get(f"{base_url}/api/recommendations/personalized",
                            params={"limit": 10}, headers=auth),
        n,
    ))

    # 登录：每次请求独立 X-Forwarded-For，绕开"10 次/分钟/IP"限流以获得 n 个有效样本
    login_body = {"username": username, "password": password}
    login_idx = {"i": 0}

    def _login():
        login_idx["i"] += 1
        xff = f"{_FAKE_IP_PREFIX}.{login_idx['i'] // 250}.{login_idx['i'] % 250 + 1}"
        return session.post(f"{base_url}/api/auth/login", json=login_body,
                            headers={"X-Forwarded-For": xff})

    login_stat = bench_serial("用户登录 POST /api/auth/login（bcrypt 校验，每请求独立客户端 IP）",
                              _login, n)
    items.append(login_stat)

    # 统计缓存：冷（缓存过期后首次，7 次聚合 COUNT）与热（TTL 内命中）分开
    stats_cache = measure_stats_cache(base_url, session, n, cold_wait)

    return {"items": items, "stats_cache": stats_cache}


def measure_stats_cache(base_url: str, session: requests.Session, n: int,
                        cold_wait: int = DEFAULT_COLD_WAIT) -> dict:
    """首页统计接口：冷启动 vs 缓存命中。

    cold_wait=None 表示跳过冷测量（--no-cold-wait）：此时不产出冷启动数字，
    避免把缓存命中值误标为冷启动。
    """
    print("[D] 首页统计缓存（冷启动 / 缓存命中）")
    cold_ms = None
    cold_ok = False
    if cold_wait is not None:
        # 先请求一次激活缓存，再等待 TTL 过期，保证"冷"是真冷
        session.get(f"{base_url}/api/stats")
        print(f"  等待 {cold_wait}s 使统计缓存过期 …")
        time.sleep(cold_wait)

        t0 = time.perf_counter()
        resp = session.get(f"{base_url}/api/stats")
        cold_ms = (time.perf_counter() - t0) * 1000
        cold_ok = resp.status_code == 200
        print(f"  冷启动（缓存过期后首次）：{cold_ms:.1f}ms")
    else:
        print("  已跳过冷启动测量（--no-cold-wait）")

    hot = bench_serial("统计接口 GET /api/stats（缓存命中）",
                       lambda: session.get(f"{base_url}/api/stats"), n)
    return {
        "cold_ms": cold_ms if cold_ok else None,
        "cold_ok": cold_ok,
        "hot": hot,
    }


# ──────────────────────────── B. AI 对话首包延迟 ────────────────────────────

def run_ai_sse_benchmark(base_url: str, session: requests.Session, token: str, n: int) -> list:
    """SSE 首包延迟：POST /api/ai/chat，测首帧（首个 data: 行）到达时间与总时长"""
    print(f"[B] AI 对话首包延迟（SSE，n={n}，真实调用 Embedding/Rerank/LLM）")
    results = []
    for i in range(n):
        msg = AI_MESSAGES[i % len(AI_MESSAGES)]
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "text/event-stream",
            # 每条请求独立客户端 IP，避免与后端"20 次/分钟/IP"的 AI 限流相互干扰
            "X-Forwarded-For": f"{_FAKE_IP_PREFIX}.{100 + i}.1",
        }
        t0 = time.perf_counter()
        first_frame_ms = None
        total_chars = 0
        try:
            resp = session.post(f"{base_url}/api/ai/chat", json={"message": msg},
                                headers=headers, stream=True, timeout=(10, 120))
            if resp.status_code != 200:
                print(f"  [{i + 1}/{n}] {msg!r} → HTTP {resp.status_code}，跳过")
                resp.close()
                continue
            for line in resp.iter_lines(decode_unicode=True):
                if first_frame_ms is None and line and line.startswith("data: "):
                    first_frame_ms = (time.perf_counter() - t0) * 1000
                if line and line.startswith("data: "):
                    total_chars += len(line)
            total_s = time.perf_counter() - t0
            resp.close()
        except Exception as e:
            print(f"  [{i + 1}/{n}] {msg!r} → 异常 {e}")
            continue
        results.append({
            "message": msg,
            "first_frame_ms": first_frame_ms,
            "total_s": total_s,
            "sse_chars": total_chars,
        })
        ff = f"{first_frame_ms:.0f}ms" if first_frame_ms is not None else "无首帧"
        print(f"  [{i + 1}/{n}] {msg!r}: 首帧={ff} 总时长={total_s:.2f}s")
    return results


# ──────────────────────────── C. 并发基准 ────────────────────────────

async def _conc_level(url: str, level: int, total: int) -> dict:
    """单个并发级别：限制同时在途请求数为 level，共发 total 个请求"""
    import httpx

    limits = httpx.Limits(max_connections=level + 10, max_keepalive_connections=level + 10)
    latencies, errors = [], 0
    sem = asyncio.Semaphore(level)

    async with httpx.AsyncClient(limits=limits, timeout=30) as client:
        # 预热连接池
        try:
            await client.get(url)
        except Exception:
            pass

        async def one():
            nonlocal errors
            async with sem:
                t = time.perf_counter()
                try:
                    r = await client.get(url)
                    dt = (time.perf_counter() - t) * 1000
                    if r.status_code == 200:
                        latencies.append(dt)
                    else:
                        errors += 1
                except Exception:
                    errors += 1

        t_all = time.perf_counter()
        await asyncio.gather(*(one() for _ in range(total)))
        elapsed = time.perf_counter() - t_all

    stat = summarize(latencies, errors)
    stat.update({
        "concurrency": level,
        "total": total,
        "elapsed_s": elapsed,
        "qps": total / elapsed if elapsed > 0 else 0.0,
    })
    return stat


def run_concurrency_benchmarks(base_url: str, levels: list, total: int) -> list:
    """并发基准：菜谱列表接口（纯 DB 查询，不含外部 API）"""
    print(f"[C] 并发基准（接口：菜谱列表；每级 {total} 个请求）")
    url = f"{base_url}/api/recipes?page=1&page_size=20"
    results = []
    for level in levels:
        stat = asyncio.run(_conc_level(url, level, total))
        results.append(stat)
        print(f"  并发 {level:>2}: QPS={stat['qps']:.1f} P50={stat['p50_ms']:.1f}ms "
              f"P95={stat['p95_ms']:.1f}ms P99={stat['p99_ms']:.1f}ms "
              f"错误={stat['errors']}/{stat['total']}")
    return results


# ──────────────────────────── 前置检查 ────────────────────────────

def preflight(base_url: str, session: requests.Session, username: str, password: str) -> dict:
    """健康检查 + 登录取 token + 校验数据（菜谱数、样本 ID、搜索非空）"""
    print("[0] 前置检查")
    r = session.get(f"{base_url}/api/health", timeout=5)
    assert r.status_code == 200 and r.json().get("status") == "ok", "健康检查失败，后端未就绪"
    print("  /api/health → ok")

    r = session.post(f"{base_url}/api/auth/login",
                     json={"username": username, "password": password}, timeout=10)
    assert r.status_code == 200, f"登录失败 HTTP {r.status_code}: {r.text[:200]}"
    token = r.json()["access_token"]
    print(f"  登录成功（{username}），已取得 JWT")

    stats = session.get(f"{base_url}/api/stats", timeout=10).json()
    print(f"  数据规模：菜谱 {stats['total_recipes']} / 套餐 {stats['total_meal_plans']} / "
          f"用户 {stats['total_users']}")

    r = session.get(f"{base_url}/api/recipes", params={"page": 1, "page_size": 10}, timeout=10)
    assert r.status_code == 200 and r.json()["items"], "菜谱列表为空，无法取样本 ID"
    recipe_ids = [it["id"] for it in r.json()["items"]]
    print(f"  样本菜谱 ID：{recipe_ids[:5]} …（共 {len(recipe_ids)} 个轮换使用）")

    keyword = "红烧"
    r = session.get(f"{base_url}/api/recipes",
                    params={"keyword": keyword, "page": 1, "page_size": 20}, timeout=10)
    assert r.status_code == 200 and r.json()["total"] > 0, f"搜索关键词 {keyword!r} 无结果"
    print(f"  搜索关键词 {keyword!r} → {r.json()['total']} 条结果")

    return {"token": token, "recipe_ids": recipe_ids, "keyword": keyword, "stats": stats}


def check_login_xff(base_url: str, session: requests.Session,
                    username: str, password: str) -> bool:
    """自检：确认后端采信 X-Forwarded-For（--proxy-headers）。
    连发 12 次带同一 XFF 的登录请求：第 11 次起应返回 429（限流 10 次/分钟/IP）。
    若全部 200 → XFF 未被采信（后端未启用 --proxy-headers）。"""
    body = {"username": username, "password": password}
    xff = f"{_FAKE_IP_PREFIX}.250.250"
    statuses = []
    for _ in range(12):
        r = session.post(f"{base_url}/api/auth/login", json=body,
                         headers={"X-Forwarded-For": xff}, timeout=10)
        statuses.append(r.status_code)
    trusted = 429 in statuses
    print(f"  限流自检：{'XFF 已采信（第 11 次起 429，可按 IP 隔离）' if trusted else '⚠ XFF 未被采信，登录样本将降为 10'}")
    return trusted


# ──────────────────────────── 结果输出 ────────────────────────────

def fmt(x: float) -> str:
    return f"{x:.1f}"


def render_markdown(report: dict) -> str:
    meta = report["meta"]
    lines = []
    lines.append("# 接口性能基准结果（bench_api.py）\n")
    lines.append(f"- 测量时间：{meta['timestamp']}")
    lines.append(f"- 服务地址：{meta['base_url']}（客户端与后端同机，localhost 直连，无网络开销）")
    lines.append(f"- 服务形态：uvicorn 单进程单 Worker（--port 8000），连接复用（keep-alive）")
    lines.append(f"- 数据规模：菜谱 {meta['dataset']['total_recipes']} / 套餐 "
                 f"{meta['dataset']['total_meal_plans']} / 用户 {meta['dataset']['total_users']}")
    lines.append(f"- 关键配置：DEBUG={meta['settings']['DEBUG']}、SQL_ECHO={meta['settings']['SQL_ECHO']}、"
                 f"混合检索={meta['settings']['RAG_HYBRID_SEARCH']}、"
                 f"精排={meta['settings']['RERANK_ENABLED']}（α={meta['settings']['RERANK_ALPHA']}）、"
                 f"LLM={meta['settings']['LLM_MODEL']}、Embedding={meta['settings']['EMBEDDING_MODEL']}")
    lines.append(f"- 说明：串行基准每组 N={meta['serial_n']}（预热 5 次不计入）；"
                 f"本机同机测量，绝对值为乐观值\n")

    lines.append("## A. 纯接口串行基准\n")
    lines.append("| 接口 | N | avg (ms) | P50 (ms) | P95 (ms) | P99 (ms) | max (ms) | 错误 |")
    lines.append("|------|---|------|------|------|------|------|------|")
    for it in report["serial"]["items"]:
        lines.append(f"| {it['name']} | {it['ok']} | {fmt(it['avg_ms'])} | {fmt(it['p50_ms'])} | "
                     f"{fmt(it['p95_ms'])} | {fmt(it['p99_ms'])} | {fmt(it['max_ms'])} | {it['errors']} |")
    sc = report["serial"]["stats_cache"]
    lines.append("")
    lines.append("## B. 首页统计缓存（60s TTL）\n")
    lines.append("| 场景 | 延迟 | 说明 |")
    lines.append("|------|------|------|")
    if sc["cold_ms"] is not None:
        lines.append(f"| 冷启动（缓存过期后首次） | {fmt(sc['cold_ms'])} ms | 执行 7 次聚合 COUNT 后写缓存 |")
    hot = sc["hot"]
    lines.append(f"| 缓存命中（TTL 内） | avg {fmt(hot['avg_ms'])} / P95 {fmt(hot['p95_ms'])} ms | "
                 f"N={hot['ok']}，直接返回内存字典 |")
    lines.append("")

    if report["ai_sse"]:
        lines.append("## C. AI 对话首包延迟（SSE，真实调用外部 API）\n")
        lines.append("| # | 用户输入 | 首帧 (ms) | 整段回复时长 (s) |")
        lines.append("|---|---------|------|------|")
        for i, a in enumerate(report["ai_sse"], 1):
            ff = fmt(a["first_frame_ms"]) if a["first_frame_ms"] is not None else "—"
            lines.append(f"| {i} | {a['message']} | {ff} | {a['total_s']:.2f} |")
        ffs = [a["first_frame_ms"] for a in report["ai_sse"] if a["first_frame_ms"] is not None]
        if ffs:
            lines.append(f"\n首帧延迟：avg {fmt(statistics.fmean(ffs))} ms / "
                         f"min {fmt(min(ffs))} / max {fmt(max(ffs))}（n={len(ffs)}）\n")

    lines.append("## D. 并发基准（菜谱列表接口）\n")
    lines.append("| 并发数 | 总请求 | QPS | P50 (ms) | P95 (ms) | P99 (ms) | 错误率 |")
    lines.append("|--------|--------|-----|------|------|------|--------|")
    for it in report["concurrency"]:
        err_rate = it["errors"] / it["total"] * 100 if it["total"] else 0
        lines.append(f"| {it['concurrency']} | {it['total']} | {it['qps']:.1f} | {fmt(it['p50_ms'])} | "
                     f"{fmt(it['p95_ms'])} | {fmt(it['p99_ms'])} | {err_rate:.2f}% |")
    lines.append("")
    lines.append(f"> 测试条件：单 Worker、本机 localhost、keep-alive 连接复用，"
                 f"菜谱列表为纯数据库查询（不含外部 API）。\n")
    return "\n".join(lines)


# ──────────────────────────── 主流程 ────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="后端接口性能基准（论文 6.5 性能测试）")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--username", default=os.getenv("BENCH_USERNAME", ""),
                        help="压测账号（普通用户即可），亦可用环境变量 BENCH_USERNAME")
    parser.add_argument("--password", default=os.getenv("BENCH_PASSWORD", ""),
                        help="压测账号密码，亦可用环境变量 BENCH_PASSWORD")
    parser.add_argument("--serial-n", type=int, default=DEFAULT_SERIAL_N, help="串行基准样本数")
    parser.add_argument("--skip-ai", action="store_true", help="跳过 AI 首包测试（省 LLM 额度）")
    parser.add_argument("--ai-n", type=int, default=DEFAULT_AI_N, help="AI 首包样本数（真烧额度）")
    parser.add_argument("--concurrency", default=",".join(map(str, DEFAULT_CONCURRENCY)))
    parser.add_argument("--conc-total", type=int, default=200, help="每个并发级别的总请求数")
    parser.add_argument("--no-cold-wait", action="store_true", help="不等统计缓存过期（跳过冷启动测量）")
    parser.add_argument("--out-prefix", default="bench_api_results")
    args = parser.parse_args()

    if not args.username or not args.password:
        parser.error("缺少压测账号：请用 --username/--password 传入，或设置环境变量 "
                     "BENCH_USERNAME/BENCH_PASSWORD（账号需预先在系统中注册，建议使用专门的压测账号）")

    settings = get_settings()
    session = requests.Session()
    session.headers["User-Agent"] = "recipe-bench/1.0"

    print(f"=== 接口性能基准 @ {args.base_url} ===\n")
    ctx = preflight(args.base_url, session, args.username, args.password)

    xff_ok = check_login_xff(args.base_url, session, args.username, args.password)
    login_n = args.serial_n if xff_ok else 10

    report = {"meta": {}}
    cold_wait = None if args.no_cold_wait else DEFAULT_COLD_WAIT
    serial_result = run_serial_benchmarks(
        args.base_url, session, ctx["token"], ctx["recipe_ids"], ctx["keyword"],
        args.serial_n, args.username, args.password, cold_wait,
    )
    # 若 XFF 未被采信，登录只统计限流窗口内的有效样本
    if not xff_ok:
        for it in serial_result["items"]:
            if "login" in it["name"]:
                it["name"] += f"（N={login_n}，限流约束）"
    report["serial"] = serial_result

    ai_results = []
    if not args.skip_ai:
        ai_results = run_ai_sse_benchmark(args.base_url, session, ctx["token"], args.ai_n)
    else:
        print("[B] 已按 --skip-ai 跳过 AI 首包测试")
    report["ai_sse"] = ai_results

    levels = [int(x) for x in args.concurrency.split(",") if x.strip()]
    report["concurrency"] = run_concurrency_benchmarks(args.base_url, levels, args.conc_total)

    report["meta"] = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "base_url": args.base_url,
        "serial_n": args.serial_n,
        "ai_n": len(ai_results),
        "concurrency_levels": levels,
        "conc_total": args.conc_total,
        "dataset": ctx["stats"],
        "settings": {
            "DEBUG": settings.DEBUG,
            "SQL_ECHO": settings.SQL_ECHO,
            "RAG_HYBRID_SEARCH": settings.RAG_HYBRID_SEARCH,
            "RERANK_ENABLED": settings.RERANK_ENABLED,
            "RERANK_ALPHA": settings.RERANK_ALPHA,
            "LLM_MODEL": settings.LLM_MODEL,
            "EMBEDDING_MODEL": settings.EMBEDDING_MODEL,
        },
    }

    out_dir = Path(__file__).parent
    md_path = out_dir / f"{args.out_prefix}.md"
    json_path = out_dir / f"{args.out_prefix}.json"
    md_path.write_text(render_markdown(report), encoding="utf-8")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== 完成 ===")
    print(f"Markdown: {md_path}")
    print(f"JSON    : {json_path}")
    print(f"- 菜谱列表 avg={fmt(report['serial']['items'][0]['avg_ms'])}ms "
          f"P99={fmt(report['serial']['items'][0]['p99_ms'])}ms")
    if report["concurrency"]:
        c50 = report["concurrency"][-1]
        print(f"- 并发 {c50['concurrency']}: QPS={c50['qps']:.1f} P95={fmt(c50['p95_ms'])}ms")


if __name__ == "__main__":
    main()