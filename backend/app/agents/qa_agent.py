"""法律问答 Agent — 基于检索到的案例回答法律问题"""

from langchain_core.messages.base import BaseMessage
import logging
from typing import List, Dict, Optional, Literal
from pydantic import BaseModel, Field
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage

from app.config import settings
from app.llm.model_client import get_llm
from app.llm.prompts import QA_SYSTEM_PROMPT, QA_USER_PROMPT, META_EXTRACT_PROMPT, HISTORY_SUMMARIZE_PROMPT, REFLECTION_PROMPT

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


class ReflectionVerdict(BaseModel):
    """Self-Reflection 质量门控的评审结论。

    忠实性（有无编造法条/事实）一票否决；针对性/可操作性轻微不足可放行但记录反馈。
    """
    passed: bool = Field(description="回答是否达到可交付标准")
    score: float = Field(description="综合质量分（0-1），忠实性权重最高")
    feedback: str = Field(
        default="",
        description="不通过时的具体修正反馈（哪条法条/事实有问题、怎么改）；通过时可为空",
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
        # 质量门控评审器：结构化输出 + 重试（评审失败=门控失效，放行为降级路径）
        self.reflect_llm = (
            self.llm
            .with_structured_output(ReflectionVerdict, method="function_calling")
            .with_retry(stop_after_attempt=2)
        )
        # ── LCEL 统一管道：一切皆 Runnable，自动获得 ainvoke/astream/batch 能力，
        #    每个中间步骤（消息组装/提示模板）自动进 LangSmith trace ──
        # QA 主链：消息组装 → LLM（输出 AIMessageChunk，保留打字机流式语义）
        # [旧写法] answer/stream_answer 内手动：self.llm.ainvoke/astream(self.build_messages(cases, messages, summary))
        self.qa_chain = (
            RunnableLambda(
                lambda x: self.build_messages(
                    x["cases"], x["messages"], x.get("summary"), x.get("reflection_feedback")
                )
            )
            | self.llm
        )
        # 历史摘要链：PromptTemplate → LLM → 字符串解析
        # [旧写法] summarize_history 内手动：resp = await self.llm.ainvoke(HISTORY_SUMMARIZE_PROMPT.format(prev_summary=..., history=..., max_chars=...)); new_summary = (resp.content or "").strip()
        self.summarize_chain = (
            PromptTemplate.from_template(HISTORY_SUMMARIZE_PROMPT)
            | self.llm
            | StrOutputParser()
        )
        # 元数据抽取链：文本预处理 → 结构化 LLM（重试已内置 meta_llm）
        # [旧写法] extract_meta 内手动：result = await self.meta_llm.ainvoke(META_EXTRACT_PROMPT.format(answer=answer_text[:6000]))
        self.meta_chain = (
            RunnableLambda(lambda text: META_EXTRACT_PROMPT.format(answer=text[:6000]))
            | self.meta_llm
        )

    async def extract_meta(self, answer_text: str) -> Optional[LegalAnswerMeta]:
        """从完整回答文本抽取元数据。失败返回 None（增强功能，不阻塞主流程）。"""
        if not answer_text or len(answer_text) < 20:
            return None
        try:
            # [旧写法] result = await self.meta_llm.ainvoke(META_EXTRACT_PROMPT.format(answer=answer_text[:6000]))
            result = await self.meta_chain.ainvoke(answer_text)
            if result is None:  # function_calling 模式拒答返回 None 而非抛异常
                raise ValueError("structured output returned None")
            return result
        except Exception:
            logger.exception("元数据抽取失败，降级跳过（不影响回答本身）")
            return None

    def build_messages(self, cases: List[Dict], messages: List[BaseMessage],
                       summary: str = None, reflection_feedback: str = None) -> List[BaseMessage]:
        """组装 LLM 输入消息：system（人设 + 案例上下文）+ [历史摘要] + [质量修正反馈] + 对话历史视图。

        - 案例作为当轮 system 注入，绝不进入长期累积的 messages
        - messages 应是裁剪后的视图（context_manager.split_history 的 kept），
          checkpoint 里的全量历史不受影响
        - summary：被裁掉的最老轮次的压缩摘要，注入在 system 之后、原文之前
        - reflection_feedback：质量门控不通过时的修正反馈（重试轮注入，引导针对性修改）
        """
        system_content = (
            QA_SYSTEM_PROMPT
            + "\n\n## 相关案例\n"
            + self._format_cases(cases)
        )
        msgs: List[BaseMessage] = [SystemMessage(content=system_content)]
        if summary:
            msgs.append(SystemMessage(content=f"## 早期对话摘要（由系统自动压缩）\n{summary}"))
        if reflection_feedback:
            msgs.append(SystemMessage(
                content=f"## 质量自检反馈（上一版回答未通过审核，本次必须修正）\n{reflection_feedback}"
            ))
        return msgs + list[BaseMessage](messages)

    async def reflect_answer(self, answer: str, cases: List[Dict], query: str) -> ReflectionVerdict:
        """质量门控评审：LLM 按清单（忠实性/针对性/可操作性）给回答打分。

        评审失败降级为放行（门控是增强路径，失效时不阻塞主流程）。
        """
        try:
            verdict = await self.reflect_llm.ainvoke(REFLECTION_PROMPT.format(
                query=query,
                cases=self._format_cases(cases),
                answer=answer[:6000],
            ))
            if verdict is None:  # function_calling 模式拒答返回 None 而非抛异常
                raise ValueError("structured output returned None")
            # 分数线兜底：LLM 说 passed 但分低于阈值 → 仍不通过（防评审宽松漂移）
            if verdict.passed and verdict.score < settings.REFLECTION_SCORE_THRESHOLD:
                verdict.passed = False
                verdict.feedback = verdict.feedback or "综合质量分低于阈值，请补充关键依据后重新回答"
            return verdict
        except Exception:
            logger.exception("质量自检评审失败，降级为放行")
            return ReflectionVerdict(passed=True, score=1.0, feedback="")

    async def summarize_history(self, prev_summary: str, dropped: List[BaseMessage]) -> str:
        """把落入裁剪区的历史轮次压缩成结构化事实摘要，并与已有摘要合并。

        增强功能：失败降级返回旧摘要（此时仅有裁剪、无压缩，
        被裁内容丢失但主流程不阻塞）。
        """
        if not dropped:
            return prev_summary or ""
        history_text = "\n".join(
            f"{'用户' if isinstance(m, HumanMessage) else '助手'}: {m.content}"
            for m in dropped
        )
        try:
            # [旧写法] resp = await self.llm.ainvoke(HISTORY_SUMMARIZE_PROMPT.format(prev_summary=..., history=..., max_chars=...))
            #          new_summary = (resp.content or "").strip()
            new_summary = (
                await self.summarize_chain.ainvoke({
                    "prev_summary": prev_summary or "无",
                    "history": history_text,
                    "max_chars": settings.SUMMARY_MAX_CHARS,
                })
            ).strip()
            return new_summary or prev_summary or ""
        except Exception:
            logger.exception("历史摘要压缩失败，降级为仅裁剪")
            return prev_summary or ""

    async def answer(self,cases:List[Dict],messages:List[BaseMessage]=None,summary:str=None,reflection_feedback:str=None) ->List[BaseMessage]:

        # [旧写法] response = await self.llm.ainvoke(self.build_messages(cases, messages, summary))
        response = await self.qa_chain.ainvoke(
            {"cases": cases, "messages": messages or [], "summary": summary,
             "reflection_feedback": reflection_feedback}
        )

        sources = self._extract_sources(cases)

        return {"answer":response,"sources":sources}

    async def stream_answer(self,cases:List[Dict],messages:List[BaseMessage]=None,summary:str=None,reflection_feedback:str=None):
        # [旧写法] async for chunk in self.llm.astream(self.build_messages(cases, messages, summary)):
        async for chunk in self.qa_chain.astream(
            {"cases": cases, "messages": messages or [], "summary": summary,
             "reflection_feedback": reflection_feedback}
        ):
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
