"""检索质量实测：库内/库外问题跑全链路（RRF + rerank），观察分数分布
目的：区分"检索链路问题"还是"数据问题"，并验证 RAG_SCORE_THRESHOLD 接入的合理性
"""
import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))

from app.agents.retrieval_agent import get_retrieval_agent


QUERIES = [
    # (问题, 库内预期)
    ("夫妻离婚时共同财产如何分割？", True),
    ("公司拖欠工资，员工可以要求经济补偿吗？", True),
    ("交通事故造成人身损害，如何赔偿？", True),      # 库内无交通事故案例，只有法条
    ("民间借贷利息约定多少受法律保护？", True),        # 库内有借款案例
    ("外卖骑手在送餐途中撞伤行人，责任由谁承担？", False),  # 库外：新业态用工+交通
    ("小区电梯故障困人，物业要承担什么责任？", False),    # 库外：物业管理
]


async def main():
    agent = get_retrieval_agent()
    for q, expected in QUERIES:
        cases = await agent.retrieve(query=q, top_k=5)
        print(f"\n{'='*72}")
        print(f"Q: {q}  [{'库内' if expected else '库外'}]")
        if not cases:
            print("  （无结果）")
            continue
        for i, c in enumerate(cases, 1):
            title = (c.get("title") or "")[:28]
            score = c.get("rerank_score")
            score_s = f"{score:.3f}" if score is not None else "  -  "
            print(f"  {i}. [{score_s}] {title}")


if __name__ == "__main__":
    asyncio.run(main())
