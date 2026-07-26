"""
案例检索 Agent + ReAct 子图
- RetrievalAgent：底层检索执行（HybridRetriever + Reranker），供 search_cases Tool 调用
- build_retrieval_subgraph：ReAct 子图（agent + ToolNode + evaluate + finish），嵌入主图
"""
import json
from typing import TypedDict, Annotated, List, Dict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage

from app.rag.retriever import HybridRetriever
from app.rag.reranker import Reranker
from app.config import settings
from app.llm.model_client import get_llm
from app.tools.search_tool import search_cases


# 底层检索 Agent（被 search_cases Tool 内部调用）
class RetrievalAgent:
    """案例检索 Agent — 封装 HybridRetriever + Reranker"""
    def __init__(self):
        self.retriever = HybridRetriever()
        self.reranker = Reranker() if settings.RERANK_ENABLED else None

    async def retrieve(self, query: str, top_k: int = 5, filters: Dict = None) -> List[Dict]:
        """
        检索相关案例
        Args:
            query: 查询文本
            top_k: 返回数量
            filters: 过滤条件

        Returns:
            检索到的案例列表
        """
        # 初始检索（多路召回）
        candidates = await self.retriever.retrieve(
            query=query,
            top_k=top_k * 3,
            filters=filters
        )
        # 重排序
        if self.reranker and candidates:
            ranked_results = await self.reranker.rerank(
                            query=query,
                            documents=candidates,
                            top_k=top_k
                        )
            return ranked_results
        return candidates[:top_k]

    async def search_by_keywords(
        self,
        keywords: List[str],
        top_k: int = 10
    ) -> List[Dict]:
        """关键词检索"""
        query = " ".join(keywords)
        return await self.retrieve(query, top_k)

    async def search_by_article(
        self,
        article: str,
        top_k: int = 10
    ) -> List[Dict]:
        """按法条检索"""
        filters = {"laws": {"$contains": article}}
        return await self.retrieve(article, top_k, filters)


# ReAct 检索子图
# 工具列表
_TOOLS = [search_cases]

# 子图 State
class RetrievalState(TypedDict):
    """子图内部状态"""
    query: str                                        # 原始查询
    reformulated_query: str                           # 重写查询（retry 时更新）
    retrieved_cases: list                             # 最终检索结果
    tool_call_count: int                              # 工具调用次数（量化评估用）
    status: str                                       # done / retry
    messages: Annotated[list[BaseMessage], add_messages]  # ReAct 对话链


def _extract_cases_from_messages(messages: list) -> list:
    """从 ToolMessage 中提取 cases（取最近一条包含 cases 的 ToolMessage）"""
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage):
            try:
                data = json.loads(msg.content)
                if "cases" in data:
                    return data["cases"]
            except (json.JSONDecodeError, TypeError):
                continue
    return []

def _count_tool_calls(messages: list) -> int:
    """统计 messages 中的 tool_calls 总数"""
    count = 0
    for msg in messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            count += len(msg.tool_calls)
    return count


# 子图节点 
async def agent_node(state: RetrievalState) -> dict:
    """ReAct Reason 步：LLM 分析 query，决定调用 search_cases 的参数"""
    llm = get_llm().bind_tools(_TOOLS)
    query = state.get("reformulated_query") or state["query"]

    system = SystemMessage(content=(
        "你是案例检索助手。根据用户问题提取法院(court)、年份(year)、案由(category)等结构化参数，"
        "调用 search_cases 工具检索案例。\n"
        f"可用的案由类别：劳动争议、合同纠纷、婚姻家庭、知识产权、刑事、行政、交通事故、消费权益\n"
        "如果首次检索结果不足，请调整查询关键词或放宽过滤条件重新检索。"
    ))

    # 首轮只有 system + human，后续轮追加 messages 保留上下文
    existing = [m for m in state.get("messages", []) if not isinstance(m, SystemMessage)]
    invoke_messages = [system] + existing + [HumanMessage(content=query)]

    response = await llm.ainvoke(invoke_messages)
    return {
        "messages": [response],
        "tool_call_count": state.get("tool_call_count", 0) + len(response.tool_calls or []),
    }

def should_continue(state: RetrievalState) -> str:
    """LLM 返回了 tool_calls → 去执行工具；否则 → finish"""
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        return "tools"
    return "finish"

def evaluate_node(state: RetrievalState) -> dict:
    """评估检索结果：数量够不够，决定 done / retry / interrupt"""
    cases = _extract_cases_from_messages(state["messages"])
    count = len(cases)
    retry = state.get("tool_call_count", 0)
    # 结果够了
    if count >= 3:
        return {"retrieved_cases": cases, "status": "done"}

    # 还没重试够，自动再来一轮
    if retry < 3:
        return {"retrieved_cases": cases, "status": "retry"}

    # 自动重试耗尽 → 人工介入（HITL interrupt）
    user_supplement = interrupt({
        "type": "need_more_info",
        "hint": (
            f"已尝试 {retry} 轮检索，只找到 {count} 条相关案例，信息可能不够充分。\n"
            f"您可以补充以下信息帮助我更精准地检索：\n"
            f"- 具体的案由或案件类型（如劳动争议、合同纠纷）\n"
            f"- 涉及的法律法规名称\n"
            f"- 关键的案件事实描述"
        ),
        "current_count": count,
    })

    # resume 后拿到用户补充信息，标记重试
    return {
        "retrieved_cases": cases,
        "status": "retry",
        "reformulated_query": state["query"] + " " + user_supplement,
    }


def evaluate_route(state: RetrievalState) -> str:
    """evaluate 路由：done → finish，retry → agent"""
    return "finish" if state.get("status") == "done" else "agent"


async def finish_node(state: RetrievalState) -> dict:
    """整理最终结果，返回给主图"""
    cases = state.get("retrieved_cases") or _extract_cases_from_messages(state["messages"])
    return {"retrieved_cases": cases, "status": "done"}

# 编译子图
def build_retrieval_subgraph():
    """构建 ReAct 检索子图：agent → tools → evaluate → (retry | finish)"""
    graph = StateGraph(RetrievalState)

    # 节点
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(_TOOLS, handle_tool_errors=True))  # 第 3 层兜底
    graph.add_node("evaluate", evaluate_node)
    graph.add_node("finish", finish_node)

    # 边
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {
        "tools": "tools",
        "finish": "finish",
    })
    graph.add_edge("tools", "evaluate")
    graph.add_conditional_edges("evaluate", evaluate_route, {
        "agent": "agent",    # retry → 回 agent 重新调用
        "finish": "finish",  # done → 结束
    })
    graph.add_edge("finish", END)

    return graph.compile()


# 编译后的子图实例，供 workflow.py 嵌入主图
retrieval_subgraph = build_retrieval_subgraph()
