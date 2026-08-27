"""LangGraph 工作流编排 — 定义 Agent 之间的协作流程（含 Human-in-the-Loop）"""
import json
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.types import Command
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph.message import add_messages

from app.agents.intent_agent import IntentAgent
from app.agents.qa_agent import QAAgent
from app.agents.document_agent import DocumentAgent
from app.agents.retrieval_agent import retrieval_subgraph
from app.agents.human_loop import check_intent, info_gathering
from app.llm.checkpoint import get_checkpointer


class AgentState(TypedDict):
    """Agent 状态定义"""
    query: str                    # 用户问题（可能被 HITL 补充后更新）
    intent: str                   # 识别的意图
    intent_confidence: float      # 意图置信度（0-1）
    user_supplement: str          # 用户补充信息（HITL resume 后）
    clarify_round: int            # 信息收集轮次（自循环节点用）
    info_sufficient: bool          # 信息是否充分（True→放行，False→自循环追问）
    context: list                 # 上下文信息
    retrieved_cases: list         # 检索到的案例
    document_type: str            # 文书类型
    document_params: dict         # 文书参数
    response: str                 # 最终响应
    sources: list                 # 来源引用
    answer_meta: dict             # 回答元数据（summary/risk_level/applicable_laws）
    messages: Annotated[list[BaseMessage], add_messages]  # 对话历史

class LegalMindWorkflow:
    """法律咨询 Agent 工作流"""

    def __init__(self):
        self.intent_agent = IntentAgent()
        self.qa_agent = QAAgent()
        self.document_agent = DocumentAgent()
        self._graph = None

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(AgentState)

        #  添加节点 
        workflow.add_node("intent_recognition", self._intent_node)
        workflow.add_node("check_intent", check_intent)          # HITL #1：意图确认（一次性）
        workflow.add_node("info_gathering", info_gathering)     # HITL #2：多轮信息收集（自循环）
        workflow.add_node("retrieval_agent", retrieval_subgraph)  # ReAct 检索子图（内含 HITL #3）
        workflow.add_node("qa_generation", self._qa_node)
        workflow.add_node("document_generation", self._document_node)
        workflow.add_node("final_output", self._output_node)

        # 添加图结构 
        # intent_recognition → check_intent → info_gathering（自循环）→ 路由
        workflow.set_entry_point("intent_recognition")
        workflow.add_edge("intent_recognition", "check_intent")
        workflow.add_edge("check_intent", "info_gathering")

        # info_gathering 自循环：info_sufficient=False → 回自己；True → 按意图路由
        workflow.add_conditional_edges("info_gathering", self._route_after_info, {
            "qa": "retrieval_agent",
            "search": "retrieval_agent",
            "document": "document_generation",
            "loop": "info_gathering",   # 自循环：信息不足时回到自己
        })

        # retrieval_agent（ReAct 子图）→ (条件路由)
        workflow.add_conditional_edges("retrieval_agent", self._route_after_retrieval, {
            "qa": "qa_generation",
            "search": "final_output",
        })

        workflow.add_edge("qa_generation", "final_output")
        workflow.add_edge("document_generation", "final_output")
        workflow.add_edge("final_output", END)

        return workflow.compile(checkpointer=get_checkpointer())

    #  节点函数 
    async def _intent_node(self, state: AgentState) -> dict:
        """意图识别：返回 intent + confidence"""
        result = await self.intent_agent.recognize(state.get("query"))
        return {
            "intent": result.intent,
            "intent_confidence": result.confidence,
        }

    async def _qa_node(self, state: AgentState) -> dict:
        cases = state["retrieved_cases"]
        messages = state["messages"]

        full_text = ""
        async for chunk in self.qa_agent.stream_answer(cases, messages):
            full_text += chunk.content or ""

        # 流式正文完成后抽取元数据（结论/风险等级/法条）。
        # 此时 token 已流给前端，抽取的 1-2s 用户无感知；
        # 失败返回 None 不阻塞——元数据是增强，不是关键路径
        meta = await self.qa_agent.extract_meta(full_text)

        return {
            "response": full_text,
            "messages": [AIMessage(content=full_text)],
            "sources": self.qa_agent._extract_sources(cases),
            "answer_meta": meta.model_dump() if meta else {},
        }

    async def _document_node(self, state: AgentState) -> dict:
        response = await self.document_agent.generate(
            document_type=state.get("document_type", "起诉状"),
            params=state.get("document_params", {}),
            query=state["query"],
        )
        content = response["content"]
        return {
            "response": content,
            "sources": response.get("references", []),
            "messages": [AIMessage(content=content)],
        }

    async def _output_node(self, state: AgentState) -> dict:
        if state.get("intent") == "search" and not state.get("response"):
            cases = state.get("retrieved_cases", [])
            # 每层缩进 2 空格，输出带换行和缩进的美化格式
            text = json.dumps(cases, ensure_ascii=False, indent=2)
            return {
                "messages": [AIMessage(content=text)],
                "response": text,
                "sources": self.qa_agent._extract_sources(cases),
            }
        return {}

    #  路由函数 
    def _route_after_info(self, state: AgentState) -> str:
        """info_gathering 自循环路由：信息不足→回自己，充分→按意图路由"""
        if not state.get("info_sufficient"):
            return "loop"  # 自循环
        # 信息充分，按意图路由
        intent = state["intent"]
        if intent == "document":
            return "document"
        elif intent == "search":
            return "search"
        return "qa"

    def _route_after_retrieval(self, state: AgentState) -> str:
        if state["intent"] == "search":
            return "search"
        else:
            return "qa"

    #  图管理 
    def get_graph(self):
        """懒加载编译图。首次调用时编译并缓存。"""
        if self._graph is None:
            self._graph = self._build_graph()
        return self._graph

    #  执行入口 
    async def run(self, query: str, thread_id: str) -> dict:
        config = {"configurable": {"thread_id": thread_id}}
        init_state = {
            "query": query,
            "messages": [HumanMessage(content=query)],
        }
        result = await self.get_graph().ainvoke(init_state, config=config)
        return result

    async def astream(self, query: str, thread_id: str):
        """正常流程：发送新消息并流式返回"""
        config = {"configurable": {"thread_id": thread_id}}
        init_state = {
            "query": query,
            "messages": [HumanMessage(content=query)],
        }
        async for chunk, metadata in self.get_graph().astream(
            init_state, config=config, stream_mode="messages"
        ):
            yield chunk, metadata

    async def astream_resume(self, thread_id: str, user_response: str):
        """恢复被打断的图执行，流式返回后续结果。

        用 Command(resume=user_response) 恢复 LangGraph 的 interrupt 点，
        图会从暂停处继续执行。
        """
        config = {"configurable": {"thread_id": thread_id}}
        async for chunk, metadata in self.get_graph().astream(
            Command(resume=user_response), config=config, stream_mode="messages"
        ):
            yield chunk, metadata


