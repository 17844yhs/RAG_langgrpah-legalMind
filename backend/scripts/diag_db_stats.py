"""一次性诊断脚本：统计 PostgreSQL 各表行数 + Chroma 向量库数据量。用完可删。"""
import asyncio
import json
from pathlib import Path

import asyncpg

PG_DSN = "postgresql://legal_user:legal_pass@localhost:5432/legal_db"
CHROMA_PATH = Path(__file__).resolve().parent.parent / "data" / "chroma"


async def pg_stats():
    conn = await asyncpg.connect(PG_DSN)
    tables = await conn.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
    print("=== PostgreSQL 各表行数 ===")
    for t in tables:
        name = t["tablename"]
        cnt = await conn.fetchval(f'SELECT COUNT(*) FROM "{name}"')
        print(f"  {name}: {cnt}")
    # 知识库/文档表如果有内容，抽样看来源
    for maybe in ("documents", "knowledge_base", "laws", "cases", "files"):
        names = {t["tablename"] for t in tables}
        if maybe in names:
            rows = await conn.fetch(f'SELECT * FROM "{maybe}" LIMIT 3')
            for r in rows:
                d = dict(r)
                d.pop("embedding", None)
                s = str(d)
                print(f"  [{maybe} 样例] {s[:200]}")
    await conn.close()


def chroma_stats():
    print("\n=== Chroma 向量库 ===")
    try:
        import chromadb
        client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        cols = client.list_collections()
        total = 0
        for c in cols:
            col = client.get_collection(c.name)
            print(f"  集合 {c.name}: {col.count()} 条向量")
            total += col.count()
            if col.count():
                sample = col.get(limit=2, include=["metadatas"])
                for m in sample.get("metadatas", [])[:2]:
                    print(f"    元数据样例: {json.dumps(m, ensure_ascii=False)[:220]}")
        print(f"  合计: {total} 条向量")
    except Exception as e:
        print(f"  读取失败: {type(e).__name__}: {e}")


if __name__ == "__main__":
    asyncio.run(pg_stats())
    chroma_stats()
