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
"""
from langchain_openai import ChatOpenAI
from langchain_deepseek import ChatDeepSeek
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from app.config import settings

_llm = None
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
            return ChatDeepSeek(model=settings.LLM_MODEL, api_key=settings.LLM_API_KEY,
                              base_url=settings.LLM_API_BASE,
                              extra_body={"thinking": {"type": "disabled"}},
                              **common)
        elif provider == "openai":
            return ChatOpenAI(model=settings.LLM_MODEL, openai_api_key=settings.LLM_API_KEY, **common)
        elif provider == "myopenai_ollma":
            return ChatOpenAI(model="qwen2.5:0.5b", openai_api_key=settings.LLM_API_KEY,
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
