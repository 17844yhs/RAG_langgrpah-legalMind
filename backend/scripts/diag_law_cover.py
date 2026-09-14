"""验证：未按 id 入向量库的法条，其条文正文是否已被其他切片正文覆盖。用完可删。"""
import asyncio
from pathlib import Path

import asyncpg
import chromadb

PG_DSN = "postgresql://legal_user:legal_pass@localhost:5432/legal_db"
CHROMA_PATH = Path(__file__).resolve().parent.parent / "data" / "chroma"


def norm(s: str) -> str:
    return "".join(s.split())


async def main():
    conn = await asyncpg.connect(PG_DSN)
    pg_laws = await conn.fetch("SELECT id, title, content FROM laws")
    await conn.close()

    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    col = client.get_collection("legal_cases")
    chunks = col.get(include=["documents", "metadatas"])

    vec_ids = {m.get("id") for m in chunks["metadatas"] if m.get("type") == "law"}
    corpus = norm("".join(chunks["documents"]))  # 全部切片正文拼成大字符串做包含检查

    by_id_covered, by_content_covered, missing = 0, 0, []
    short_in_corpus = 0
    for r in pg_laws:
        c = (r["content"] or "").strip()
        if r["id"] in vec_ids:
            by_id_covered += 1
            continue
        snippet = norm(c)[:40]  # 取正文前 40 个有效字符做指纹
        if snippet and snippet in corpus:
            if len(c) < 50:
                short_in_corpus += 1  # 短条文，但正文已被其他切片覆盖
            else:
                by_content_covered += 1
        else:
            missing.append(r)

    total = len(pg_laws)
    print(f"PG 法条总数: {total}")
    print(f"  按 id 直接入向量库:        {by_id_covered}")
    print(f"  短条文但正文已被切片覆盖:  {short_in_corpus}")
    print(f"  长条文正文已被其他切片覆盖: {by_content_covered}")
    print(f"  真正缺失:                  {len(missing)}")
    for r in missing[:15]:
        c = (r["content"] or "").strip()
        print(f"    {r['id']}  {r['title'][:30]}  content_len={len(c)}  head={c[:30]!r}")


asyncio.run(main())
