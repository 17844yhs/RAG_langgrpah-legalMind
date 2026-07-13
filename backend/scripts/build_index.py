"""将 PostgreSQL 中的案例数据导入 ChromaDB 向量库"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from tortoise import Tortoise
from langchain_core.documents import Document


async def build_index():
    # 连接 PostgreSQL
    await Tortoise.init(
        db_url="postgres://legal_user:legal_pass@localhost:5432/legal_db",
        modules={"models": ["app.models.case"]},
    )
    from app.models.case import Case

    cases = await Case.all()
    if not cases:
        print(" 数据库中没有案例，请先运行 seed_cases.py")
        return

    # 构建 LangChain Document 列表
    documents = []
    for case in cases:
        doc = Document(
            page_content=f"{case.title}\n{case.summary or ''}\n{case.content or ''}",
            metadata={
                "id": str(case.id),
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

    # 写入向量库
    from app.rag.vector_store import get_vector_store
    vector_store = get_vector_store()
    vector_store.add_documents(documents)

    print(f"已导入 {len(documents)} 条案例到向量库")
    await Tortoise.close_connections()


if __name__ == "__main__":
    print("🔨 开始构建向量索引...")
    asyncio.run(build_index())