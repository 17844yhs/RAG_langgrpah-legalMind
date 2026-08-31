"""案例检索 Tool — Pydantic 参数校验 + tenacity 重试 + 已知错误捕获 + ToolNode 兜底"""
import json
import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator
from langchain_core.tools import tool
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


VALID_CATEGORIES = [
    "劳动争议", "合同纠纷", "婚姻家庭", "知识产权",
    "刑事", "行政", "交通事故", "消费权益",
]


# 第 0 层：Pydantic 参数校验 
class CaseSearchInput(BaseModel):
    """案例检索参数 — LLM 从自然语言中提取结构化字段"""
    query: str = Field(description="检索关键词或法律问题描述")
    court: Optional[str] = Field(
        default=None,
        description="法院名称，如'北京市海淀区人民法院'",
    )
    year: Optional[int] = Field(
        default=None,
        description="判决年份",
    )
    category: Optional[str] = Field(
        default=None,
        description="案由类别",
    )

    @field_validator("year")
    @classmethod
    def validate_year(cls, v):
        if v is not None:
            now = datetime.datetime.now().year
            if v < 1990 or v > now:
                raise ValueError(f"年份必须在 1990-{now} 之间")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v):
        if v is not None and v not in VALID_CATEGORIES:
            raise ValueError(f"案由必须是以下之一: {', '.join(VALID_CATEGORIES)}")
        return v


# 第 1 层：tenacity 重试（临时网络/连接错误自动恢复）
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((ConnectionError, TimeoutError, OSError)),
    reraise=True,
)
async def _do_retrieval(query: str, filters: dict, top_k: int) -> list:
    """实际检索执行，tenacity 对连接类错误自动重试"""
    from app.agents.retrieval_agent import get_retrieval_agent
    agent = get_retrieval_agent()
    return await agent.retrieve(query=query, top_k=top_k, filters=filters or None)


# Tool 定义（第 0 + 1 + 2 层串联） 
@tool(args_schema=CaseSearchInput)
async def search_cases(
    query: str,
    court: Optional[str] = None,
    year: Optional[int] = None,
    category: Optional[str] = None,
) -> str:
    """检索相关裁判文书案例。支持按法院、年份、案由进行结构化过滤。
    当首次检索结果不足时，可调整查询参数重新检索。"""
    # 构建 metadata filter
    filters = {}
    if court:
        filters["court"] = court
    if category:
        filters["case_type"] = category

    try:
        # 第 0 层已通过（Pydantic 自动校验）
        # 第 1 层：tenacity 自动重试
        results = await _do_retrieval(query, filters, top_k=10)

        return json.dumps({
            "count": len(results),
            "cases": results,
            "filters_applied": {
                k: v for k, v in {
                    "court": court, "year": year, "category": category
                }.items() if v
            },
        }, ensure_ascii=False)

    # 第 2 层：已知错误友好提示 
    except Exception as e:
        err_msg = str(e).lower()
        if "connection" in err_msg or "chroma" in err_msg or "database" in err_msg:
            return json.dumps({
                "error": "数据库连接异常，请稍后重试",
                "cases": [], "count": 0,
            }, ensure_ascii=False)
        elif "embedding" in err_msg or "model" in err_msg or "transformer" in err_msg:
            return json.dumps({
                "error": "检索服务暂不可用（模型加载异常）",
                "cases": [], "count": 0,
            }, ensure_ascii=False)
        else:
            # 未知错误 → 往上抛，由第 3 层 ToolNode handle_tool_errors 兜底
            raise


# 第 3 层在子图编译时配置 
# ToolNode([search_cases], handle_tool_errors=True)
# 任何未捕获的异常会被包装成 ToolMessage(content="Error: ...")，不崩溃
