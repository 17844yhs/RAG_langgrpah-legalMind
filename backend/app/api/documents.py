"""
文书生成 API 路由
"""
import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, List

from app.agents.document_agent import DocumentAgent
from app.agents.retrieval_agent import get_retrieval_agent
from app.dependencies import get_current_user
from app.exceptions import AppException, sse_error_event

logger = logging.getLogger("app.error")

router = APIRouter()

class DocumentGenerateRequest(BaseModel):
    """文书生成请求"""
    document_type: str
    query: str
    params: Dict
    use_references: bool = True

class DocumentGenerateResponse(BaseModel):
    """文书生成响应"""
    content: str
    document_type: str
    references: List[Dict]

@router.post("/generate", response_model=DocumentGenerateResponse)
async def generate_document(request: DocumentGenerateRequest, user=Depends(get_current_user)):
    """生成法律文书（非流式）"""
    agent = DocumentAgent()
    retrieval_agent = get_retrieval_agent()

    references = []
    if request.use_references:
        references = await retrieval_agent.retrieve(
            query=request.query,
            top_k=3
        )
    
    result = await agent.generate(
        document_type=request.document_type,
        params=request.params,
        query=request.query,
        references=references
    )

    return DocumentGenerateResponse(
        content=result["content"],
        document_type=result["document_type"],
        references=result["references"]
    )

@router.post("/generate/stream")
async def generate_document_stream(request: DocumentGenerateRequest, user=Depends(get_current_user), http_request: Request = None):
    """生成法律文书（流式）"""
    trace_id = http_request.state.trace_id if http_request else None

    async def generate():
        try:
            agent = DocumentAgent()
            retrieval_agent = get_retrieval_agent()

            references = []
            if request.use_references:
                references = await retrieval_agent.retrieve(
                    query=request.query,
                    top_k=3
                )

            # 流式生成文书（prompt 构造封装在 DocumentAgent.astream_generate 内）
            full_text = ""
            async for chunk in agent.astream_generate(
                request.document_type, request.params, request.query, references
            ):
                token = chunk.content
                if token:
                    full_text += token
                    yield f"data: {json.dumps({'content': token}, ensure_ascii=False)}\n\n"

            # 发送 references
            if references:
                yield f"data: {json.dumps({'references': references[:2]}, ensure_ascii=False)}\n\n"

        except AppException as e:
            # 已知业务错误：错误码 + 文案可以放心给前端
            yield sse_error_event(e.code.value, e.detail, trace_id)
        except Exception:
            # 未知错误：堆栈只进日志（原始异常可能含模型路径等敏感信息），对外只给 traceId
            logger.exception("[%s] SSE 流式文书生成失败", trace_id)
            yield sse_error_event("SYS_001", "文书生成服务暂时不可用，请稍后重试", trace_id)

        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/templates")
async def get_templates():
    """获取支持的文书模板列表"""
    return {
        "templates": [
            {"type": "起诉状", "description": "民事起诉状"},
            {"type": "答辩状", "description": "民事答辩状"},
            {"type": "合同", "description": "各类合同"},
            {"type": "律师函", "description": "律师催告函"},
            {"type": "上诉状", "description": "民事上诉状"},
        ]
    }
