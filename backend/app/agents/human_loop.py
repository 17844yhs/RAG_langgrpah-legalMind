"""Human-in-the-Loop 管理 — 管理所有需要人工介入的节点"""
import logging

from langgraph.types import interrupt
from langchain_core.messages import HumanMessage, AIMessage
from pydantic import BaseModel, Field

from app.llm.model_client import get_llm
from app.llm.prompts import INFO_GATHERING_PROMPT
from app.llm.context_manager import split_history, format_history_text

logger = logging.getLogger("app.agent")


# ── HITL #1：意图确认（一次性）──

async def check_intent(state):
    """意图置信度不足时，生成澄清问题并等待用户确认。

    触发条件：intent_confidence < 0.8
    用户 resume 后，将用户回答拼入 query 供下游重新识别。
    """
    confidence = state.get("intent_confidence", 1.0)
    if confidence >= 0.8:
        return {}  # 置信度足够，直接放行

    detected = state.get("intent", "qa")
    clarification = (
        f"您的问题我不太确定具体意图，当前判断为「{detected}」（置信度 {confidence:.0%}）。\n"
        f"能否补充说明一下您的需求？例如：\n"
        f"1. 咨询法律问题\n"
        f"2. 生成法律文书（起诉状、合同等）\n"
        f"3. 查找相关判例"
    )

    # interrupt() 暂停图执行，将数据发送给前端
    # resume 时，用户的回答作为返回值
    user_response = interrupt({
        "type": "confirm_intent",
        "question": clarification,
        "confidence": confidence,
        "detected_intent": detected,
    })

    # 将用户补充信息拼接到 query，后续节点会用新 query
    return {
        "user_supplement": user_response,
        "query": state["query"] + "\n" + user_response,
    }


# ── HITL #2：多轮信息收集（自循环）──

class InfoCheckResult(BaseModel):
    """LLM 信息充分性判断结果"""
    sufficient: bool = Field(description="当前信息是否足以回答用户问题")
    question: str = Field(
        default="",
        description="信息不足时的追问问题；信息充分时留空",
    )


MAX_CLARIFY_ROUNDS = 3  # 最多追问 3 轮，防止死循环


async def info_gathering(state):
    """多轮信息收集节点 — LLM 判断信息充分性，不足则追问（自循环 HITL）

    每轮流程：
    1. LLM 评估当前对话历史是否信息充分
    2. 充分 → 放行（info_sufficient=True）
    3. 不足 → 生成针对性追问 → interrupt 等待用户回答
    4. resume 后，追问 + 用户回答追加到 messages，轮次 +1
    5. 条件边检测 info_sufficient：False → 自循环回本节点；True → 路由到下游
    """
    round = state.get("clarify_round", 0)

    # 超过最大轮次，强制放行（防死循环）
    if round >= MAX_CLARIFY_ROUNDS:
        return {"info_sufficient": True}

    # LLM 判断信息充分性 + 生成追问（一次调用完成两件事）
    # with_retry：格式不合规/网络抖动等瞬时失败重试一次
    llm = (
        get_llm()
        .with_structured_output(InfoCheckResult, method="function_calling")
        .with_retry(stop_after_attempt=2)
    )

    # 构建对话历史文本：视图裁剪 + 摘要（超长对话不把全量历史喂给判断 LLM）
    # 摘要在前（早期轮次）、原文在后（近期轮次），与 qa 侧的注入顺序一致
    kept, _ = split_history(state.get("messages", []))
    history = format_history_text(kept, state.get("context_summary") or "")

    try:
        result = await llm.ainvoke(INFO_GATHERING_PROMPT.format(
            intent=state.get("intent", "qa"),
            query=state.get("query", ""),
            history=history,
        ))
        # function_calling 模式下模型拒答会返回 None 而非抛异常
        if result is None:
            raise ValueError("structured output returned None")
    except Exception:
        # 降级：充分性判断是"增强体验"而非"关键路径"，
        # 判断失败不应阻塞回答——直接放行，宁可少追问一轮
        logger.exception("信息充分性判断失败，降级放行")
        return {"info_sufficient": True}

    # 信息充分 → 放行
    if result.sufficient:
        return {"info_sufficient": True}

    # 不充分 → interrupt 追问（前端收到后渲染 InterruptCard）
    user_answer = interrupt({
        "type": "clarify_info",
        "question": result.question,
        "round": round + 1,
    })

    # resume 后，追问 + 用户回答都追加到 messages（下轮 LLM 能看到完整 Q&A 上下文）
    return {
        "messages": [
            AIMessage(content=result.question),   # 助手的追问
            HumanMessage(content=user_answer),    # 用户的回答
        ],
        "clarify_round": round + 1,
        "info_sufficient": False,
    }


# check_retrieval 已移入 retrieval_agent.py 的 evaluate_node（子图内部 HITL）
