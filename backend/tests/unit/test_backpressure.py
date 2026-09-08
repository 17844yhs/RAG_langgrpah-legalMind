"""单元测试（白盒）：背压控制（UPGRADE_PLAN 10.3）

进程级 asyncio.Semaphore 限制并发 LLM 调用，超出上限的调用排队等待。
锁住三件事：
1. 并发上限不被突破（_agenerate / _astream 两条通道）
2. 排队不丢请求（所有调用最终完成，结果无损）
3. 主备实例共享同一把信号量 + 工厂确实产出限流子类
"""

import asyncio

import pytest

from app.config import settings
from app.llm import model_client as mc
from app.llm.model_client import (
    _BackpressureMixin,
    _get_semaphore,
    get_llm,
)


# ── 测试替身：只观测并发度，不发网络请求 ──

class _Counter:
    """独立计数器对象（不用类属性——子类 += 会遮蔽父类属性，断言会读错对象）"""

    def __init__(self):
        self.active = 0
        self.peak = 0

    def enter(self):
        self.active += 1
        self.peak = max(self.peak, self.active)

    def exit_(self):
        self.active -= 1


class _RecordingBase:
    def __init__(self):
        self.counter = _Counter()

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        self.counter.enter()
        await asyncio.sleep(0.03)
        self.counter.exit_()
        return "ok"

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        self.counter.enter()
        await asyncio.sleep(0.03)
        self.counter.exit_()
        yield "chunk"


class _FakeThrottled(_BackpressureMixin, _RecordingBase):
    pass


async def test_agenerate_never_exceeds_limit(monkeypatch):
    """8 个并发调用、上限 2 → 峰值并发恰好 2，且全部完成不丢请求"""
    # monkeypatch 而非直接赋值：缓存单例测后自动还原，不污染其他用例
    monkeypatch.setattr(mc, "_llm_semaphore", asyncio.Semaphore(2))
    model = _FakeThrottled()
    results = await asyncio.gather(*[
        model._agenerate([{"role": "user", "content": "x"}]) for _ in range(8)
    ])
    assert results == ["ok"] * 8
    assert model.counter.peak == 2
    assert model.counter.active == 0  # 全部释放，无许可泄漏


async def test_astream_holds_permit_for_stream_duration(monkeypatch):
    """流式通道同样受限：峰值并发不超过上限，chunk 无损"""
    monkeypatch.setattr(mc, "_llm_semaphore", asyncio.Semaphore(2))
    model = _FakeThrottled()

    async def _consume():
        chunks = [c async for c in model._astream([{"role": "user", "content": "x"}])]
        assert chunks == ["chunk"]

    await asyncio.gather(*[_consume() for _ in range(8)])
    assert model.counter.peak == 2


async def test_semaphore_created_from_settings():
    """懒创建：首次调用按 LLM_MAX_CONCURRENCY 初始化"""
    assert _get_semaphore()._value == settings.LLM_MAX_CONCURRENCY
    # 第二次调用复用同一实例（主备共享的前提）
    assert _get_semaphore() is _get_semaphore()


async def test_factory_produces_throttled_clients(monkeypatch):
    """get_llm() 主备实例都必须是限流子类（改了工厂忘换类会静默失去保护）"""
    monkeypatch.setattr(mc, "_llm", None)
    monkeypatch.setattr(settings, "LLM_PROVIDER", "deepseek")
    monkeypatch.setattr(settings, "LLM_API_KEY", "test-key")
    llm = get_llm()
    assert isinstance(llm.runnable, mc._ThrottledDeepSeek)
    for fb in llm.fallbacks:
        assert isinstance(fb, mc._ThrottledDeepSeek)
