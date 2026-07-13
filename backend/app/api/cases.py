"""
案例检索 API 路由
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional

from app.agents.retrieval_agent import RetrievalAgent
from app.services.case_service import CaseService

router = APIRouter()


class CaseDetail(BaseModel):
    """案例详情"""
    id: str  # 案例唯一标识
    title: str  # 案例标题
    case_number: str  # 案号
    court: str  # 审理法院
    judgment_date: str  # 裁判日期
    case_type: str  # 案件类型（民事/劳动争议等）
    summary: str  # 裁判要旨/案情摘要
    content: Optional[str] = None  # 裁判文书全文（仅详情接口返回）
    laws: List[str] = []  # 引用的法条列表

@router.get("/search")
async def search_cases_get(
    q: str = Query(..., description="搜索关键词"), 
    court: Optional[str] = Query(None, description="法院"),
    case_type: Optional[str] = Query(None, description="案件类型"),
    limit: int = Query(10, ge=1, le=100),
):
    """搜索案例（GET 方式）"""
    filters = {}
    if court:
        filters["court"]= court
    if case_type:
        filters["case_type"]= case_type
    
    agent = RetrievalAgent()
    results = await agent.retrieve(
        query=q,
        top_k=limit,
        filters=filters if filters else None
    )

    return {"cases": results, "total": len(results)}

@router.get("/{case_id}", response_model=CaseDetail)
async def get_case_detail(case_id: str):
    """获取案例详情"""
    service = CaseService()
    case = await service.get_by_id(case_id)

    if not case:
        raise HTTPException(status_code=404,detail="没有找到这个案例")
    return CaseDetail(**case)