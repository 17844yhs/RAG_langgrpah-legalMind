"""一次性诊断：核对 PG 与 Chroma 的数据完整性差异。用完可删。"""
import asyncio
from pathlib import Path

import asyncpg
import chromadb

PG_DSN = "postgresql://legal_user:legal_pass@localhost:5432/legal_db"
CHROMA_PATH = Path(__file__).resolve().parent.parent / "data" / "chroma"


async def main():
    conn = await asyncpg.connect(PG_DSN)

    # ---- 案例对比 ----
    pg_cases = await conn.fetch("SELECT id::text, title, case_type FROM cases ORDER BY id")
    pg_case_ids = {r["id"] for r in pg_cases}

    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    col = client.get_collection("legal_cases")
    data = col.get(include=["metadatas"])
    metas = data["metadatas"]

    vec_case_ids = {m.get("id") for m in metas if m.get("type") == "case"}

    missing_cases = []
    for r in pg_cases:
        if r["id"] not in vec_case_ids:
            missing_cases.append(r)
    print("=== 案例覆盖 ===")
    print(f"PG 案例 {len(pg_case_ids)} 个 | 向量库案例 {len(vec_case_ids)} 个")
    for r in missing_cases:
        print(f"  未入向量库: {r['id'][:8]}  {r['title']}  [{r['case_type']}]")
    if not missing_cases:
        print("  全部覆盖")

    # ---- 法条对比：向量化 law 切片带了什么 id 字段 ----
    law_metas = [m for m in metas if m.get("type") == "law"]
    print("\n=== 法条切片元数据字段 ===")
    if law_metas:
        print(f"  字段: {list(law_metas[0].keys())}")
        print(f"  样例: { {k: str(v)[:60] for k, v in law_metas[0].items()} }")

    pg_laws = await conn.fetch("SELECT id, title FROM laws ORDER BY id")
    pg_law_ids = {r["id"] for r in pg_laws}
    # 尝试常见字段名
    vec_law_ids = set()
    for m in law_metas:
        for key in ("law_id", "source_id", "doc_id", "id", "parent_id"):
            if m.get(key) in pg_law_ids:
                vec_law_ids.add(m[key])
                break
    covered = pg_law_ids & vec_law_ids
    not_covered = pg_law_ids - vec_law_ids
    print(f"\n=== 法条覆盖 ===")
    print(f"PG 法条 {len(pg_law_ids)} 条 | 向量库可追溯到的法条 {len(vec_law_ids)} 条")
    print(f"  已覆盖: {len(covered)} | 未覆盖: {len(not_covered)}")
    if not_covered:
        sample = sorted(not_covered)[:10]
        for lid in sample:
            row = next(r for r in pg_laws if r["id"] == lid)
            print(f"  未入向量库样例: {row['id']}  {row['title'][:40]}")
        # 未覆盖法条的类型分布
        from collections import Counter
        title_dist = Counter(
            next(r for r in pg_laws if r["id"] == lid)["title"][:12] for lid in list(not_covered)[:2000]
        )
        print("  未覆盖法条标题分布(Top10):")
        for k, v in title_dist.most_common(10):
            print(f"    {k}: {v}")

    await conn.close()


asyncio.run(main())
