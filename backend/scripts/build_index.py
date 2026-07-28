"""将 PostgreSQL 中的案例 + 法律法规数据导入 ChromaDB 向量库

加入文本分块：RecursiveCharacterTextSplitter 将长文档切成 chunk，
避免超出 embedding 模型的 token 上限导致信息截断。
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

    documents = []

    # ── 1. 索引案例 ──
    cases = await Case.all()
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
        documents.append(doc)
    print(f"  案例：{len(cases)} 条")

    # ── 2. 索引法律法规 ──
    laws = await Law.all()
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
        documents.append(doc)
    print(f"  法律法规：{len(laws)} 条")

    if not documents:
        print("  数据库中没有数据，请先运行 import_eval_data.py 和 seed_cases.py")
        await Tortoise.close_connections()
        return

    # ── 3. 文本分块 ──
    # 分块后每个 chunk 单独做 embedding，保留完整语义
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=500,
        chunk_overlap=50,
        separators=["\n\n", "\n", "。", "；", "，", " "],
    )
    chunks = splitter.split_documents(documents)
    print(f"  分块：{len(documents)} 条文档 → {len(chunks)} 个 chunk")

    # ── 4. 清空旧索引并写入向量库 ──
    from app.rag.vector_store import get_vector_store
    vector_store = get_vector_store()

    # 清空旧数据，避免追加导致新旧数据混合
    try:
        collection = vector_store._collection
        old_count = collection.count()
        if old_count > 0:
            # 删除所有旧文档
            collection.delete(ids=collection.get()["ids"])
            print(f"  已清空旧索引：{old_count} 条")
    except Exception as e:
        print(f"  清空旧索引失败（可能是空库）：{e}")

    vector_store.add_documents(chunks)

    print(f"\n✅ 已导入 {len(chunks)} 个 chunk 到向量库（来自 {len(documents)} 条文档）")
    await Tortoise.close_connections()


if __name__ == "__main__":
    print("🔨 开始构建向量索引...")
    asyncio.run(build_index())


# ============================================================
# 旧版（不分块，整条文档直接入向量库），保留备查
# ============================================================
#
# # ── 3. 写入向量库 ──
# from app.rag.vector_store import get_vector_store
# vector_store = get_vector_store()
# vector_store.add_documents(documents)
# print(f"\n✅ 已导入 {len(documents)} 条文档到向量库")