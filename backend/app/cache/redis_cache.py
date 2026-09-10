"""Redis 缓存层 — 意图识别缓存 + 检索结果缓存

设计原则：缓存是"加速器"而不是"依赖"，可用性永远优先于命中率：

1. 降级直连：Redis 不可达 / CACHE_ENABLED=False 时，所有读写变 no-op，
   业务路径零感知（对应 config.REDIS_URL / config.CACHE_ENABLED）
2. 熔断冷却：连续 2 次操作失败即进入 60s 冷却期，期间不再尝试连接——
   避免高并发下每个请求都白付一次 TCP 连接超时（错误也是要花钱的）
3. 键设计：业务前缀 + 归一化内容 sha256——中文/超长 query 直接哈希，
   规避 Redis key 长度限制与特殊字符问题；归一化（小写+空白折叠）
   保证"你好"与"你好  "同键命中

通用概念（跨框架可迁移）：
- 旁路缓存（cache-aside）：业务代码先查缓存、miss 后查源（LLM/检索）再回填，
  缓存层不侵入业务逻辑——与 Spring @Cacheable、Django cache_page 同一模式
- 熔断器（circuit breaker）：快速失败优于慢速重试，用"冷却期"给故障组件
  恢复时间，是 Resilience4j / polly 的标准做法
"""
import asyncio
import hashlib
import json
import logging
import time
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger("app.cache")

# ── 熔断器参数 ──────────────────────────────────────────
_BREAKER_THRESHOLD = 2    # 连续失败次数阈值，达到即开闸
_BREAKER_COOLDOWN = 60.0  # 冷却期（秒），期内所有操作直接跳过

_state: dict = {
    "client": None,             # redis.asyncio.Redis 实例（懒创建）
    "consecutive_failures": 0,  # 连续失败计数
    "open_until": 0.0,          # 熔断开启截止时刻（time.monotonic）
}


def _normalize(text: str) -> str:
    """归一化文本：小写 + 空白折叠，让近似相同的输入共享缓存键"""
    return " ".join(text.split()).lower()


def make_key(*parts: Any) -> str:
    """构造缓存键：前缀:sha256(归一化后的 json 序列化)"""
    raw = json.dumps([_normalize(p) if isinstance(p, str) else p for p in parts],
                     ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"legalmind:{digest}"


def _breaker_open() -> bool:
    """熔断是否生效中（含冷却期到期后自动半开：下次操作允许重试连接）"""
    return time.monotonic() < _state["open_until"]


def _record_success() -> None:
    _state["consecutive_failures"] = 0


def _record_failure() -> None:
    _state["consecutive_failures"] += 1
    if _state["consecutive_failures"] >= _BREAKER_THRESHOLD:
        _state["open_until"] = time.monotonic() + _BREAKER_COOLDOWN
        _state["consecutive_failures"] = 0
        logger.warning("Redis 连续失败 %d 次，熔断 %ds（期间缓存直连）",
                       _BREAKER_THRESHOLD, int(_BREAKER_COOLDOWN))


def _get_client():
    """懒创建 Redis 客户端（redis-py 的 asyncio 实现，socket 超时 1s 快速失败）"""
    if _state["client"] is None:
        import redis.asyncio as aioredis
        _state["client"] = aioredis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=1.0,
            socket_timeout=1.0,
        )
    return _state["client"]


async def cache_get(key: str) -> Optional[Any]:
    """读缓存：miss/禁用/降级返回 None，绝不抛异常"""
    if not settings.CACHE_ENABLED or _breaker_open():
        return None
    try:
        client = _get_client()
        raw = await client.get(key)
        _record_success()
        return json.loads(raw) if raw is not None else None
    except Exception as e:
        _record_failure()
        logger.debug("缓存读取失败（降级直连）: %s", e)
        return None


async def cache_set(key: str, value: Any, ttl: int) -> None:
    """写缓存：禁用/降级静默跳过，写失败不影响业务"""
    if not settings.CACHE_ENABLED or _breaker_open():
        return
    try:
        client = _get_client()
        await client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl)
        _record_success()
    except Exception as e:
        _record_failure()
        logger.debug("缓存写入失败（忽略）: %s", e)


async def ping_cache() -> bool:
    """启动时探测 Redis 可用性（仅用于日志观测，不影响可用性）"""
    if not settings.CACHE_ENABLED:
        return False
    try:
        await _get_client().ping()
        _record_success()
        return True
    except Exception:
        _record_failure()
        return False


async def close_cache() -> None:
    """lifespan 关闭时释放连接池"""
    if _state["client"] is not None:
        try:
            await _state["client"].aclose()
        except Exception:
            pass
        _state["client"] = None
