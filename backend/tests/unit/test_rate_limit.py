"""LLM 速率限流（Token Bucket）单元测试

不联网：桶行为用确定性时间注入（monkeypatch time.monotonic）与直接字段
操作验证；mixin 接线用 MRO 组合伪基类 + 计数假 acquire_rate_token。
"""
import asyncio
import time

import pytest

from app.config import settings
from app.llm import model_client as mc
from app.llm import rate_limit as rl


@pytest.fixture(autouse=True)
def _reset_bucket():
    """逐测试重置进程级单例与设置，避免串扰"""
    rl._bucket = None
    yield
    rl._bucket = None


def test_disabled_when_rpm_zero(monkeypatch):
    """rpm=0 → 无桶 → acquire 立即返回（限流关闭，行为与之前一致）"""
    monkeypatch.setattr(settings, "LLM_RATE_LIMIT_RPM", 0)
    assert rl._get_bucket() is None

    async def run():
        t0 = time.perf_counter()
        await rl.acquire_rate_token()
        return time.perf_counter() - t0

    assert asyncio.run(run()) < 0.1


def test_capacity_is_one_second_of_rate():
    b = rl.AsyncTokenBucket(300)
    assert b.rate == pytest.approx(5.0)
    assert b.capacity == 5
    assert b.tokens == 5.0   # 满桶起步


def test_burst_drain_immediate():
    """满桶容量内的请求全部即时通过（突发容忍）"""
    b = rl.AsyncTokenBucket(300)   # capacity 5

    async def run():
        t0 = time.perf_counter()
        for _ in range(5):
            await b.acquire()
        return time.perf_counter() - t0

    assert asyncio.run(run()) < 0.5


def test_empty_bucket_waits_for_refill():
    """桶空后 acquire 等待补充：rate=20/s → 约 50ms"""
    b = rl.AsyncTokenBucket(1200)   # 20/s，容量 20
    b.tokens = 0.0
    b.updated = time.monotonic()

    async def run():
        t0 = time.perf_counter()
        await b.acquire()
        return time.perf_counter() - t0

    elapsed = asyncio.run(run())
    assert 0.03 <= elapsed < 5.0   # 下界证明真的等待了，上界防挂死


def test_lazy_refill_math_deterministic(monkeypatch):
    """确定性 refill 数学：2 秒后时间推进 → 补 2 个令牌（受容量截断）"""
    b = rl.AsyncTokenBucket(60)    # rate 1.0/s，容量 1
    t0 = time.monotonic()
    b.tokens = 0.0
    b.updated = t0
    # 时间直接推进到 t0+2.0：应补满容量 1，acquire 零等待通过
    monkeypatch.setattr(rl.time, "monotonic", lambda: t0 + 2.0)

    async def run():
        t = time.perf_counter()
        await b.acquire()
        return time.perf_counter() - t

    assert asyncio.run(run()) < 0.1
    assert b.tokens == pytest.approx(0.0)   # 取走后归零


def test_refill_capped_at_capacity():
    """长时间流逝不能无限囤积令牌（截断在容量）"""
    b = rl.AsyncTokenBucket(60)
    b.tokens = 0.0
    b.updated = time.monotonic() - 100.0   # 名义上可补 100 个

    async def run():
        await asyncio.wait_for(b.acquire(1), timeout=1.0)  # 立即可取 1 个

    asyncio.run(run())
    assert b.tokens == pytest.approx(0.0)
    # 再取第 2 个必须等待（容量只有 1）——用超时证明不会瞬间通过
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(asyncio.wait_for(b.acquire(1), timeout=0.2))


def test_bucket_singleton_shared():
    """进程级单例：两次获取同一实例（主备 LLM 共享的前提）"""
    monkey_rpm = 300
    import app.config as cfg
    original = cfg.settings.LLM_RATE_LIMIT_RPM
    cfg.settings.LLM_RATE_LIMIT_RPM = monkey_rpm
    try:
        assert rl._get_bucket() is rl._get_bucket()
    finally:
        cfg.settings.LLM_RATE_LIMIT_RPM = original


# ── mixin 接线：_agenerate / _astream 均在调用前扣令牌 ──────────────

class _FakeBase:
    """伪真实 ChatModel：记录底层调用次数"""

    def __init__(self):
        self.gen_calls = 0

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        self.gen_calls += 1
        return "ok"

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        self.gen_calls += 1
        for i in range(5):
            yield f"c{i}"


def _make_fake():
    class Fake(mc._BackpressureMixin, _FakeBase):
        pass

    return Fake()


@pytest.fixture
def token_counter(monkeypatch):
    calls = {"n": 0}

    async def fake_acquire():
        calls["n"] += 1

    monkeypatch.setattr(mc, "acquire_rate_token", fake_acquire)
    return calls


async def test_generate_debits_one_token(token_counter):
    fake = _make_fake()
    result = await fake._agenerate([])
    assert result == "ok"
    assert fake.gen_calls == 1
    assert token_counter["n"] == 1


async def test_stream_debits_once_for_many_chunks(token_counter):
    """整段流只扣 1 个令牌（扣在启动时刻，不随 chunk 重复扣）"""
    fake = _make_fake()
    chunks = [c async for c in fake._astream([])]
    assert len(chunks) == 5
    assert fake.gen_calls == 1
    assert token_counter["n"] == 1
