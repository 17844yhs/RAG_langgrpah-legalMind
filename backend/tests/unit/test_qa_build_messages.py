"""R3 空检索显式声明：rerank 阈值滤空后的 prompt 兜底（防无依据硬答）。

build_messages 是纯组装方法（不触 LLM/DB），用 __new__ 绕过 __init__
（构造需真实 LLM 客户端）——与图集成测试 stub stream_answer 分工：
那边测图流转，这里测 prompt 契约本身。
"""
from langchain_core.messages import HumanMessage

from app.agents.qa_agent import QAAgent


def _bare_agent() -> QAAgent:
    return QAAgent.__new__(QAAgent)


def test_empty_cases_inject_refusal_notice():
    """空检索 → 注入拒答声明：告知未命中 + 禁止引用编号（R3 兜底）"""
    agent = _bare_agent()
    msgs = agent.build_messages([], [HumanMessage(content="量子纠缠纠纷怎么立案")])
    system = msgs[0].content
    assert "未检索到" in system
    assert "不得引用具体法条编号" in system
    # 空检索时不得再渲染数据区标题（无资料不给数据区，防模型对空区硬编）
    assert "仅供分析的数据区" not in system


def test_nonempty_cases_keep_data_zone():
    """有检索 → 数据区照常渲染（隔离声明 + 法条原文），不受 R3 改动影响"""
    agent = _bare_agent()
    msgs = agent.build_messages(
        [{"type": "law", "title": "劳动合同法", "content": "第八十二条……"}],
        [HumanMessage(content="未签合同二倍工资")],
    )
    system = msgs[0].content
    assert "仅供分析的数据区" in system
    assert "第八十二条" in system
    assert "未检索到" not in system
