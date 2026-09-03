"""单元测试：Token 用量追踪 — RequestUsage 聚合 + TokenUsageHandler 采集

测试定位：单元级白盒。这里被测的是"采集层"——它处在全链路
（回调→ContextVar→SSE→JSONB→UI）的最源头，聚合错了会污染所有下游数据，
所以双来源提取、累加、清栈这类边界必须有测试守住。
构造 LLMResult 时不发任何网络请求——只是组装 langchain 的输出对象喂给回调。
"""
from types import SimpleNamespace

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from app.llm.usage_tracker import (
    RequestUsage,
    TokenUsageHandler,
    _estimate_cost,
    trace_id_var,
    usage_var,
)


def _result(usage_metadata: dict | None = None, model_name: str | None = None,
            token_usage: dict | None = None) -> LLMResult:
    """构造 on_llm_end 需要的 LLMResult（双来源可切换）"""
    kwargs = {}
    if usage_metadata:
        kwargs["usage_metadata"] = usage_metadata
    if model_name:
        kwargs["response_metadata"] = {"model_name": model_name}
    gen = ChatGeneration(message=AIMessage(content="", **kwargs))
    llm_output = {}
    if model_name:
        llm_output["model_name"] = model_name
    if token_usage:
        llm_output["token_usage"] = token_usage
    # 回调层拿到的是 LLMResult：generations 是列表的列表，generations[0][0] 取第一条生成
    return LLMResult(generations=[[gen]], llm_output=llm_output or None)


# ── RequestUsage 聚合 ──

def test_usage_add_accumulates():
    usage = RequestUsage()
    usage.add(100, 50)
    usage.add(30, 20)
    d = usage.to_dict()
    assert d["input_tokens"] == 130
    assert d["output_tokens"] == 70
    assert d["total_tokens"] == 200
    assert d["calls"] == 2      # 多次 LLM 调用归集成一条 usage


def test_usage_empty():
    d = RequestUsage().to_dict()
    assert d == {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "calls": 0}


# ── _extract_usage：双来源 ──

def test_extract_from_usage_metadata():
    """优先 langchain 标准 usage_metadata"""
    r = _result(usage_metadata={"input_tokens": 10, "output_tokens": 5, "total_tokens": 15},
                model_name="deepseek-v4-flash")
    assert TokenUsageHandler._extract_usage(r) == (10, 5, "deepseek-v4-flash")


def test_extract_fallback_to_token_usage():
    """标准字段缺失时兜底 DeepSeek 的 llm_output.token_usage"""
    r = _result(token_usage={"prompt_tokens": 7, "completion_tokens": 3},
                model_name="deepseek-chat")
    assert TokenUsageHandler._extract_usage(r) == (7, 3, "deepseek-chat")


def test_extract_returns_none_when_missing():
    r = _result()
    assert TokenUsageHandler._extract_usage(r) is None


# ── on_llm_end / on_llm_error 生命周期 ──

async def test_on_llm_end_accumulates_into_request_usage():
    usage = RequestUsage()
    usage_var.set(usage)
    trace_id_var.set("trace-xyz")
    try:
        handler = TokenUsageHandler()
        handler.on_llm_start({}, prompts=["p"], run_id=1)
        handler.on_llm_end(
            _result(usage_metadata={"input_tokens": 8, "output_tokens": 2, "total_tokens": 10}),
            run_id=1,
        )
        assert usage.calls == 1
        assert usage.input_tokens == 8
    finally:
        usage_var.set(None)
        trace_id_var.set(None)


async def test_on_llm_error_cleans_running_stack():
    """失败调用必须清栈，否则 _running 字典内存泄漏"""
    handler = TokenUsageHandler()
    handler.on_llm_start({}, prompts=["p"], run_id=42)
    handler.on_llm_error(RuntimeError("boom"), run_id=42)
    assert handler._running == {}


# ── 成本估算 ──

def test_estimate_cost_known_model():
    # deepseek-chat: 输入 2 元/百万 → 100 万输入 = ¥2.0000
    assert _estimate_cost("deepseek-chat", 1_000_000, 0) == "¥2.0000"


def test_estimate_cost_unknown_model():
    assert _estimate_cost("gpt-99", 100, 100) == "-"
