"""意图识别 Agent — 基于 Structured Output 识别用户意图并输出置信度"""
import logging

from pydantic import BaseModel, Field
from typing import Literal

from app.llm.model_client import get_llm
from app.cache.redis_cache import cache_get, cache_set, make_key
from app.config import settings

logger = logging.getLogger("app.agent")


class IntentResult(BaseModel):
    """意图识别结构化输出"""
    intent: Literal["qa", "document", "search", "chitchat"] = Field(
        description=(
            "用户意图类型：qa=法律问答, document=文书生成, search=案例检索, "
            "chitchat=问候/寒暄/无实质法律内容的闲聊（如'你好''谢谢''你是谁'）"
        )
    )
    confidence: float = Field(
        description="识别置信度，0-1之间。如果对用户意图不确定，请给出较低分数",
        ge=0,
        le=1,
    )
    reasoning: str = Field(
        description="判断理由，一句话概括",
        default="",
    )


class IntentAgent:
    """意图识别 Agent"""
    def __init__(self):
        self.llm = get_llm()
        # DeepSeek 不支持 json_schema response_format，改用 function_calling 模式
        # with_retry：结构化输出常见的瞬时失败（网络抖动/格式不合规）重试一次即可恢复
        self.structured_llm = (
            self.llm
            .with_structured_output(IntentResult, method="function_calling")
            .with_retry(stop_after_attempt=2)
        )

    async def recognize(self, query: str) -> IntentResult:
        """识别用户意图，返回 IntentResult（含 confidence）。

        降级策略：意图识别是"非关键路径"——失败不应阻塞主流程。
        返回低置信度默认值 qa（0.55 < 0.8），会自动触发 HITL #1 澄清，
        让用户口头确认意图：结构化输出失败被"人机协作"优雅兜住。

        缓存策略：cache-aside 旁路缓存——同问题命中 Redis 直接返回（省 1 次
        LLM 调用）；只缓存 LLM 成功结果，失败降级的默认值是瞬态的，绝不入缓存
        （否则一次网络抖动会把错误分类固化 24h）。
        """
        cache_key = make_key("intent", query)
        cached = await cache_get(cache_key)
        if cached is not None:
            logger.info("意图缓存命中: %s", cached.get("intent"))
            return IntentResult(**cached)
        try:
            result = await self.structured_llm.ainvoke(
                f"分析用户问题并判断意图。\n"
                f"注意：问候、寒暄、感谢、无实质法律内容的闲聊应归类为 chitchat。\n"
                f"用户问题：{query}"
            )
            # function_calling 模式下模型拒答会返回 None 而非抛异常
            if result is None:
                raise ValueError("structured output returned None")
            await cache_set(cache_key, result.model_dump(), settings.INTENT_CACHE_TTL)
            return result
        except Exception:
            logger.exception("意图识别失败，降级为低置信度 qa（将触发澄清 HITL）")
            return IntentResult(
                intent="qa",
                confidence=0.55,
                reasoning="意图识别失败，降级默认值",
            )
