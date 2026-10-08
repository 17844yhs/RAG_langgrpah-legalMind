"""单元测试（白盒）：智能路由 10.5 — 问候快速通道

chitchat 高置信 → 跳过信息收集/检索/质量门，规则模板直接回复（全程仅 1 次 LLM）。
锁住三个关键分支：
1. 高置信 chitchat → 快速通道
2. 经 HITL 澄清后的 chitchat → 保守走完整流程（user_supplement 非空）
3. 非 chitchat 意图 → 原有路径不受影响
"""

import pytest
from langchain_core.messages import AIMessage, RemoveMessage

from app.agents.workflow import LegalMindWorkflow


@pytest.fixture()
def wf():
    return LegalMindWorkflow()


# ── 路由：_route_after_check ──

def test_chitchat_high_confidence_takes_fast_path(wf):
    state = {"intent": "chitchat", "intent_confidence": 0.95, "user_supplement": ""}
    assert wf._route_after_check(state) == "chitchat"


def test_chitchat_after_hitl_clarification_goes_full_pipeline(wf):
    # HITL #1 介入过（用户补充过说明）→ 不快速放行，保守走完整管线
    state = {"intent": "chitchat", "user_supplement": "其实我想咨询劳动纠纷"}
    assert wf._route_after_check(state) == "continue"


def test_non_chitchat_intent_unaffected(wf):
    for intent in ("qa", "document", "search"):
        assert wf._route_after_check({"intent": intent}) == "continue"


# ── 节点：_chitchat_node ──

async def test_chitchat_node_returns_template_reply(wf):
    result = await wf._chitchat_node({"query": "你好", "user_msg_id": "u-1"})
    assert result["response"] in wf._CHITCHAT_REPLIES
    # 12.x 重要性过滤：寒暄不入对话历史——仅擦除本轮用户消息，不追加问候 AI 消息
    removals = [m for m in result["messages"] if isinstance(m, RemoveMessage)]
    assert [m.id for m in removals] == ["u-1"]
    assert not any(isinstance(m, AIMessage) for m in result["messages"])


async def test_chitchat_node_without_msg_id_writes_no_history(wf):
    result = await wf._chitchat_node({"query": "你好"})
    assert result["response"] in wf._CHITCHAT_REPLIES
    assert result["messages"] == []


# ── 图结构：条件边映射存在（防节点改名后 KeyError）──

async def test_graph_compiles_with_chitchat_branch(monkeypatch):
    # 单测环境无 Postgres：checkpointer/store 均 None，只影响持久化，不影响布线校验
    from app.agents import workflow as wf_module
    monkeypatch.setattr(wf_module, "get_checkpointer", lambda: None)
    monkeypatch.setattr(wf_module, "get_store", lambda: None)
    graph = wf_module.LegalMindWorkflow().get_graph()
    node_names = set(graph.get_graph().nodes)
    assert "chitchat_reply" in node_names
    assert "info_gathering" in node_names
