"""短查询原始召回诊断（绕过缓存和阈值）"""
import asyncio
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))


async def main():
    from app.rag.retriever import HybridRetriever
    from app.rag.reranker import Reranker
    from app.config import settings

    ret = HybridRetriever()
    rr = Reranker()
    q = "拖欠工资"
    cands = await ret.retrieve(query=q, top_k=15, filters={"type": "case"})
    print(f"原始候选（case 过滤后）: {len(cands)}")
    if rr and cands:
        ranked = await rr.rerank(query=q, documents=cands, top_k=5)
        print(f"rerank 后: {len(ranked)}")
        for d in ranked:
            print(f"  [{d.get('rerank_score'):.4f}] {(d.get('title') or '')[:30]} (type={d.get('type')})")
    # 对照：不过滤 type 的原始召回
    cands2 = await ret.retrieve(query=q, top_k=15)
    types = {}
    for c in cands2:
        types[c.get("type")] = types.get(c.get("type"), 0) + 1
    print(f"不过滤 type 的候选分布: {types}")
    print(f"阈值: {settings.RAG_SCORE_THRESHOLD}")


asyncio.run(main())
