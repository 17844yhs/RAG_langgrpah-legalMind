"""单元测试：context_manager.split_history — 视图裁剪的轮次边界与兜底逻辑

┌─────────────────────────── 测试定位（复习笔记）───────────────────────────┐
│ 级别：单元测试（测单个纯函数，不拉起图、不碰 DB/LLM）                       │
│ 方法：白盒（专挑内部分支和边界条件打：预算相等、轮次对齐、兜底路径）          │
│ 手段：零 mock——被测对象本身就是纯逻辑，给输入断言输出即可                   │
│ 选材标准：逻辑越纯、边界越多，越值得测（回归时最容易被改坏的也是这些）        │
└──────────────────────────────────────────────────────────────────────────┘

这是 Context 管理的核心纯逻辑，边界条件密集，最适合白盒单测。
"""
from langchain_core.messages import AIMessage, HumanMessage

from app.llm.context_manager import estimate_chars, format_history_text, split_history


def _round(text: str) -> list:
    """一轮对话 = 用户提问 + AI 回复"""
    return [HumanMessage(content=text), AIMessage(content=text + "-回复")]


def test_empty_messages():
    kept, dropped = split_history([])
    assert kept == []
    assert dropped == []


def test_within_budget_no_crop():
    msgs = _round("短问题")
    kept, dropped = split_history(msgs, budget=10_000)
    assert kept == msgs
    assert dropped == []


def test_crop_aligns_to_round_boundary():
    """超预算时必须从 HumanMessage 轮次边界裁，且保留最多的轮次"""
    msgs = _round("a" * 100) + _round("b" * 100) + _round("c" * 100)
    # 总 600 字，预算 450：suffix[2]=200（第 2 轮起）放得下，
    # suffix[0]/suffix[2] 之间第 1 轮起点 j=2 是最早可行的 HumanMessage 起点
    kept, dropped = split_history(msgs, budget=450)

    assert len(dropped) == 2          # 裁掉第 1 轮（2 条消息）
    assert len(kept) == 4             # 保留后两轮
    assert isinstance(kept[0], HumanMessage)  # kept 必须以轮次边界开头
    assert dropped[0].content.startswith("a")


def test_last_round_never_dropped():
    """兜底：当前问题绝不能丢——哪怕最后一轮单独超预算"""
    huge = "x" * 10_000
    msgs = [HumanMessage(content=huge), AIMessage(content=huge)]
    kept, dropped = split_history(msgs, budget=100)

    assert len(kept) == 2             # 最后一轮整轮保留
    assert kept == msgs
    assert dropped == []


def test_budget_exactly_at_total():
    """体量恰好等于预算 → 不裁（<= 语义）"""
    msgs = _round("abc")
    kept, dropped = split_history(msgs, budget=estimate_chars(msgs))
    assert kept == msgs
    assert dropped == []


def test_estimate_chars():
    msgs = [HumanMessage(content="123"), AIMessage(content="45")]
    assert estimate_chars(msgs) == 5
    assert estimate_chars([]) == 0


def test_format_history_text_order():
    """摘要在前（早期），原文在后（近期）；角色标注正确"""
    msgs = [HumanMessage(content="工资被拖欠"), AIMessage(content="建议申请仲裁")]
    text = format_history_text(msgs, summary="早期摘要")

    assert text.index("【早期对话摘要】") < text.index("【近期对话原文】")
    assert "用户: 工资被拖欠" in text
    assert "助手: 建议申请仲裁" in text


def test_format_history_text_no_summary():
    text = format_history_text([HumanMessage(content="hi")], summary=None)
    assert "【早期对话摘要】" not in text
    assert "【近期对话原文】" in text