workflow = LegalMindWorkflow()

# ============================================================
# stream_mode 模式说明
# ============================================================
#
# 1. messages 模式：
#    - yield 时机：每个消息块（如 LLM token）产出时
#    - yield 内容：(AIMessageChunk, metadata)
#    - 特点：有逐字打字机效果 ✅
#    - 缺点：非流式节点（search/document）的数据拿不到，需 aget_state 兜底
#    - 适用：需要实时显示生成内容的聊天场景
#
# 2. updates 模式：
#    - yield 时机：每个节点执行完毕后
#    - yield 内容：该节点的增量更新（{节点名: 变化字段}）
#    - 特点：能拿到所有节点的数据，无打字机效果 ❌
#    - 适用：监控每个节点的输出、调试
#
# 3. values 模式：
#    - yield 时机：每个节点执行完毕后
#    - yield 内容：当前完整的全局 state 快照
#    - 特点：包含所有字段，无打字机效果 ❌
#    - 适用：只需要最终结果、不关心中间过程
#
# Human-in-the-Loop (HITL) 说明：
# - interrupt() 暂停图执行，将数据发送给前端
# - Command(resume=value) 恢复图执行，用户回答作为 interrupt() 的返回值
# - 两个 HITL 节点：check_intent（意图确认，主图）和 evaluate（检索质量，retrieval 子图内）
# ============================================================
