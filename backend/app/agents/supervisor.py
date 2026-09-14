"""层级 Agent 团队 — Supervisor 按法律领域并行派发专业检索 Agent，Combiner 汇总

结构：domain_supervisor ──Send 并行──▶ specialist ×N ──▶ combiner

- supervisor：LLM 结构化输出 1-2 个法律领域（带缓存）；低置信/失败 → 空列表 → 主图走原 ReAct 通道
- specialist：领域专家视角改写查询 + 案例库直查。
  刻意不做完整 ReAct：并行分支内的 interrupt 混乱且 N×(1-3) 次 LLM 成本失控；
  领域精度由"专家改写查询 + case_type 过滤"承担
- combiner：按案由去重合并、按 rerank 分截断；不足 TEAM_MERGE_MIN_CASES → 主图升级走 ReAct 兜底

数据适配说明：知识库 case_type 实测分布（scripts/diag_case_type.py）为
民事 112 / 劳动争议 4 / 行政 2 / 民事公益诉讼 1——无"合同纠纷/婚姻家庭"等细分标注。
因此领域过滤用 DOMAIN_TO_CASE_TYPES 映射（细分领域归入"民事"大类），
专家的核心价值在领域化查询改写；未来数据补充标注后，改映射表即可获得精准过滤。
"""
import logging
from typing import List

from pydantic import BaseModel, Field
from typing import TYPE_CHECKING

from app.llm.model_client import get_llm
from app.llm.prompts import (
    DOMAIN_SUPERVISOR_PROMPT,
    SPECIALIST_QUERY_REWRITE_PROMPT,
    DOMAIN_SEARCH_HINTS,
)
from app.cache.redis_cache import cache_get, cache_set, make_key
from app.config import settings
from app.agents.retrieval_agent import get_retrieval_agent
from app.tools.search_tool import VALID_CATEGORIES

if TYPE_CHECKING:
    from app.agents.workflow import AgentState

logger = logging.getLogger("app.agent")


# ── 领域 → 知识库 case_type 映射 ──
# 细分领域没有独立标注时归入"民事"大类；数据补标注后只需改这张表
DOMAIN_TO_CASE_TYPES = {
    "劳动争议": ["劳动争议", "民事"],
    "合同纠纷": ["民事"],
    "婚姻家庭": ["民事"],
    "交通事故": ["民事"],
    "消费权益": ["民事"],
    "知识产权": ["民事"],
    "刑事": ["刑事"],
    "行政": ["行政", "民事公益诉讼"],
}


class DomainRoute(BaseModel):
    """领域路由结构化输出"""
    domains: List[str] = Field(
        default_factory=list,
        description="涉及的法律领域列表（从可选领域中选，最多 2 个；无法判断则为空列表）",
    )
    reasoning: str = Field(default="", description="一句话判断理由")


class SpecialistResult(BaseModel):
    """单个领域专家的检索产出（写入 state.specialist_results）"""
    domain: str
    search_query: str       # 领域专家改写后的检索查询（观测/调试用）
    cases: list


async def domain_supervisor_node(state: "AgentState") -> dict:
    """领域路由：识别问题涉及的 1-2 个法律领域（空 = 交给通用 ReAct 通道）

    降级策略与意图识别一致（非关键路径）：LLM 失败返回空列表走通用通道，
    绝不因分派失败阻塞主流程。
    """
    query = state["query"]
    cache_key = make_key("domain_route", query)
    cached = await cache_get(cache_key)
    if cached is not None:
        logger.info("领域路由缓存命中: %s", cached.get("domains"))
        return {"domains": cached.get("domains") or []}

    structured_llm = (
        get_llm()
        .with_structured_output(DomainRoute, method="function_calling")
        .with_retry(stop_after_attempt=2)
    )
    try:
        result = await structured_llm.ainvoke(
            DOMAIN_SUPERVISOR_PROMPT.format(
                query=query, categories="、".join(VALID_CATEGORIES)
            )
        )
        if result is None:
            raise ValueError("structured output returned None")
        # 白名单过滤 + 去重 + 数量截断：LLM 可能幻觉出枚举外的领域名或重复派发
        domains = list(dict.fromkeys(
            d for d in (result.domains or []) if d in VALID_CATEGORIES
        ))[: settings.MAX_SPECIALISTS]
        await cache_set(cache_key, {"domains": domains}, settings.INTENT_CACHE_TTL)
    except Exception:
        logger.exception("领域路由失败，降级为通用检索通道")
        domains = []

    return {"domains": domains}


async def specialist_node(state: dict) -> dict:
    """领域专家：改写查询 → 案例库直查。

    经 Send("specialist", {"domain": ..., "query": ...})派发，
    state 即 Send payload（不是完整 AgentState）；返回值经
    specialist_results 的 operator.add reducer 并行累积进主图状态。
    """
    domain = state["domain"]
    query = state["query"]

    # 1) 领域专家视角改写查询（cache-aside：同领域同问题短窗内复用）
    rewrite_key = make_key("specialist_rewrite", domain, query)
    search_query = await cache_get(rewrite_key)
    if search_query is None:
        try:
            resp = await get_llm().ainvoke(
                SPECIALIST_QUERY_REWRITE_PROMPT.format(
                    domain=domain,
                    hints=DOMAIN_SEARCH_HINTS.get(domain, ""),
                    query=query,
                )
            )
            # 取首行、限长，防御模型不守"只输出一行"的指令
            search_query = (resp.content or "").strip().splitlines()[0][:120] if resp else query
            if not search_query:
                search_query = query
            await cache_set(rewrite_key, search_query, settings.RETRIEVAL_CACHE_TTL)
        except Exception:
            logger.exception("专家查询改写失败（%s），回退原始查询", domain)
            search_query = query

    # 2) 案例库直查。type=case 在召回层下推（等值过滤可下推 Chroma）；
    #    case_type 细分在本地筛——若塞进 filters（$in 复杂条件）会连累
    #    type 下推一并失效，得不偿失
    try:
        agent = get_retrieval_agent()
        cases = await agent.retrieve(query=search_query, top_k=6, doc_type="case")
        allowed = DOMAIN_TO_CASE_TYPES.get(domain)
        if allowed:
            cases = [c for c in cases if (c.get("case_type") or "") in allowed]
    except Exception:
        logger.exception("领域专家检索失败: %s", domain)
        cases = []

    result = SpecialistResult(domain=domain, search_query=search_query, cases=cases)
    return {"specialist_results": [result.model_dump()]}


def combiner_node(state: "AgentState") -> dict:
    """合并器（fan-in）：多专家结果去重、按 rerank 分截断，写入 retrieved_cases"""
    results = state.get("specialist_results") or []
    # dict 池去重：同一案例多 chunk 时保留 rerank 分更高的那个 chunk
    pool: dict = {}
    for r in results:
        for c in r.get("cases", []):
            # case_number 是天然去重键，缺失时退回三元组
            key = (
                c.get("case_number")
                or f"{c.get('title')}|{c.get('court')}|{c.get('judgment_date')}"
            )
            if key not in pool or (c.get("rerank_score") or 0) > (pool[key].get("rerank_score") or 0):
                pool[key] = c

    merged = sorted(pool.values(), key=lambda c: c.get("rerank_score") or 0, reverse=True)[:12]
    logger.info(
        "领域专家合并：%s → 去重后 %d 条",
        [r.get("domain") for r in results], len(merged),
    )
    return {"retrieved_cases": merged}
