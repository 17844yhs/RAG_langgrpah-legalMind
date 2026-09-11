"""评测 miss 详情诊断：gold 条号 vs 检索结果"""
import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))


async def main():
    from tortoise import Tortoise
    await Tortoise.init(
        db_url="postgres://legal_user:legal_pass@localhost:5432/legal_db",
        modules={"models": ["app.models.law", "app.models.case", "app.models.eval_dataset"]},
    )
    from app.models.eval_dataset import EvalSample
    from app.models.law import Law
    from app.agents.retrieval_agent import get_retrieval_agent

    samples = await EvalSample.filter(relevant_law_ids__isnull=False).limit(20)
    agent = get_retrieval_agent()
    for s in samples:
        gold_ids = s.relevant_law_ids
        gold_titles = []
        for gid in gold_ids:
            law = await Law.filter(id=gid).first()
            gold_titles.append(law.title if law else f"{gid}(不存在!)")
        docs = await agent.retrieve(query=s.question, top_k=5, doc_type="law")
        got_ids = [d["id"] for d in docs]
        hit_rank = next((i + 1 for i, d in enumerate(docs) if d["id"] in gold_ids), 0)
        mark = f"HIT@{hit_rank}" if hit_rank else "MISS"
        print(f"[{mark}] {s.question[:24]}")
        print(f"   gold: {gold_titles}")
        if not hit_rank:
            for d in docs[:3]:
                print(f"   got : [{d['rerank_score']:.3f}] {d['title'][:40]}")
        time.sleep(0.15)
    await Tortoise.close_connections()


asyncio.run(main())
