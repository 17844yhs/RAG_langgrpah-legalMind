"""短查询 rerank 分数分布诊断（阈值误杀分析）"""
import asyncio
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))


async def main():
    from app.agents.retrieval_agent import get_retrieval_agent
    agent = get_retrieval_agent()
    for q in ["拖欠工资", "公司拖欠工资应该怎么办", "离婚财产分割", "民间借贷"]:
        docs = await agent.retrieve(query=q, top_k=5, doc_type="case")
        scores = [f"{d['rerank_score']:.3f}" for d in docs[:3]]
        titles = [(d.get('title') or '')[:20] for d in docs[:2]]
        print(f"[{q}] {len(docs)}条 top分数={scores} {titles}")
    # 法条对照
    for q in ["拖欠工资", "劳动仲裁"]:
        docs = await agent.retrieve(query=q, top_k=5, doc_type="law")
        scores = [f"{d['rerank_score']:.3f}" for d in docs[:3]]
        print(f"[{q}/law] {len(docs)}条 top分数={scores}")


asyncio.run(main())
