"""聊天 API — 支持 SSE 流式输出 + Human-in-the-Loop interrupt/resume"""
import uuid
import json
from typing import List, Optional
from pydantic import BaseModel, Field

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse

from app.agents.workflow import workflow
from app.dependencies import get_current_user
from app.models.chat import ChatSession, ChatMessageRecord
from app.models.user import User


router = APIRouter()
# 请求/响应模型 

class ChatMessage(BaseModel):
    """聊天消息"""
    role: str
    content: str

class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: Optional[str] = None

class ResumeRequest(BaseModel):
    """恢复被打断的图执行"""
    session_id: str
    response: str = Field(min_length=1, max_length=2000)

class ChatResponse(BaseModel):
    """聊天响应"""
    response: str
    intent: str
    sources: List[dict]
    session_id: str

# 辅助函数 
async def _get_user_obj(user_info: dict) -> User:
    return await User.get(id=user_info["user_id"])

async def _ensure_session(session_id: str, user_obj: User) -> ChatSession:
    """确保会话存在并属于当前用户（不存在则创建）"""
    session, _ = await ChatSession.get_or_create(
        # session_id 既用于查询，也在创建时写入
        session_id=session_id,
        # 只在“创建”时使用，查询时忽略
        defaults={"user": user_obj},
    )
    return session


async def _record_messages(session: ChatSession, user_msg: str, assistant_msg: str) -> None:
    """把一轮对话写入 ChatMessageRecord，供侧边栏 UI 读取"""
    await ChatMessageRecord.create(chat_session=session, role="user", content=user_msg)
    await ChatMessageRecord.create(chat_session=session, role="assistant", content=assistant_msg)


async def _check_interrupt(session_id: str) -> Optional[dict]:
    """检查图是否被 interrupt 打断，返回 interrupt 数据或 None"""
    graph = workflow.get_graph()
    config = {"configurable": {"thread_id": session_id}}
    state = await graph.aget_state(config)

    # state.next 非空 = 图被 interrupt 暂停了，还有节点等待执行
    if state.next:
        tasks = state.tasks if hasattr(state, "tasks") else []
        if tasks and hasattr(tasks[0], "interrupts") and tasks[0].interrupts:
            return tasks[0].interrupts[0].value
    return None


async def _finalize_stream(session, query, full_text, session_id):
    """流结束后的收尾：兜底输出、记录消息、发送 sources"""
    graph = workflow.get_graph()
    config = {"configurable": {"thread_id": session_id}}
    state = await graph.aget_state(config)
    values = state.values or {}
    # 非流式节点（search/document）的 response 兜底一次性输出
    if not full_text:
        fallback = values.get("response", "")
        if fallback:
            full_text = fallback
            yield f"data: {json.dumps({'content': fallback}, ensure_ascii=False)}\n\n"
    # 写入侧边栏记录
    if full_text:
        await _record_messages(session, query, full_text)
    # 发送引用来源
    sources = values.get("sources") or []
    if sources:
        yield f"data: {json.dumps({'sources': sources}, ensure_ascii=False)}\n\n"

#  路由 
@router.post("/send", response_model=ChatResponse)
async def send_message(request: ChatRequest, user=Depends(get_current_user)):
    """发送消息（非流式）"""
    user_obj = await _get_user_obj(user)
    session_id = request.session_id or str(uuid.uuid4())
    session = await _ensure_session(session_id, user_obj)
    result = await workflow.run(query=request.message, thread_id=session_id)

    await _record_messages(session, request.message, result["response"])

    return ChatResponse(
        response=result["response"],
        intent=result.get("intent", ""),
        sources=result.get("sources", []),
        session_id=session_id,
    )

@router.post("/stream")
async def stream_message(request: ChatRequest, user=Depends(get_current_user)):
    """发送消息（流式响应 + interrupt 检测）"""
    user_obj = await _get_user_obj(user)
    session_id = request.session_id or str(uuid.uuid4())
    session = await _ensure_session(session_id, user_obj)
    query = request.message

    async def generate():
        full_text = ""
        try:
            # 先发 session_id，前端新会话需要用它来 resume
            yield f"data: {json.dumps({'session_id': session_id}, ensure_ascii=False)}\n\n"

            async for chunk, metadata in workflow.astream(query=query, thread_id=session_id):
                node = metadata.get("langgraph_node") if metadata else None
                if node == "qa_generation" and chunk.content:
                    full_text += chunk.content
                    yield f"data: {json.dumps({'content': chunk.content}, ensure_ascii=False)}\n\n"

            # 检查是否被 interrupt 打断 
            interrupt_data = await _check_interrupt(session_id)
            if interrupt_data:
                # 被打断：发送 interrupt 事件给前端，等待用户交互
                yield f"data: {json.dumps({'interrupt': interrupt_data}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return

            #  正常结束 
            async for event in _finalize_stream(session, query, full_text, session_id):
                yield event

            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'content': f'抱歉，处理出错：{e}'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.post("/resume")
async def resume_interrupted(request: ResumeRequest, user=Depends(get_current_user)):
    """恢复被 interrupt 打断的图执行（流式响应）。

    用户回答了 interrupt 问题后调用此端点。
    resume 后可能触发下一个 interrupt（如先意图确认，再检索补充），
    所以同样需要检测 interrupt 并返回 SSE 流。
    """
    user_obj = await _get_user_obj(user)
    session = await _ensure_session(request.session_id, user_obj)

    async def generate():
        full_text = ""
        try:
            async for chunk, metadata in workflow.astream_resume(
                thread_id=request.session_id,
                user_response=request.response,
            ):
                node = metadata.get("langgraph_node") if metadata else None
                if node == "qa_generation" and chunk.content:
                    full_text += chunk.content
                    yield f"data: {json.dumps({'content': chunk.content}, ensure_ascii=False)}\n\n"

            #  resume 后再次检查 interrupt（可能触发第二个 HITL 节点） 
            interrupt_data = await _check_interrupt(request.session_id)
            if interrupt_data:
                yield f"data: {json.dumps({'interrupt': interrupt_data}, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"
                return

            #  正常结束 
            async for event in _finalize_stream(
                session, f"[resume] {request.response}", full_text, request.session_id
            ):
                yield event

            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'content': f'抱歉，处理出错：{e}'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


#  会话管理 
@router.get("/sessions")
async def list_sessions(user=Depends(get_current_user)):
    """获取当前用户的会话列表"""
    user_obj = await _get_user_obj(user)
    sessions = await ChatSession.filter(user=user_obj).order_by("-created_at").limit(50)
    result = []
    for s in sessions:
        last_msg = await ChatMessageRecord.filter(chat_session=s, role="user").order_by("created_at").first()
        result.append({
            "session_id": s.session_id,
            "title": last_msg.content[:30] if last_msg else "新对话",
            "created_at": s.created_at.isoformat() if s.created_at else None,
        })
    return {"sessions": result}


async def _get_owned_session(session_id: str, user_info: dict) -> ChatSession:
    """获取属于当前用户的会话，不存在或越权则 404"""
    session = await ChatSession.get_or_none(session_id=session_id)
    if not session or str(session.user_id) != user_info["user_id"]:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, user=Depends(get_current_user), limit: int = 50):
    session = await _get_owned_session(session_id, user)
    messages = await ChatMessageRecord.filter(chat_session=session).order_by("created_at").limit(limit)
    return {"messages": [{"role": m.role, "content": m.content} for m in messages]}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user=Depends(get_current_user)):
    session = await _get_owned_session(session_id, user)
    await session.delete()
    return {"message": "Session deleted"}
