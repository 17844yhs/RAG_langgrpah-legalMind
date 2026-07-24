"""Human-in-the-Loop 管理 — 管理所有需要人工介入的节点"""
from langgraph.types import interrupt


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


async def check_retrieval(state):
    """检索结果不足时，建议用户补充信息。

    触发条件：retrieved_cases 数量 < 3
    用户 resume 后，将补充信息拼入 query，由下游检索节点重新检索。
    """
    cases = state.get("retrieved_cases", [])
    if len(cases) >= 3:
        return {}  # 结果充足，直接放行

    hint = (
        f"目前只找到 {len(cases)} 条相关案例，信息可能不够充分。\n"
        f"您可以补充以下信息帮助我更精准地检索：\n"
        f"- 具体的案由或案件类型（如劳动争议、合同纠纷）\n"
        f"- 涉及的法律法规名称\n"
        f"- 关键的案件事实描述"
    )

    user_supplement = interrupt({
        "type": "need_more_info",
        "hint": hint,
        "current_count": len(cases),
    })

    return {
        "user_supplement": user_supplement,
        "query": state["query"] + " " + user_supplement,
    }
