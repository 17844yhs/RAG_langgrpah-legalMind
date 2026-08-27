"""意图识别 Agent — 基于 Structured Output 识别用户意图并输出置信度"""
import logging

from pydantic import BaseModel, Field
from typing import Literal

from app.llm.model_client import get_llm

logger = logging.getLogger("app.agent")


class IntentResult(BaseModel):
    """意图识别结构化输出"""
    intent: Literal["qa", "document", "search"] = Field(
        description="用户意图类型：qa=法律问答, document=文书生成, search=案例检索"
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
        """
        try:
            result = await self.structured_llm.ainvoke(
                f"分析用户问题并判断意图。\n用户问题：{query}"
            )
            # function_calling 模式下模型拒答会返回 None 而非抛异常
            if result is None:
                raise ValueError("structured output returned None")
            return result
        except Exception:
            logger.exception("意图识别失败，降级为低置信度 qa（将触发澄清 HITL）")
            return IntentResult(
                intent="qa",
                confidence=0.55,
                reasoning="意图识别失败，降级默认值",
            )
