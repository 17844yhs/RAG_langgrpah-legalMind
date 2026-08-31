"""Token 成本追踪 — BaseCallbackHandler 采集层

链路：TraceIdMiddleware(ContextVar) → LLM 调用(on_llm_end) → 结构化日志
                                      ↓
                      grep 日志即可归集成本；后续落库/配额只需消费这里

设计要点：
- 用 usage_metadata（langchain 标准字段）而非解析 llm_output，跨模型可移植；
  DeepSeek(ChatOpenAI 系) 双来源兜底
- ContextVar 桥接 traceId：纯 ASGI 中间件写的 scope.state 在 langchain
  回调里不可见，ContextVar 在同一 asyncio 调用链内自动传播
- 挂载点在模型构造参数（callbacks=...），实例保持 BaseChatModel，
  with_structured_output / bind_tools 的方法代理零影响
- 单价表按 元/百万 token 计：只做成本估算（可观测性），不做计费
"""
'''
TraceIdMiddleware.__call__（最外层，同一异步调用链的起点）
    ├─ trace_id_var.set(trace_id)      ← 请求级身份证号
    ├─ usage_var.set(RequestUsage())   ← 请求级 token 累计器（本次对话的"账本"）
    └─ await self.app(...)             ← 后面所有代码都在这条链里
            ↓ 层层 await 透传
       workflow.astream() → LLM ainvoke()
            ↓ 回调触发
       TokenUsageHandler.on_llm_end
           ├─ trace_id_var.get()  → 日志带上 traceId，能定位是哪次请求
           └─ usage_var.get()     → 拿到同一个 RequestUsage，add() 累加
'''
import logging
import time
# Python 3.7+ 内置，用于在异步任务中传递上下文变量（类似 threading.local 的异步版本-协程传递）。
from contextvars import ContextVar

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

logger = logging.getLogger("app.usage")

# traceId 桥接：ASGI中间件 set → flaskapi里面的langchain 回调 get
trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)


class RequestUsage:
    """请求级 token 累计器：一次请求内所有 LLM 调用（意图/澄清/问答/元数据）自动归集"""
    # __slots__ 限制实例属性，节省内存。
    __slots__ = ("input_tokens", "output_tokens", "calls")

    def __init__(self):
        self.input_tokens = 0
        self.output_tokens = 0
        self.calls = 0

    def add(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.calls += 1

    def to_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "calls": self.calls,
        }


usage_var: ContextVar[RequestUsage | None] = ContextVar("request_usage", default=None)

# 元/百万 token（官网牌价，估算用）；未收录模型 cost 显示为 "-"
MODEL_PRICING: dict[str, dict[str, float]] = {
    "deepseek-chat": {"input": 2.0, "output": 8.0},
    "deepseek-v4-flash": {"input": 1.0, "output": 4.0},
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> str:
    price = MODEL_PRICING.get(model)
    if not price:
        return "-"
    cost = (input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000
    return f"¥{cost:.4f}"


class TokenUsageHandler(BaseCallbackHandler):
    """on_llm_end 采集 token 用量 → 带 traceId 的结构化日志"""

    def __init__(self):
        # run_id -> (start_ts, model) ：配对 on_llm_start / on_llm_end 算延迟
        self._running: dict = {}

    def on_llm_start(self, serialized: dict, prompts: list, *, run_id, **kwargs) -> None:
        model = "?"
        if isinstance(serialized, dict):
            # serialized.kwargs 里通常带 model_name / model
            kw = serialized.get("kwargs", {}) or {}
            model = kw.get("model_name") or kw.get("model") or model
        self._running[run_id] = (time.perf_counter(), model)

    def on_llm_error(self, error: BaseException, *, run_id, **kwargs) -> None:
        # 主实例失败的调用也要清栈，避免内存泄漏；备实例成功会再触发 on_llm_end
        self._running.pop(run_id, None)

    def on_llm_end(self, response: LLMResult, *, run_id, **kwargs) -> None:
        start, start_model = self._running.pop(run_id, (None, "?"))
        usage = self._extract_usage(response)
        if not usage:
            return
        input_tokens, output_tokens, model = usage
        # 请求级累计（SSE 结束时随 usage 事件发给前端）
        req_usage = usage_var.get()
        if req_usage is not None:
            req_usage.add(input_tokens, output_tokens)
        latency = (time.perf_counter() - start) * 1000 if start else -1
        logger.info(
            "[%s] llm model=%s in=%d out=%d total=%d cost≈%s (%.0fms)",
            trace_id_var.get() or "-",
            model, input_tokens, output_tokens,
            input_tokens + output_tokens,
            _estimate_cost(model, input_tokens, output_tokens),
            latency,
        )

    @staticmethod
    def _extract_usage(response: LLMResult) -> tuple[int, int, str] | None:
        """返回 (input, output, model)；优先标准 usage_metadata，DeepSeek 兜底 llm_output"""
        # 模型名从响应里取（serialized 在新版 langchain 不带 kwargs.model）
        model = (response.llm_output or {}).get("model_name") or "?"
        try:
            msg = response.generations[0][0]
            gen_msg = getattr(msg, "message", msg)
            um = getattr(gen_msg, "usage_metadata", None)
            if um:
                if model == "?":
                    model = (getattr(gen_msg, "response_metadata", {}) or {}).get(
                        "model_name") or model
                return um["input_tokens"], um["output_tokens"], model
        except (IndexError, KeyError, AttributeError):
            pass
        tu = (response.llm_output or {}).get("token_usage") or {}
        if tu.get("prompt_tokens") is not None:
            return tu["prompt_tokens"], tu["completion_tokens"], model
        return None
