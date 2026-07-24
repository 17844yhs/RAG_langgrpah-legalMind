"""意图识别 Agent — 基于 Structured Output 识别用户意图并输出置信度"""
from pydantic import BaseModel, Field
from typing import Literal

from app.llm.model_client import get_llm


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
        self.structured_llm = self.llm.with_structured_output(IntentResult, method="function_calling")

    async def recognize(self, query: str) -> IntentResult:
        """识别用户意图，返回 IntentResult（含 confidence）"""
        result = await self.structured_llm.ainvoke(
            f"分析用户问题并判断意图。\n用户问题：{query}"
        )
        return result
