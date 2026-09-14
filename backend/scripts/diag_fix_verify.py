"""修复后验证：覆盖诊断 + 短条文检索抽查（经混合检索链路真实查询）。用完可删。"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.rag.retriever import HybridRetriever


async def coverage_check():
    """复用 diag_law_cover 的逻辑快速复核覆盖数"""
    import asyncpg
    import chromadb
    from pathlib import Path

    conn = await asyncpg.connect("postgresql://legal_user:legal_pass@localhost:5432/legal_db")
    pg_laws = await conn.fetch("SELECT id, content FROM laws")
    await conn.close()

    client = chromadb.PersistentClient(path=str(Path(__file__).resolve().parent.parent / "data" / "chroma"))
    col = client.get_collection("legal_cases")
    chunks = col.get(include=["documents", "metadatas"])
    vec_ids = {m.get("id") for m in chunks["metadatas"] if m.get("type") == "law"}
    corpus = "".join("".join(d.split()) for d in chunks["documents"])

    missing = []
    for r in pg_laws:
        if r["id"] in vec_ids:
            continue
        snippet = "".join((r["content"] or "").split())[:40]
        if not (snippet and snippet in corpus):
            missing.append(r["id"])
    print(f"[覆盖] PG 法条 {len(pg_laws)} | 向量库直入 {len(vec_ids)} | 仍缺失 {len(missing)}")
    return missing


async def retrieval_check():
    """短条文抽查：修复前这些查询只能命中编级长文，现在应能直接命中条文本身"""
    retriever = HybridRetriever()
    probes = [
        "民事主体从事民事活动应当遵循诚信原则",   # 总则编第七条（30字，曾缺失）
        "不得违反法律不得违背公序良俗",           # 总则编第八条（27字，曾缺失）
        "自然人的民事权利能力一律平等",           # 总则编第十四条（15字，曾缺失）
    ]
    for q in probes:
        results = await retriever.retrieve(q, top_k=5)
        hits = []
        for r in results[:5]:
            m = r.get("metadata") or {}
            content = r.get("content") or r.get("page_content") or ""
            hits.append(f"[{m.get('type')}/{m.get('id', '?')}] {content[:42].replace(chr(10), ' ')}")
        print(f"\n查询: {q}")
        for h in hits:
            print(f"  {h}")


async def main():
    missing = await coverage_check()
    if not missing:
        print("[覆盖] ✅ 全部法条已进入检索索引")
    print()
    await retrieval_check()


asyncio.run(main())
