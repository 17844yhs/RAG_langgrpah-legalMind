"""LLM 客户端 — 双层 Fallback 容灾链

链路：主 LLM (DeepSeek) → 备 LLM (DeepSeek 独立实例)

设计要点：
- 主/备同模型双实例（不引入新模型）：主实例遭遇连接抖动/内部状态异常时
  备实例顶上
- exceptions_to_handle 必须显式配全：默认只捕少量异常，RateLimitError /
  APIConnectionError / APITimeoutError 都不在默认名单，漏配 = fallback 不生效
  （且 openai 的异常类不是内置 ConnectionError 的子类，必须显式列出）
- 第三层"规则兜底"由应用层承担而非链尾 Lambda：intent 失败降级 HITL、
  SSE error 事件等已有带上下文的降级体系；链尾 Lambda 会导致
  with_structured_output 属性代理失败（Lambda 无同名方法），不可行
- 对 bind_tools / with_structured_output 透明：所有 fallback 均为 ChatModel，
  方法代理可用
- 流式：用 astream（RunnableWithFallbacks.stream() 是同步 generator）；
  "第一个 chunk 产出前"的失败自动切换备实例，流中途失败不重试，
  走上层 SSE error 事件（避免已输出 token 重复）
- 背压控制（UPGRADE_PLAN 10.3）：_Throttled* 子类在 _agenerate/_astream 外层
  包进程级 asyncio.Semaphore，并发超出 LLM_MAX_CONCURRENCY 的调用在信号量上
  排队等待而非全部涌入 API（防限流雪崩）。选择子类方案而非外层 wrapper：
  包装类会破坏 with_structured_output/bind_tools 的方法代理（Lambda 前科），
  真 ChatModel 子类则完全透明。主备实例共享同一信号量，容灾切换后总量上限不变
"""
import asyncio

from langchain_openai import ChatOpenAI
from langchain_deepseek import ChatDeepSeek
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from app.config import settings
from app.llm.rate_limit import acquire_rate_token
from app.llm.usage_tracker import TokenUsageHandler

_llm = None
_usage_handler = TokenUsageHandler()

# ── 背压控制：进程级并发信号量（懒创建）──
_llm_semaphore: "asyncio.Semaphore | None" = None


def _get_semaphore() -> asyncio.Semaphore:
    """LLM 并发信号量。主备实例共享同一把，容灾切换不放大在途压力。"""
    global _llm_semaphore
    if _llm_semaphore is None:
        _llm_semaphore = asyncio.Semaphore(settings.LLM_MAX_CONCURRENCY)
    return _llm_semaphore


class _BackpressureMixin:
    """在真实 API 调用的进出两端包信号量的混入。

    - _agenerate：ainvoke / with_structured_output(function_calling) 的底层通道
    - _astream  ：流式回答的底层通道，流全程持有许可
                  （保护的就是对 API 的并发连接数；客户端断开时任务被 cancel，
                    async with 自动释放许可，不会泄漏）
    顺序：先令牌桶（准入速率）后信号量（并发数）——桶等待发生在信号量之外，
    等待者不占用并发许可，否则限流会人为压低并发峰值（有测试为证）。
    """

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        await acquire_rate_token()       # 令牌桶：准入控制，先于并发闸门
        async with _get_semaphore():
            return await super()._agenerate(
                messages, stop=stop, run_manager=run_manager, **kwargs
            )

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        await acquire_rate_token()       # 整段流只扣一次（启动时刻）
        async with _get_semaphore():
            async for chunk in super()._astream(
                messages, stop=stop, run_manager=run_manager, **kwargs
            ):
                yield chunk


class _ThrottledDeepSeek(_BackpressureMixin, ChatDeepSeek):
    """带并发上限的 DeepSeek 客户端"""


class _ThrottledOpenAI(_BackpressureMixin, ChatOpenAI):
    """带并发上限的 OpenAI 兼容客户端（含 ollama 分支）"""


# 非线程安全,单线程应用（FastAPI 单进程）可用;多线程无参函数用functools.lru_cache
def get_llm():
    global _llm
    if _llm is None:
        _llm = _init_llm()
    return _llm

def _init_llm():
    common = {
        "temperature": settings.LLM_TEMPERATURE,
        "max_tokens": settings.LLM_MAX_TOKENS
        }

    # 显式配全网络/限流类异常：漏配则主实例抛错直接冒泡，fallback 永不触发
    _LLM_ERRORS = (
        TimeoutError,
        ConnectionError,
        APIConnectionError,
        APITimeoutError,
        RateLimitError,
        APIStatusError,
    )

    def _make(provider: str):
        if provider == "deepseek":
            # V4 Flash 默认开启思考模式，但思考模式不支持 tool_choice，需手动关闭
            # callbacks= 构造参数挂载 TokenUsageHandler：实例保持 BaseChatModel，
            # with_structured_output / bind_tools 方法代理不受影响
            return _ThrottledDeepSeek(model=settings.LLM_MODEL, api_key=settings.LLM_API_KEY,
                              base_url=settings.LLM_API_BASE,
                              extra_body={"thinking": {"type": "disabled"}},
                              callbacks=[_usage_handler],
                              **common)
        elif provider == "openai":
            return _ThrottledOpenAI(model=settings.LLM_MODEL, openai_api_key=settings.LLM_API_KEY, **common)
        elif provider == "myopenai_ollma":
            return _ThrottledOpenAI(model="qwen2.5:0.5b", openai_api_key=settings.LLM_API_KEY,
                              openai_api_base="http://127.0.0.1:11434/v1", **common)
        else:
            raise ValueError(f'不支持这个服务商:{provider}')

    main = _make(settings.LLM_PROVIDER)
    backup = _make(settings.LLM_PROVIDER)
    return main.with_fallbacks([backup], exceptions_to_handle=_LLM_ERRORS)


class LLMClient:
    def __init__(self):
        self.llm= get_llm()

    async def generate(self,prompt:str) ->str:
        resp = await self.llm.ainvoke(prompt)
        return resp.content
        
    async def stream(self,prompt:str):
        # 必须用 astream 而不能用原来的stream：RunnableWithFallbacks.stream() 返回同步 generator，
        # 无法 async for（裸 ChatModel 能跑是 langchain 兼容行为，包装后不保证）
        async for chunk in self.llm.astream(prompt):
            yield chunk.content
