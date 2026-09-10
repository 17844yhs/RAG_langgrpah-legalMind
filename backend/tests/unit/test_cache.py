"""Redis 缓存层单元测试

覆盖三块：
1. 键归一化与 JSON 往返
2. 降级三段式：禁用开关 / 操作失败不抛异常 / 熔断器开关与冷却恢复
3. 业务接入：意图识别缓存（同 query 只调一次 LLM）、检索缓存（同参数只检索一次）

缓存模块的全局熔断状态通过夹具逐测试重置；Redis 客户端用内存 stub 替换，
不依赖真实 Redis（CI 无 Redis 服务也能全绿——这正是"降级直连"设计的验证）。
"""
import time

import pytest

from app.cache import redis_cache
from app.cache.redis_cache import cache_get, cache_set, close_cache, make_key, ping_cache
from app.config import settings


class StubRedis:
    """内存版 Redis stub：可注入故障模拟连接失败"""

    def __init__(self, fail: bool = False):
        self.store: dict = {}
        self.fail = fail
        self.calls = 0

    async def get(self, key):
        self.calls += 1
        if self.fail:
            raise ConnectionError("stub: redis down")
        return self.store.get(key)

    async def set(self, key, value, ex=None):
        self.calls += 1
        if self.fail:
            raise ConnectionError("stub: redis down")
        self.store[key] = value

    async def ping(self):
        self.calls += 1
        if self.fail:
            raise ConnectionError("stub: redis down")
        return True

    async def aclose(self):
        pass


@pytest.fixture(autouse=True)
def _reset_cache_state(monkeypatch):
    """逐测试重置全局熔断状态 + 注入全新 stub，避免用例间串扰"""
    monkeypatch.setattr(redis_cache, "_state", {
        "client": StubRedis(),
        "consecutive_failures": 0,
        "open_until": 0.0,
    })
    monkeypatch.setattr(settings, "CACHE_ENABLED", True)


# ── 键设计 ──────────────────────────────────────────────

def test_make_key_normalizes_whitespace_and_case():
    """归一化：空白折叠 + 小写，让近似输入同键命中"""
    assert make_key("intent", "你好") == make_key("intent", "你好  ")
    assert make_key("intent", "ABC") == make_key("intent", "abc")


def test_make_key_distinguishes_inputs():
    """不同业务前缀/内容不得碰撞"""
    assert make_key("intent", "你好") != make_key("retrieval", "你好")
    assert make_key("intent", "你好") != make_key("intent", "你好吗")


# ── 基础存取与降级 ──────────────────────────────────────

async def test_cache_roundtrip():
    await cache_set("k", {"a": 1, "b": ["你好"]}, ttl=60)
    assert await cache_get("k") == {"a": 1, "b": ["你好"]}


async def test_cache_miss_returns_none():
    assert await cache_get("nonexistent") is None


async def test_disabled_flag_bypasses_client(monkeypatch):
    """总开关关闭：不触碰客户端，get 恒 None"""
    stub = redis_cache._state["client"]
    monkeypatch.setattr(settings, "CACHE_ENABLED", False)
    await cache_set("k", {"a": 1}, ttl=60)
    assert await cache_get("k") is None
    assert stub.calls == 0


async def test_get_failure_degrades_to_none():
    """读取失败：返回 None（业务视为 miss），绝不抛异常"""
    redis_cache._state["client"] = StubRedis(fail=True)
    assert await cache_get("k") is None


async def test_set_failure_is_silent():
    """写入失败：静默忽略，业务零感知"""
    redis_cache._state["client"] = StubRedis(fail=True)
    await cache_set("k", {"a": 1}, ttl=60)  # 不应抛异常
    assert redis_cache._state["client"].calls == 1


# ── 熔断器 ──────────────────────────────────────────────

async def test_breaker_opens_after_consecutive_failures():
    """连续失败达阈值 → 开闸，后续操作跳过客户端（不再白付连接超时）"""
    stub = StubRedis(fail=True)
    redis_cache._state["client"] = stub
    await cache_get("k1")
    await cache_get("k2")          # 第 2 次失败 → 熔断开启
    assert stub.calls == 2
    await cache_get("k3")          # 熔断期内：直接跳过
    assert stub.calls == 2         # 调用数不再增长
    assert redis_cache._breaker_open()


