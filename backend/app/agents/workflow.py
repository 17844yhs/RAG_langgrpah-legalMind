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
from app.agents.retrieval_agent import RetrievalAgent
from app.agents.human_loop import check_intent, check_retrieval
from app.llm.checkpoint import get_checkpointer


class AgentState(TypedDict):
    """Agent 状态定义"""
    query: str                    # 用户问题（可能被 HITL 补充后更新）
    intent: str                   # 识别的意图
    intent_confidence: float      # 意图置信度（0-1）
    user_supplement: str          # 用户补充信息（HITL resume 后）
    context: list                 # 上下文信息
    retrieved_cases: list         # 检索到的案例
    document_type: str            # 文书类型
    document_params: dict         # 文书参数
    response: str                 # 最终响应
    sources: list                 # 来源引用
    messages: Annotated[list[BaseMessage], add_messages]  # 对话历史

class LegalMindWorkflow:
    """法律咨询 Agent 工作流"""

    def __init__(self):
        self.intent_agent = IntentAgent()
        self.qa_agent = QAAgent()
        self.document_agent = DocumentAgent()
        self.retrieval_agent = RetrievalAgent()
        self._graph = None

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(AgentState)

        # ── 添加节点 ──
        workflow.add_node("intent_recognition", self._intent_node)
        workflow.add_node("check_intent", check_intent)          # HITL #1
        workflow.add_node("case_retrieval", self._retrieval_node)
        workflow.add_node("check_retrieval", check_retrieval)     # HITL #2
        workflow.add_node("qa_generation", self._qa_node)
        workflow.add_node("document_generation", self._document_node)
        workflow.add_node("final_output", self._output_node)

        # 添加图结构 
        # intent_recognition → check_intent → (条件路由)
        workflow.set_entry_point("intent_recognition")
        workflow.add_edge("intent_recognition", "check_intent")
        workflow.add_conditional_edges("check_intent", self._router_by_intent, {
            "qa": "case_retrieval",
            "search": "case_retrieval",
            "document": "document_generation",
        })

        # case_retrieval → check_retrieval → (条件路由)
        workflow.add_edge("case_retrieval", "check_retrieval")
        workflow.add_conditional_edges("check_retrieval", self._route_after_retrieval, {
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

    async def _retrieval_node(self, state: AgentState) -> dict:
        cases = await self.retrieval_agent.retrieve(query=state.get("query"), top_k=5)
        return {"retrieved_cases": cases}

    async def _qa_node(self, state: AgentState) -> dict:
        cases = state["retrieved_cases"]
        messages = state["messages"]

        full_text = ""
        async for chunk in self.qa_agent.stream_answer(cases, messages):
            full_text += chunk.content or ""

        return {
            "response": full_text,
            "messages": [AIMessage(content=full_text)],
            "sources": self.qa_agent._extract_sources(cases),
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
            text = json.dumps(cases, ensure_ascii=False, indent=2)
            return {
                "messages": [AIMessage(content=text)],
                "response": text,
                "sources": self.qa_agent._extract_sources(cases),
            }
        return {}

    #  路由函数 
    def _router_by_intent(self, state: AgentState) -> str:
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
# - 两个 HITL 节点：check_intent（意图确认）和 check_retrieval（检索质量）
# ============================================================
