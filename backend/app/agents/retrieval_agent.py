"""
案例检索 Agent + ReAct 子图
- RetrievalAgent：底层检索执行（HybridRetriever + Reranker），供 search_cases Tool 调用
- build_retrieval_subgraph：ReAct 子图（agent + ToolNode + evaluate + finish），嵌入主图
"""
import json
import logging
from typing import TypedDict, Annotated, List, Dict

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition
from langgraph.types import interrupt
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, ToolMessage

from app.rag.retriever import HybridRetriever
from app.rag.reranker import Reranker
from app.config import settings
from app.llm.model_client import get_llm
from app.llm.prompts import RETRIEVAL_AGENT_SYSTEM_PROMPT
from app.tools.search_tool import search_cases
from app.cache.redis_cache import cache_get, cache_set, make_key

logger = logging.getLogger("app.agent")


# 底层检索 Agent（被 search_cases Tool 内部调用）
class RetrievalAgent:
    """案例检索 Agent — 封装 HybridRetriever + Reranker

    通过 get_retrieval_agent() 获取进程级单例使用。
    直接实例化会在每次请求时重新加载 cross-encoder 模型（秒级开销）
    和 BM25 索引，严禁在请求路径上 new。
    """
    def __init__(self):
        self.retriever = HybridRetriever()
        self.reranker = Reranker() if settings.RERANK_ENABLED else None

    async def retrieve(self, query: str, top_k: int = 5, filters: Dict = None, doc_type: str = None) -> List[Dict]:
        """
        检索相关案例
        Args:
            query: 查询文本
            top_k: 返回数量
            filters: 过滤条件
            doc_type: 文档类型过滤（"case"/"law"），在重排前过滤不浪费 Reranker 算力；
                      None 表示不过滤（聊天 RAG 需要法条+案例混合召回）

        Returns:
            检索到的案例列表
        """
        # cache-aside：完整链路（召回+过滤+重排）的结果整体缓存，键含全部输入——
        # CPU 重排 2-9s 是检索侧最贵的一步，知识库静态所以同查询短窗内可安全复用
        cache_key = make_key("retrieval", query, top_k, filters or {}, doc_type or "")
        cached = await cache_get(cache_key)
        if cached is not None:
            logger.info("检索缓存命中: %s（%d 条）", query[:20], len(cached))
            return cached
        # 初始检索（多路召回）。
        # doc_type 在召回层就下推（而非召回后过滤）：短查询（如"拖欠工资"）的混合
        # top-k 可能被单一类型占满（法条 chunk 字面/语义双强），案例被挤出候选池，
        # 召回后过滤得到空集——实测 '拖欠工资' 案例召回 0 条，分层下推后恢复
        recall_filters = dict(filters or {})
        if doc_type:
            recall_filters.setdefault("type", doc_type)
        candidates = await self.retriever.retrieve(
            query=query,
            top_k=top_k * 3,
            filters=recall_filters
        )
        # 后置过滤仅作兜底（召回层 filters 因存储不支持而下推失败时仍保证类型正确）
        if doc_type and candidates:
            candidates = [c for c in candidates if c.get("type") == doc_type]
        # 重排序
        if self.reranker and candidates:
            ranked_results = await self.reranker.rerank(
                            query=query,
                            documents=candidates,
                            top_k=top_k
                        )
            # 分数阈值过滤：rerank 分低于阈值视为不相关。
            # 实测（diag_retrieval.py）：强相关 0.55-0.99，噪声填充 ≤0.15，
            # 不设阈值时离谱查询也硬凑 top_k 条噪声 → LLM 拿噪声硬答（幻觉温床）。
            # 返回空列表 = 上层走"无参考"兜底，而非编造。
            if settings.RAG_SCORE_THRESHOLD > 0:
                ranked_results = [
                    c for c in ranked_results
                    if (c.get("rerank_score") or 0) >= settings.RAG_SCORE_THRESHOLD
                ]
            await cache_set(cache_key, ranked_results, settings.RETRIEVAL_CACHE_TTL)
            return ranked_results
        results = candidates[:top_k]
        await cache_set(cache_key, results, settings.RETRIEVAL_CACHE_TTL)
        return results

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


# 进程级单例：cross-encoder 模型 + BM25 索引只加载一次
_retrieval_agent: "RetrievalAgent | None" = None


def get_retrieval_agent() -> "RetrievalAgent":
    global _retrieval_agent
    if _retrieval_agent is None:
        _retrieval_agent = RetrievalAgent()
    return _retrieval_agent


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
    interrupt_count: int                               # interrupt 次数（防死循环）
    status: str                                       # done / retry
    messages: Annotated[list[BaseMessage], add_messages]  # ReAct 对话链


