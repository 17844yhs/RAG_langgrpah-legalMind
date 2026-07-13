import uuid
import json
from typing import List, Optional
from pydantic import BaseModel

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse

from app.agents.workflow import workflow
from app.dependencies import get_current_user
from app.models.chat import ChatSession, ChatMessageRecord
from app.models.user import User


router = APIRouter()

class ChatMessage(BaseModel):
    """聊天消息"""
    role: str
    content: str

class ChatRequest(BaseModel):
    """聊天请求"""
    message: str
    session_id: Optional[str] = None

class ChatResponse(BaseModel):
    """聊天响应"""
    response: str
    intent: str
    sources: List[dict]
    session_id: str

async def _get_user_obj(user_info:dict) -> User:
    """根据 get_current_user 返回的信息拿到 User 对象"""
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

@router.post('/send',response_model=ChatResponse)
async def send_message(request:ChatRequest,user=Depends(get_current_user)):
    """发送消息（非流式）"""
    user_obj = await _get_user_obj(user)
    session_id = request.session_id or str(uuid.uuid4())
    session = await _ensure_session(session_id,user_obj)
    result = await workflow.run(query=request.message,thread_id=session_id)

    await _record_messages(session,request.message,result["response"])

    return ChatResponse(
        response=result["response"],
        intent=result.get("intent",""),
        sources=result.get("sources",[]),
        session_id=session_id
    )

@router.post("/stream")
async def stream_message(request: ChatRequest, user=Depends(get_current_user)):
    """发送消息（流式响应）"""
    user_obj = await _get_user_obj(user)
    session_id = request.session_id or str(uuid.uuid4())
    session = await _ensure_session(session_id, user_obj)
    query = request.message
    # 获取数据
    async def generate():
        full_text =""
        try:
            # 消费的异步生成器是节点state的增量
            async for chunk, metadata in workflow.astream(query=query,thread_id=session_id):
                node = metadata.get("langgraph_node") if metadata else None
                if node == "qa_generation" and chunk.content:
                    full_text += chunk.content
                    yield f"data: {json.dumps({'content': chunk.content}, ensure_ascii=False)}\n\n"
                
            # 流式模式不暴露最终 state，需单独读取（取 sources；并为 search/document 意图兜底）
            # 整个图执行完毕后的最终完整 state 快照，而不是每个节点增量
            graph = workflow.get_graph()
            config = {"configurable": {"thread_id": session_id}}
            state = await graph.aget_state(config)
            values = state.values or {}

            # 非 qa 意图（search/document）未走流式 LLM，用最终 response 兜底一次性输出
            if not full_text:
                fallback = values.get("response", "")
                if fallback:
                    full_text = fallback
                    yield f"data: {json.dumps({'content': fallback}, ensure_ascii=False)}\n\n"
            # 写入侧边栏记录
            await _record_messages(session, query, full_text)

            # 最后发送 sources
            sources = values.get("sources") or []
            if sources:
                yield f"data: {json.dumps({'sources': sources}, ensure_ascii=False)}\n\n"

            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'content': f'抱歉，处理出错：{e}'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(generate(),media_type="text/event-stream")

@router.get('/sessions')
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
            "created_at": s.created_at.isoformat() if s.created_at else None
            })
    return {'sessions':result}

async def _get_owned_session(session_id: str, user_info: dict) -> ChatSession:
    """获取属于当前用户的会话，不存在或越权则 404"""
    session = await ChatSession.get_or_none(session_id=session_id)
    if not session or str(session.user_id) != user_info["user_id"]:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, user=Depends(get_current_user), limit: int = 50):
    """获取某个会话的消息"""
    session = await _get_owned_session(session_id,user)
    messages = await ChatMessageRecord.filter(chat_session=session).order_by("created_at").limit(limit)
    return {"messages": [{"role": m.role, "content": m.content} for m in messages]}

@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user=Depends(get_current_user)):
    session = await _get_owned_session(session_id,user)
    await session.delete()
    return {"message": "Session deleted"}