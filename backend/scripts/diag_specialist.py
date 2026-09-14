"""诊断：领域专家检索中间值（改写查询 → 阈值过滤前后条数 → case_type 过滤前后）
定位"专家 0 条"是阈值误杀还是数据本来就少。
"""
import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))

from app.llm.model_client import get_llm
from app.llm.prompts import SPECIALIST_QUERY_REWRITE_PROMPT, DOMAIN_SEARCH_HINTS
from app.agents.retrieval_agent import get_retrieval_agent
from app.agents.supervisor import DOMAIN_TO_CASE_TYPES

CASES = [
    ("劳动争议", "公司拖欠工资不发，我该怎么维权？"),
    ("劳动争议", "劳动合同和劳务合同有什么区别"),
    ("合同纠纷", "劳动合同和劳务合同有什么区别"),
]


async def main():
    agent = get_retrieval_agent()
    for domain, query in CASES:
        resp = await get_llm().ainvoke(SPECIALIST_QUERY_REWRITE_PROMPT.format(
            domain=domain, hints=DOMAIN_SEARCH_HINTS.get(domain, ""), query=query))
        sq = (resp.content or "").strip().splitlines()[0][:120]
        raw = await agent.retrieve(query=sq, top_k=6, doc_type="case")
        allowed = DOMAIN_TO_CASE_TYPES.get(domain, [])
        typed = [c for c in raw if (c.get("case_type") or "") in allowed]
        scores = [f"{c.get('rerank_score') or 0:.3f}" for c in raw]
        print(f"\n[{domain}] {query}")
        print(f"  改写查询: {sq}")
        print(f"  阈值后 {len(raw)} 条 分数={scores}")
        print(f"  case_type 过滤后 {len(typed)} 条 类型={[c.get('case_type') for c in raw]}")


asyncio.run(main())
