"""API 层冒烟（纯 HTTP，不触碰服务进程内部）+ 评测子集检索指标（独立进程跑 agent）

拆成两个阶段：
  python scripts/smoke_api.py http   # 阶段1：纯 HTTP 打已运行的服务
  python scripts/smoke_api.py eval   # 阶段2：本进程直接算检索指标（需停止服务跑，或与服务共存均可）
"""
import json
import os
import sys
import time
import urllib.request

MODE = sys.argv[1] if len(sys.argv) > 1 else "http"
BASE = "http://localhost:8000/api/v1"


def api(path, method="GET", body=None, timeout=180):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def run_http():
    print("=== 1. cases/search 全链路（Chroma+BM25+RRF+rerank+阈值）===")
    for q in ["公司拖欠工资应该怎么办", "离婚时共同财产如何分割", "民间借贷利息约定过高"]:
        t0 = time.time()
        data = api(f"/cases/search?q={urllib.request.quote(q)}&limit=5")
        rows = data["cases"]
        print(f"\n[{q}] {time.time()-t0:.1f}s, {len(rows)} 条:")
        for x in rows[:3]:
            print(f"  [{x['score']:.3f}] {(x['title'] or '')[:38]}")


def run_eval():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    os.chdir(os.path.join(os.path.dirname(__file__), ".."))
    import asyncio

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

        def law_name(title: str) -> str:
            """从 '法律名 第X条' 提取法律名，规范化连字符（旧库 title 带连字符）"""
            return title.split(" 第")[0].replace("-", "").strip()

        hits, mrr, n = 0, 0.0, 0
        stale_gold = 0
        for s in samples:
            # gold 分层：新样本（逐条 id 在库）→ 精确匹配；旧样本（整部法律 id）→ 法律名前缀匹配
            gold_exact, gold_names = set(), set()
            for gid in s.relevant_law_ids or []:
                law = await Law.filter(id=gid).first()
                if law and " 第" in law.title:
                    gold_exact.add(gid)          # 逐条粒度样本
                elif law:
                    gold_names.add(law_name(law.title))  # 旧整部文档
                    stale_gold += 1
                else:
                    gold_exact.add(gid)
            try:
                docs = await agent.retrieve(query=s.question, top_k=5, doc_type="law")
            except Exception as e:
                print(f"  [检索失败] {s.question[:20]}: {e}")
                continue
            n += 1
            rank = 0
            for i, d in enumerate(docs):
                d_name = law_name(d.get("title") or "")
                if (d.get("id") in gold_exact) or (d_name and d_name in gold_names):
                    rank = i + 1
                    break
            if rank:
                hits += 1
                mrr += 1.0 / rank
            time.sleep(0.15)
        print(f"\n=== 2. 检索指标（{n} 条样本；旧整部 gold {stale_gold} 个按法律名前缀匹配）===")
        if n:
            print(f"Hit@5: {hits}/{n} = {hits/n:.1%}")
            print(f"MRR@5: {mrr/n:.3f}")
        await Tortoise.close_connections()

    asyncio.run(main())


if MODE == "http":
    run_http()
else:
    run_eval()
