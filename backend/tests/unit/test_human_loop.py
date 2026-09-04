"""单元测试（白盒）：info_gathering 真函数的边界分支 — 手测发现的空问题 bug 回归

背景：手测发现模型偶发返回 sufficient=False 且 question=""（function_calling
参数缺失落到默认值），代码直接把空问题 interrupt 给前端，用户看到空白澄清卡片。
修复：空问题降级放行。本文件锁住该守卫 + 正常放行路径。
（不测 insufficient+有问题的路径——interrupt() 需要图运行时，属图逻辑层职责）
"""

from langchain_core.messages import HumanMessage

from app.agents import human_loop


class _StructuredEmptyQuestion:
    """模拟 function_calling 只返回 sufficient=False、缺 question 参数"""

    async def ainvoke(self, prompt):
        return human_loop.InfoCheckResult(sufficient=False, question="")


class _StructuredSufficient:
    async def ainvoke(self, prompt):
        return human_loop.InfoCheckResult(sufficient=True, question="")


class _Retry:
    def __init__(self, result):
        self._result = result

    async def ainvoke(self, prompt):
        return self._result


class _LLM:
    """结构化输出 + retry 链的最小替身"""

    def __init__(self, result):
        self._result = result

    def with_structured_output(self, schema, method=None):
        return self

    def with_retry(self, stop_after_attempt=None):
        return _Retry(self._result)


def _state():
    return {
        "intent": "qa",
        "query": "被违法辞退怎么办",
        "messages": [HumanMessage(content="被违法辞退怎么办")],
        "clarify_round": 0,
    }


async def test_empty_question_degrades_to_pass(monkeypatch):
    """sufficient=False + question="" → 守卫降级放行，绝不 interrupt 空问题"""
    monkeypatch.setattr(
        human_loop, "get_llm", lambda: _LLM(
            human_loop.InfoCheckResult(sufficient=False, question="")
        )
    )
    result = await human_loop.info_gathering(_state())
    assert result == {"info_sufficient": True}


async def test_sufficient_passes(monkeypatch):
    """sufficient=True → 正常放行"""
    monkeypatch.setattr(
        human_loop, "get_llm", lambda: _LLM(
            human_loop.InfoCheckResult(sufficient=True, question="")
        )
    )
    result = await human_loop.info_gathering(_state())
    assert result == {"info_sufficient": True}
