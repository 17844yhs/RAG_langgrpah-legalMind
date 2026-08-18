"""将 PostgreSQL 中的案例 + 法律法规数据导入 ChromaDB 向量库

法律用 1000 字 chunk（覆盖 2-3 个相关条文），案例用 500 字 chunk。
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tortoise import Tortoise
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter


async def build_index():
    # 连接 PostgreSQL
    await Tortoise.init(
        db_url="postgres://legal_user:legal_pass@localhost:5432/legal_db",
        modules={"models": ["app.models.case", "app.models.law"]},
    )
    from app.models.case import Case
    from app.models.law import Law

    all_chunks = []

    # ── 1. 索引案例（500字切分）──
    cases = await Case.all()
    case_splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "\n", "。", "；", "，", " "],
    )
    for case in cases:
        doc = Document(
            page_content=f"{case.title}\n{case.summary or ''}\n{case.content or ''}",
            metadata={
                "id": str(case.id),
                "type": "case",
                "title": case.title,
                "case_number": case.case_number,
                "court": case.court,
                "case_type": case.case_type,
                "judgment_date": case.judgment_date.isoformat() if case.judgment_date else None,
                "summary": case.summary,
                "laws": case.laws,
            },
        )
        all_chunks.extend(case_splitter.split_documents([doc]))
    print(f"  案例：{len(cases)} 条")

    # ── 2. 索引法律法规（1000字切分，覆盖多个相关条文）──
    laws = await Law.all()
    law_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=100,
        separators=["\n\n", "\n", "。", "；", "，", " "],
    )
    for law in laws:
        keywords_str = " ".join(law.keywords) if law.keywords else ""
        doc = Document(
            page_content=f"{law.title}\n{law.content}\n{keywords_str}",
            metadata={
                "id": law.id,
                "type": "law",
                "title": law.title,
                "category": law.category,
                "keywords": law.keywords,
            },
        )
        all_chunks.extend(law_splitter.split_documents([doc]))
    print(f"  法律法规：{len(laws)} 条")

    if not all_chunks:
        print("  数据库中没有数据，请先运行 import_eval_data.py")
        await Tortoise.close_connections()
        return

    print(f"  分块完成：{len(all_chunks)} 个 chunk")

    # ── 3. 清空旧索引并写入向量库 ──
    from app.rag.vector_store import get_vector_store
    vector_store = get_vector_store()

    try:
        collection = vector_store._collection
        old_count = collection.count()
        if old_count > 0:
            collection.delete(ids=collection.get()["ids"])
            print(f"  已清空旧向量索引：{old_count} 条")
    except Exception as e:
        print(f"  清空旧向量索引失败（可能是空库）：{e}")

    # 删除旧 BM25 持久化索引（向量库重建后 BM25 需同步重建）
    from app.config import settings
    if os.path.exists(settings.BM25_INDEX_PATH):
        os.remove(settings.BM25_INDEX_PATH)
        print(f"  已删除旧 BM25 持久化索引：{settings.BM25_INDEX_PATH}")

    vector_store.add_documents(all_chunks)

    print(f"\n✅ 已导入 {len(all_chunks)} 个 chunk 到向量库")
    await Tortoise.close_connections()


if __name__ == "__main__":
    print("🔨 开始构建向量索引...")
    asyncio.run(build_index())