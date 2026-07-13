"""LangGraph 工作流编排 — 定义 Agent 之间的协作流程"""
import json
from typing import TypedDict,Annotated
from langgraph.graph import StateGraph, END
# from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import BaseMessage ,HumanMessage,AIMessage
from langgraph.graph.message import add_messages

from app.agents.intent_agent import IntentAgent
from app.agents.qa_agent import QAAgent
from app.agents.document_agent import DocumentAgent
from app.agents.retrieval_agent import RetrievalAgent
from app.llm.checkpoint import get_checkpointer


class AgentState(TypedDict):
    """Agent 状态定义"""
    query: str                    # 用户问题
    intent: str                   # 识别的意图
    context: list                 # 上下文信息
    retrieved_cases: list         # 检索到的案例
    document_type: str            # 文书类型
    document_params: dict         # 文书参数
    response: str                 # 最终响应
    sources: list                 # 来源引用
    messages: Annotated[list[BaseMessage],add_messages]                # 对话历史

class LegalMindWorkflow:
    """法律咨询 Agent 工作流"""

    def __init__(self):
        self.intent_agent = IntentAgent()
        self.qa_agent = QAAgent()
        self.document_agent = DocumentAgent()
        self.retrieval_agent = RetrievalAgent()
        # self.checkpointer = MemorySaver()
        self._graph=None
    
    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(AgentState)

        # 添加节点
        workflow.add_node("intent_recognition", self._intent_node)
        workflow.add_node("case_retrieval", self._retrieval_node)
        workflow.add_node("qa_generation", self._qa_node)
        workflow.add_node("document_generation", self._document_node)
        workflow.add_node("final_output", self._output_node)

        # 设置入口
        workflow.set_entry_point("intent_recognition")
        # 意图识别后按意图类型路由
        workflow.add_conditional_edges("intent_recognition",self._router_by_intent,{
            "qa":"case_retrieval",
            "search":"case_retrieval",
            "document":"document_generation"
        })
        # 检索后根据意图决定下一步
        workflow.add_conditional_edges("case_retrieval",self._route_after_retrieval,{
            "qa":"qa_generation",
            "search":"final_output",
        })
        workflow.add_edge("qa_generation","final_output")
        workflow.add_edge("document_generation","final_output")
        workflow.add_edge("final_output",END)

        # return workflow.compile(checkpointer=self.checkpointer)
        return workflow.compile(checkpointer=get_checkpointer())

    async def _intent_node(self,state:AgentState) ->dict:
        intent = await self.intent_agent.recognize(state.get("query"))
        return {"intent":intent}
    
    async def _retrieval_node(self,state:AgentState) ->dict:
        cases = await self.retrieval_agent.retrieve(query=state.get("query"),top_k=5)
        return {"retrieved_cases":cases}
    
    async def _qa_node(self,state:AgentState) ->dict:
        cases = state['retrieved_cases']
        messages = state['messages']

        full_text =''
        async for chunk in self.qa_agent.stream_answer(cases,messages):
            full_text += chunk.content or ''

        return {
            "response":full_text,
            "messages":[AIMessage(content=full_text)],
            "sources":self.qa_agent._extract_sources(cases)
            }
    
    async def _document_node(self, state: AgentState) -> dict:
        response = await self.document_agent.generate(
            document_type=state.get("document_type", "起诉状"),
            params=state.get("document_params", {}),
            query=state["query"]
        )
        content = response["content"]
        return {
            "response": content, 
            "sources": response.get("references", []),
            "messages":[AIMessage(content=content)],
            }

    async def _output_node(self,state:AgentState) ->dict:

        if state.get("intent") == "search" and not state.get("response"):
            cases = state.get("retrieved_cases", [])
            text = json.dumps(cases, ensure_ascii=False, indent=2)
            return {
                "messages": [AIMessage(content=text)],
                "response": text,
                "sources": self.qa_agent._extract_sources(cases),
            }
        return {}

    def _router_by_intent(self,state:AgentState) ->str:
        intent = state["intent"]
        if intent == "document":
            return "document"
        elif intent == "search":
            return "search"
        return "qa"

    def _route_after_retrieval(self,state:AgentState) ->str:
        if state["intent"] =="search":
            return "search"
        else:
            return "qa"
    
    def get_graph(self):
        """懒加载编译图。首次调用时编译并缓存。"""
        if self._graph is None:
            self._graph = self._build_graph()
        return self._graph


    async def run(self,query:str,thread_id:str) ->dict:

        config = {"configurable":{"thread_id":thread_id}}
        init_stat ={
            "query":query,
            "message": [HumanMessage(content=query)],
        }
        result = await self.get_graph().ainvoke(init_stat,config=config)
        return result

    async def astream(self,query:str,thread_id:str):
        config = {"configurable":{"thread_id":thread_id}}
        init_stat ={
            "query":query,
            "message": [HumanMessage(content=query)],
        }
        async for chunk ,metadata in self.get_graph().astream(init_stat,config=config,stream_mode ="messages"):
            yield chunk,metadata

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
# 节点内部的 LLM 调用（LangChain 的 astream）发出的回调事件会被 LangGraph 拦截，通过stream_mode='messages' 逐块产出
# (因此调用 API 时要用 async for 消费 LangGraph 拦截到的异步生成器)


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
# ============================================================