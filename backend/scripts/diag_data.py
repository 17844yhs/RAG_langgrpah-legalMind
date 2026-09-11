"""RAG 数据侧诊断：向量库规模 / chunk 长度分布 / metadata 缺失率 / PG 数据量"""
import asyncio
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.chdir(os.path.join(os.path.dirname(__file__), '..'))

from collections import Counter


def chroma_stats():
    from app.rag.vector_store import get_vector_store
    vs = get_vector_store()
    col = vs._collection
    total = col.count()
    data = col.get(include=["documents", "metadatas"])
    docs = data["documents"]
    metas = data["metadatas"]

    print(f"=== Chroma 总 chunk 数: {total} ===")
    types = Counter(m.get("type") for m in metas)
    print(f"type 分布: {dict(types)}")

    lens = [len(d) for d in docs]
    if lens:
        lens.sort()
        n = len(lens)
        print(f"chunk 字符数: min={lens[0]} p25={lens[n//4]} p50={lens[n//2]} "
              f"p75={lens[3*n//4]} p90={lens[9*n//10]} max={lens[-1]} avg={sum(lens)//n}")

    # 按 type 分别的 chunk 数（每个原始文档被切几块）
    case_ids = [m.get("id") for m in metas if m.get("type") == "case"]
    law_ids = [m.get("id") for m in metas if m.get("type") == "law"]
    print(f"案例原始文档数(按唯一 id): {len(set(case_ids))}, 法条: {len(set(law_ids))}")
    if case_ids:
        per_doc = Counter(case_ids)
        chunks_per_case = sorted(per_doc.values())
        print(f"每案例 chunk 数: min={chunks_per_case[0]} p50={chunks_per_case[len(chunks_per_case)//2]} max={chunks_per_case[-1]}")

    # 噪音指标：超短 chunk（信息量不足）与超长 chunk
    tiny = sum(1 for l in lens if l < 100)
    print(f"超短 chunk(<100字, 尾部碎片噪音): {tiny} ({tiny*100//max(n,1)}%)")

    # metadata 缺失率（案例）
    missing = Counter()
    case_metas = [m for m in metas if m.get("type") == "case"]
    for m in case_metas:
        for k in ("case_number", "court", "judgment_date", "case_type", "summary", "laws"):
            if m.get(k) in (None, "", []):
                missing[k] += 1
    if case_metas:
        print(f"案例 metadata 缺失(共 {len(case_metas)} chunks): {dict(missing)}")

    # 法条 category 分布
    law_cats = Counter(m.get("category") for m in metas if m.get("type") == "law")
    print(f"法条 category 分布: {dict(law_cats)}")

    # 案例 case_type 分布
    case_types = Counter(m.get("case_type") for m in case_metas)
    print(f"案例 case_type 分布: {dict(case_types)}")


async def pg_stats():
    from tortoise import Tortoise
    await Tortoise.init(
        db_url="postgres://legal_user:legal_pass@localhost:5432/legal_db",
        modules={"models": ["app.models.case", "app.models.law"]},
    )
    from app.models.case import Case
    from app.models.law import Law
    cases = await Case.all()
    laws = await Law.all()
    print(f"\n=== PG: 案例 {len(cases)} 条, 法条 {len(laws)} 条 ===")
    # 案例 content 长度
    if cases:
        clens = sorted(len(c.content or "") for c in cases)
        n = len(clens)
        print(f"案例 content 字符数: min={clens[0]} p50={clens[n//2]} max={clens[-1]}")
        empty_content = sum(1 for c in cases if not c.content)
        print(f"content 为空的案例: {empty_content}")
    await Tortoise.close_connections()


if __name__ == "__main__":
    chroma_stats()
    asyncio.run(pg_stats())
