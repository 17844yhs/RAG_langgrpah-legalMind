"""pytest 全局配置

- Windows 下 psycopg 要求 Selector 事件循环（Proactor 会报错），
  必须在事件循环创建前设置策略，所以放在 conftest 顶层
- 公共夹具：假案例数据、图测试用的 stub 工厂
"""
import asyncio
import sys
from types import SimpleNamespace

import pytest

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


# ── 公共数据 ──

FAKE_CASE = {
    "case_number": "(2023)京01民终1234号",
    "court": "北京市第一中级人民法院",
    "case_type": "劳动争议",
    "summary": "用人单位拖欠工资，劳动者申请劳动仲裁获支持",
    "laws": "《劳动合同法》第三十条",
}


def make_verdict(passed: bool, score: float = 1.0, feedback: str = ""):
    """构造质量门控评审结论（ duck typing，替代 ReflectionVerdict）"""
    return SimpleNamespace(passed=passed, score=score, feedback=feedback)


def make_intent_result(intent: str = "qa", confidence: float = 0.95):
    """构造意图识别结果 stub"""
    return SimpleNamespace(intent=intent, confidence=confidence)


@pytest.fixture
def fake_cases():
    return [dict(FAKE_CASE)]
