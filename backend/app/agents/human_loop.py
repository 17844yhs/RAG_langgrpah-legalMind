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


# check_retrieval 已移入 retrieval_agent.py 的 evaluate_node（子图内部 HITL）