async def test_breaker_recovers_after_cooldown():
    """冷却期结束 → 半开状态，一次成功操作即复位熔断"""
    redis_cache._state["client"] = StubRedis(fail=True)
    await cache_get("k1")
    await cache_get("k2")                       # 触发熔断
    redis_cache._state["open_until"] = time.monotonic() - 1  # 模拟冷却结束
    healthy = StubRedis()
    redis_cache._state["client"] = healthy
    await cache_set("k", {"a": 1}, ttl=60)      # 半开探测成功
    assert not redis_cache._breaker_open()
    assert await cache_get("k") == {"a": 1}     # 恢复正常读写


async def test_ping_reports_availability():
    assert await ping_cache() is True
    redis_cache._state["client"] = StubRedis(fail=True)
    assert await ping_cache() is False


async def test_close_cache_clears_client():
    await close_cache()
    assert redis_cache._state["client"] is None


# ── 业务接入：意图识别缓存 ───────────────────────────────

class _CountingLLM:
    """伪 structured_llm：统计 ainvoke 次数，返回固定意图"""

    def __init__(self):
        self.calls = 0

    async def ainvoke(self, prompt):
        self.calls += 1
        from app.agents.intent_agent import IntentResult
        return IntentResult(intent="qa", confidence=0.95, reasoning="伪 LLM")


def _make_intent_agent(llm):
    """绕过 __init__（避免真实 get_llm 构造），注入伪 LLM"""
    from app.agents.intent_agent import IntentAgent
    agent = IntentAgent.__new__(IntentAgent)
    agent.structured_llm = llm
    return agent


async def test_intent_cache_skips_llm_on_repeat_query():
    """同问题第二次识别命中缓存，LLM 只调一次"""
    from app.agents.intent_agent import IntentAgent
    llm = _CountingLLM()
    agent = _make_intent_agent(llm)

    r1 = await agent.recognize("工伤赔偿怎么算")
    r2 = await agent.recognize("工伤赔偿怎么算")   # 归一化同键

    assert llm.calls == 1
    assert r1.intent == r2.intent == "qa"
    assert r2.confidence == 0.95


async def test_intent_cache_different_query_calls_llm():
    llm = _CountingLLM()
    agent = _make_intent_agent(llm)
    await agent.recognize("工伤赔偿怎么算")
    await agent.recognize("离婚财产怎么分")
    assert llm.calls == 2


async def test_intent_llm_failure_not_cached():
    """失败降级的默认意图绝不入缓存——一次抖动不能把错误分类固化 24h"""
    from app.agents.intent_agent import IntentAgent

    class _BoomLLM(_CountingLLM):
        async def ainvoke(self, prompt):
            raise RuntimeError("LLM down")

    agent = IntentAgent.__new__(IntentAgent)
    agent.structured_llm = _BoomLLM()
    r1 = await agent.recognize("工伤赔偿怎么算")
    assert r1.confidence == 0.55          # 降级默认值

    # LLM 恢复后：同问题必须重新走 LLM（缓存里没有降级结果）
    healthy = _CountingLLM()
    agent.structured_llm = healthy
    r2 = await agent.recognize("工伤赔偿怎么算")
    assert healthy.calls == 1
    assert r2.confidence == 0.95


# ── 业务接入：检索结果缓存 ───────────────────────────────

class _CountingRetriever:
    def __init__(self):
        self.calls = 0

    async def retrieve(self, query, top_k, filters=None):
        self.calls += 1
        return [{"id": f"doc{i}", "type": "case", "content": f"案例{i}"} for i in range(top_k)]


def _make_retrieval_agent(retriever):
    from app.agents.retrieval_agent import RetrievalAgent
    agent = RetrievalAgent.__new__(RetrievalAgent)
    agent.retriever = retriever
    agent.reranker = None   # 走 candidates[:top_k] 分支
    return agent


async def test_retrieval_cache_skips_duplicate_search():
    """同 query+top_k+doc_type 只检索一次；参数不同则分别检索"""
    retriever = _CountingRetriever()
    agent = _make_retrieval_agent(retriever)

    r1 = await agent.retrieve("工伤认定", top_k=3, doc_type="case")
    r2 = await agent.retrieve("工伤认定", top_k=3, doc_type="case")
    assert retriever.calls == 1
    assert r1 == r2

    await agent.retrieve("工伤认定", top_k=5, doc_type="case")   # top_k 不同 → miss
    assert retriever.calls == 2

    await agent.retrieve("工伤认定", top_k=3, doc_type=None)     # doc_type 不同 → miss
    assert retriever.calls == 3