MAX_INTERRUPT_ROUNDS = 1  # 最多人工补充 1 次：检索不充分的危害是"引用少"而非幻觉
# （qa 提示词有无参考兜底），反复打断比少引用更伤体验——宁可放行已有结果


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

# 子图节点 
async def agent_node(state: RetrievalState) -> dict:
    """ReAct Reason 步：LLM 分析 query，决定调用 search_cases 的参数"""
    llm = get_llm().bind_tools(_TOOLS)
    query = state.get("reformulated_query") or state["query"]

    system = SystemMessage(content=RETRIEVAL_AGENT_SYSTEM_PROMPT)

    # 首轮只有 system + human；retry 轮的消息链已含历史 ToolMessage 和
    # evaluate_node 注入的反思反馈，不再重复追加 query——
    # 原话重发会诱导 LLM 用同样参数原样重试
    existing = [m for m in state.get("messages", []) if not isinstance(m, SystemMessage)]
    invoke_messages = [system] + existing
    if not existing:
        invoke_messages.append(HumanMessage(content=query))

    response = await llm.ainvoke(invoke_messages)
    return {
        "messages": [response],
        "tool_call_count": state.get("tool_call_count", 0) + len(response.tool_calls or []),
    }

def evaluate_node(state: RetrievalState) -> dict:
    """评估检索结果：数量够不够，决定 done / retry / interrupt

    重试策略：
    - 自动重试：tool_call_count < 2 时自动重试（不 interrupt）
    - HITL 介入：自动重试耗尽后 interrupt，用户补充后重试 1 次
    - 死循环守卫：interrupt 次数 >= MAX_INTERRUPT_ROUNDS → 强制 done（放行）
    """
    cases = _extract_cases_from_messages(state["messages"])
    count = len(cases)
    retry = state.get("tool_call_count", 0)
    interrupt_count = state.get("interrupt_count", 0)

    # 结果够了
    if count >= 3:
        return {"retrieved_cases": cases, "status": "done"}

    # 还没重试够，自动再来一轮
    # 注入反思反馈：把"结果被判定为不足"这个结论显式传回 LLM——
    # 它虽然看得见上轮 ToolMessage，但不知道判定标准，可能觉得 2 条就够用
    if retry < 2:
        return {
            "retrieved_cases": cases,
            "status": "retry",
            "messages": [HumanMessage(content=(
                f"系统判定：上轮检索仅返回 {count} 条相关案例，未达 3 条的可用标准，"
                "请调整策略重新检索——换一组关键词、放宽 court/year 过滤，或改用其他案由类别。"
            ))],
        }

    # interrupt 次数耗尽 → 强制放行（防死循环，兜底返回已有结果）
    if interrupt_count >= MAX_INTERRUPT_ROUNDS:
        return {"retrieved_cases": cases, "status": "done"}

    # 自动重试耗尽 → 人工介入（HITL interrupt）
    # 文案面向用户：不暴露内部轮数/条数等实现细节，只说清"没找到足够案例"并给补充方向
    user_supplement = interrupt({
        "type": "need_more_info",
        "hint": (
            "暂时没有找到足够多的相关案例。您可以补充一些案件细节帮助我更精准地检索"
            "（如：纠纷的具体经过、涉及的法律名称、想达到的目标）；"
            "也可以直接点击确认，我将基于现有信息为您解答。"
        ),
        "current_count": count,
        "interrupt_round": interrupt_count + 1,
    })

    # resume 后拿到用户补充信息：反馈 + 补充合并为一条消息注入链
    # （supplement 走 messages 进上下文，reformulated_query 仅作状态留存）
    return {
        "retrieved_cases": cases,
        "status": "retry",
        "reformulated_query": state["query"] + " " + user_supplement,
        "interrupt_count": interrupt_count + 1,
        "messages": [HumanMessage(content=(
            f"系统判定：自动检索 {retry} 轮仅找到 {count} 条相关案例，结果不足。\n"
            f"用户补充了以下信息，请结合它调整检索参数：\n{user_supplement}"
        ))],
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
    # tools_condition 返回 "tools" 或 END（"__end__"）——映射键必须与返回值精确匹配，
    # 否则 LLM 不调工具直接回答时会 KeyError: '__end__'
    graph.add_conditional_edges("agent", tools_condition, {"tools": "tools", "__end__": "finish"})
    graph.add_edge("tools", "evaluate")
    graph.add_conditional_edges("evaluate", evaluate_route)
    graph.add_edge("finish", END)

    return graph.compile()


# 编译后的子图实例，供 workflow.py 嵌入主图
retrieval_subgraph = build_retrieval_subgraph()
