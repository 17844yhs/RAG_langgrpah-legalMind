"""法律问答 Agent — 基于检索到的案例回答法律问题"""

import logging
from typing import List, Dict, Optional, Literal
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.messages import BaseMessage,SystemMessage

from app.llm.model_client import get_llm
from app.llm.prompts import QA_SYSTEM_PROMPT, QA_USER_PROMPT, META_EXTRACT_PROMPT

logger = logging.getLogger("app.agent")


class LegalAnswerMeta(BaseModel):
    """回答元数据 — 流式正文完成后二次抽取，前端渲染为答案卡片。

    设计权衡：with_structured_output 与逐 token 流式互斥（JSON 必须完整才能
    反序列化），故正文走自由文本流式保住打字机效果，元数据在流结束后
    用一次轻量结构化调用抽取——鱼与熊掌的工程解法。
    """
    summary: str = Field(description="一句话核心结论，30字以内")
    risk_level: Literal["低", "中", "高"] = Field(description="用户的法律风险等级")
    applicable_laws: List[str] = Field(
        default_factory=list,
        description="回答中实际引用的法条，如《劳动合同法》第38条；无则空列表",
    )


class QAAgent:
    """法律问答 Agent：利用大语言模型（LLM）结合检索到的相关法律案例，生成针对用户问题的专业回答。"""
    def __init__(self):
        self.llm = get_llm()
        # 元数据抽取器：结构化输出 + 重试（瞬时失败重试一次）
        self.meta_llm = (
            self.llm
            .with_structured_output(LegalAnswerMeta, method="function_calling")
            .with_retry(stop_after_attempt=2)
        )

    async def extract_meta(self, answer_text: str) -> Optional[LegalAnswerMeta]:
        """从完整回答文本抽取元数据。失败返回 None（增强功能，不阻塞主流程）。"""
        if not answer_text or len(answer_text) < 20:
            return None
        try:
            result = await self.meta_llm.ainvoke(
                META_EXTRACT_PROMPT.format(answer=answer_text[:6000])
            )
            if result is None:  # function_calling 模式拒答返回 None 而非抛异常
                raise ValueError("structured output returned None")
            return result
        except Exception:
            logger.exception("元数据抽取失败，降级跳过（不影响回答本身）")
            return None

    def build_messages(self, cases: List[Dict], messages: List[BaseMessage]) -> List[BaseMessage]:
        """组装 LLM 输入消息：system（人设 + 案例上下文）+ 对话历史（含当前问题）。

        案例作为当轮 system 注入，绝不进入长期累积的 messages。
        """
        system_content = (
            QA_SYSTEM_PROMPT
            + "\n\n## 相关案例\n"
            + self._format_cases(cases)
        )
        return [SystemMessage(content=system_content)] + list(messages)
    
    async def answer(self,cases:List[Dict],messages:List[BaseMessage]=None) ->List[BaseMessage]:
        
        response = await self.llm.ainvoke(self.build_messages(cases,messages))
    
        sources = self._extract_sources(cases)
        
        return {"answer":response,"sources":sources}
    
    async def stream_answer(self,cases:List[Dict],messages:List[BaseMessage]=None):
        async for chunk in self.llm.astream(self.build_messages(cases,messages)):
            yield chunk
    
    def _format_cases(self,cases:List[Dict]) ->str:
        """
        将检索到的案例列表格式化为字符串，便于注入到提示模板中。

        参数:
            cases (List[Dict]): 案例字典列表，每个字典应包含 title、case_number、court、summary、laws 等字段。

        返回:
            str: 格式化后的案例文本；若无案例，则返回“暂无相关案例参考。”
        """
        if not cases:
            return "暂无相关案例参考。"
        formatted = []
        for i, case in enumerate(cases, 1):
            formatted.append(
                f"【案例{i}】\n"
                f"标题：{case.get('title', '未知')}\n"
                f"案号：{case.get('case_number', '未知')}\n"
                f"法院：{case.get('court', '未知')}\n"
                f"裁判要旨：{case.get('summary', '未知')}\n"
                f"相关法条：{case.get('laws', '未知')}\n"
            )
        return "\n".join(formatted)
    
    def _format_history(self, context: List[Dict]) -> str:
        """
        将对话历史格式化为字符串，仅保留最近5条消息。

        参数:
            context (List[Dict]): 对话历史，每条消息包含 role（"user" 或 "assistant"）和 content。

        返回:
            str: 格式化后的对话历史字符串，如：
                用户：你好
                助手：您好，请问有什么法律问题？
        """      
        if not context:
            return ""
        formatted = []
        # 仅保留最近5条对话
        for msg in context[-5:]:
            role = "用户" if msg.get("role") == "user" else "助手"
            formatted.append(f"{role}：{msg.get('content', '')}")
        return "\n".join(formatted)

    def _extract_sources(self, cases: List[Dict]) -> List[Dict]:
        """
        从案例列表中提取前3个作为回答的引用来源。

        参数:
            cases (List[Dict]): 案例列表。

        返回:
            List[Dict]: 包含 title、case_number、court、date 的来源列表（最多3个）。
        """
        sources = []
        for case in cases[:3]:  # 最多取前3个案例作为引用
            sources.append({
                "title": case.get("title"),
                "case_number": case.get("case_number"),
                "court": case.get("court"),
                "date": case.get("judgment_date"),  # 判决日期
            })
        return sources
