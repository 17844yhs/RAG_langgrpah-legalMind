"""Context 窗口管理 — 对话历史的视图层裁剪

核心决策（面试可讲）：**物理裁剪 vs 视图裁剪**
- checkpoint 里的 messages 原样保留（HITL resume 依赖完整 state，物理删除
  会导致 interrupt 恢复后上下文错乱）；
- 只在构造 LLM 输入时做"视图裁剪"——超预算的最老轮次不进 prompt，
  由调用方决定是否先用摘要压缩再丢弃。

预算单位用"字符"而非 token：中文场景 1 字 ≈ 0.6 token，字符预算是
保守上界（偏多裁不偏少裁），且零依赖（不需要 tokenizer）。
"""
from langchain_core.messages import BaseMessage, HumanMessage

from app.config import settings


def estimate_chars(messages: list[BaseMessage]) -> int:
    """消息列表的体量估算（字符数）"""
    return sum(len(m.content or "") for m in messages)


def split_history(messages: list[BaseMessage], budget: int = None):
    """按预算从最新往回保留完整轮次，返回 (kept, dropped)。

    - 轮次边界 = HumanMessage（一轮 = 用户提问 + 后续 AI 回复），
      保证裁剪不会把一轮切成两半
    - 优先保留最多：找最早的可行轮次起点；整段都在预算内则不裁
    - 兜底：即使最后一轮单独超预算，也至少保留最后一轮
      （当前问题绝不能丢，丢了回答就跑题）
    """
    msgs = list(messages)
    n = len(msgs)
    if n == 0:
        return [], []
    budget = budget if budget is not None else settings.HISTORY_CHAR_BUDGET

    # 后缀字符和：suffix[i] = msgs[i:] 的体量
    suffix = [0] * (n + 1)
    for i in range(n - 1, -1, -1):
        suffix[i] = suffix[i + 1] + len(msgs[i].content or "")
    # suffix[0]这时候就是消息总长度
    # 全量都在预算内 → 不裁
    if suffix[0] <= budget:
        return msgs, []

    # 从最早轮次开始找：第一个"放得下"的 HumanMessage 起点 = 保留最多
    for j in range(1, n):
        if isinstance(msgs[j], HumanMessage) and suffix[j] <= budget:
            return msgs[j:], msgs[:j]

    # 兜底：最后一轮起点（哪怕单独超预算也要带上当前问题）
    for j in range(n - 1, -1, -1):
        if isinstance(msgs[j], HumanMessage):
            return msgs[j:], msgs[:j]
    return msgs[-1:], msgs[:-1]


def format_history_text(messages: list[BaseMessage], summary: str = None) -> str:
    """把（裁剪后的）消息列表 + 摘要拼成纯文本，供非流式 prompt 注入。

    摘要在前（代表更早的对话），原文在后（更近、更精确）。
    """
    parts = []
    if summary:
        parts.append(f"【早期对话摘要】\n{summary}")
    lines = [
        f"{'用户' if isinstance(m, HumanMessage) else '助手'}: {m.content}"
        for m in messages
    ]
    if lines:
        parts.append("【近期对话原文】\n" + "\n".join(lines))
    return "\n\n".join(parts)
